#!/usr/bin/env python3
"""Reconcile v1 trade-journal rows (notes + tags) into research.trade_notes / research.trade_tags.

v1 shapes (backend/app/store.py, read-only reference):
  trade_tags : {client_id, fingerprint, tag_ids: [tag id], note: str}   <- one doc per trade;
               it holds BOTH the tag links and the free-text note.
  tags       : {id, client_id, name, color, description}
  trade_notes: no writer in the v1 repo; accepted defensively as
               {client_id, fingerprint|trade_fingerprint, note|text, [symbol, trade_date, ...]}.

Resolution of the v2 trade_id, per row:
  1. client:  v1 client id -> core.clients.legacy_id (matches v1 `id` or str(_id)).
  2. exact:   (client_id, fingerprint) -> ledger.trades.fingerprint (UNIQUE per client).
  3. fallback: the v1 trade with that fingerprint (or the row's own trade fields) gives
     (symbol, trade_date, side, qty, price); accepted only if it matches exactly ONE v2 trade.
Anything else is reported as unresolved by v1 _id + reason. Nothing else is printed:
no names, codes, note text, tag names or trade rows (AGENTS.md section 9).

Idempotent: ON CONFLICT DO NOTHING everywhere; an existing v2 note is never overwritten
(v2 edits win). Default is --dry-run; pass --apply to write (single transaction).

Env: MONGODB_URL, PG_DSN (optional MONGODB_DB, default "stocks").
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# ── pure helpers (unit-tested) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class NoteItem:
    v1_id: str
    v1_client_id: str
    fingerprint: str | None
    note: str
    hint: tuple | None = (
        None  # (symbol, date, side, qty, price) carried by the row itself
    )


@dataclass(frozen=True)
class TagItem:
    v1_id: str
    v1_client_id: str
    fingerprint: str | None
    tag_name: str
    colour: str | None
    description: str | None


@dataclass
class Extracted:
    notes: list[NoteItem] = field(default_factory=list)
    tags: list[TagItem] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)


def _dec(v: Any, places: str) -> Decimal | None:
    try:
        return Decimal(str(v)).quantize(Decimal(places))
    except (InvalidOperation, TypeError, ValueError):
        return None


def trade_key(
    symbol: Any, trade_date: Any, side: Any, qty: Any, price: Any
) -> tuple | None:
    """Normalised natural key; qty to 6dp and price to 4dp to match ledger.trades NUMERIC scales."""
    if not symbol or not trade_date or not side:
        return None
    q, p = _dec(qty, "0.000001"), _dec(price, "0.0001")
    if q is None or p is None:
        return None
    return (
        str(symbol).strip().upper(),
        str(trade_date)[:10],
        str(side).strip().lower(),
        q,
        p,
    )


def _hint_from(doc: dict) -> tuple | None:
    return trade_key(
        doc.get("symbol"),
        doc.get("trade_date"),
        doc.get("trade_type") or doc.get("side"),
        doc.get("quantity"),
        doc.get("price"),
    )


def extract_journal(
    trade_tags_docs: Iterable[dict],
    trade_notes_docs: Iterable[dict],
    v1_tags: Iterable[dict],
) -> Extracted:
    out = Extracted()
    tags_by_id = {str(t.get("id") or t.get("_id")): t for t in v1_tags}
    seen_note: set[tuple] = set()
    for d in trade_tags_docs:
        out.counts["v1_trade_tags_docs"] += 1
        vid, cid, fp = str(d.get("_id")), str(d.get("client_id")), d.get("fingerprint")
        note = (d.get("note") or "").strip()
        if note:
            out.notes.append(NoteItem(vid, cid, fp, note))
            seen_note.add((cid, fp))
        for tid in d.get("tag_ids") or []:
            out.counts["v1_tag_links"] += 1
            t = tags_by_id.get(str(tid))
            if not t or not (t.get("name") or "").strip():
                out.counts["dangling_tag_refs"] += (
                    1  # tag deleted in v1: nothing to migrate
                )
                continue
            out.tags.append(
                TagItem(
                    vid,
                    cid,
                    fp,
                    t["name"].strip(),
                    t.get("color") or t.get("colour"),
                    t.get("description"),
                )
            )
    for d in trade_notes_docs:
        out.counts["v1_trade_notes_docs"] += 1
        cid = str(d.get("client_id"))
        fp = d.get("fingerprint") or d.get("trade_fingerprint")
        note = (d.get("note") or d.get("text") or "").strip()
        if not note:
            out.counts["empty_notes"] += 1
            continue
        if (cid, fp) in seen_note and fp:
            out.counts["note_dupe_of_trade_tags"] += 1
            continue
        out.notes.append(NoteItem(str(d.get("_id")), cid, fp, note, _hint_from(d)))
    out.counts["expected_notes"] = len(out.notes)
    out.counts["expected_tag_links"] = len(out.tags)
    return out


def build_client_map(
    v1_clients: Iterable[dict], v2_rows: Iterable[tuple[Any, str | None]]
) -> dict[str, Any]:
    """v1 client id (the `id` field the v1 app uses as client_id) -> v2 client_id UUID."""
    by_legacy = {str(leg): cid for cid, leg in v2_rows if leg}
    out: dict[str, Any] = {}
    for c in v1_clients:
        keys = [str(k) for k in (c.get("id"), c.get("_id")) if k is not None]
        uuid = next((by_legacy[k] for k in keys if k in by_legacy), None)
        if uuid is not None:
            for k in keys:
                out[k] = uuid
    # legacy ids that are already the v1 client_id string
    for leg, cid in by_legacy.items():
        out.setdefault(leg, cid)
    return out


@dataclass
class V2Index:
    by_fp: dict[tuple, int]  # (client_uuid, fingerprint) -> trade_id
    by_key: dict[tuple, list[int]]  # (client_uuid, *trade_key) -> [trade_id]

    @classmethod
    def build(cls, rows: Iterable[dict]) -> V2Index:
        by_fp: dict[tuple, int] = {}
        by_key: dict[tuple, list[int]] = {}
        for r in rows:
            by_fp[(r["client_id"], r["fingerprint"])] = r["trade_id"]
            k = trade_key(
                r["symbol"], r["trade_date"], r["trade_type"], r["quantity"], r["price"]
            )
            if k:
                by_key.setdefault((r["client_id"], *k), []).append(r["trade_id"])
        return cls(by_fp, by_key)


def resolve(
    v1_client_id: str,
    fingerprint: str | None,
    hint: tuple | None,
    client_map: dict[str, Any],
    v1_trade_keys: dict[tuple, tuple],
    idx: V2Index,
) -> tuple[Any, int | None, str]:
    """Return (client_uuid, trade_id, how). how in exact|fallback|no_client|orphan|no_match|ambiguous."""
    cu = client_map.get(v1_client_id)
    if cu is None:
        return None, None, "no_client"
    if fingerprint and (cu, fingerprint) in idx.by_fp:
        return cu, idx.by_fp[(cu, fingerprint)], "exact"
    key = hint or v1_trade_keys.get((v1_client_id, fingerprint))
    if key is None:
        return cu, None, "orphan"  # v1 trade gone and no own fields: cannot place it
    hits = idx.by_key.get((cu, *key), [])
    if len(hits) == 1:
        return cu, hits[0], "fallback"
    return cu, None, "ambiguous" if hits else "no_match"


def v1_trade_key_map(v1_trades: Iterable[dict]) -> dict[tuple, tuple]:
    out: dict[tuple, tuple] = {}
    for t in v1_trades:
        k = trade_key(
            t.get("symbol"),
            t.get("trade_date"),
            t.get("trade_type"),
            t.get("quantity"),
            t.get("price"),
        )
        if k and t.get("fingerprint"):
            out[(str(t.get("client_id")), t["fingerprint"])] = k
    return out


# ── I/O ────────────────────────────────────────────────────────────────────────


def _mongo(url: str, dbname: str):
    from pymongo import MongoClient

    return MongoClient(url, serverSelectionTimeoutMS=10_000)[dbname]


async def run(pg_dsn: str, mongo_url: str, mongo_db: str, apply: bool) -> int:
    import asyncpg

    m = _mongo(mongo_url, mongo_db)
    ex = extract_journal(
        m.trade_tags.find({}),
        m.trade_notes.find({}),
        m.tags.find({}, {"id": 1, "name": 1, "color": 1, "description": 1}),
    )
    fps = {(i.v1_client_id, i.fingerprint) for i in [*ex.notes, *ex.tags]}
    v1_cids = sorted({c for c, _ in fps})
    v1_trades = m.trades.find(
        {
            "client_id": {"$in": v1_cids},
            "fingerprint": {"$in": [f for _, f in fps if f]},
        },
        {
            "client_id": 1,
            "fingerprint": 1,
            "symbol": 1,
            "trade_date": 1,
            "trade_type": 1,
            "quantity": 1,
            "price": 1,
        },
    )
    v1_keys = v1_trade_key_map(v1_trades)

    conn = await asyncpg.connect(pg_dsn, timeout=15, command_timeout=120)
    try:
        cmap = build_client_map(
            m.clients.find({}, {"id": 1}),
            [
                (r["client_id"], r["legacy_id"])
                for r in await conn.fetch(
                    "SELECT client_id, legacy_id FROM core.clients"
                )
            ],
        )
        client_uuids = list({cmap[c] for c in v1_cids if c in cmap})
        idx = V2Index.build(
            await conn.fetch(
                "SELECT trade_id, client_id, fingerprint, symbol, trade_date, trade_type, quantity, price "
                "FROM ledger.trades WHERE client_id = ANY($1::uuid[])",
                client_uuids,
            )
        )
        before = await _counts(conn)
        stats: Counter = Counter()
        unresolved: list[tuple[str, str, str]] = []
        tx = conn.transaction()
        await tx.start()
        try:
            for n in ex.notes:
                cu, tid, how = resolve(
                    n.v1_client_id, n.fingerprint, n.hint, cmap, v1_keys, idx
                )
                stats[f"note_{how}"] += 1
                if tid is None:
                    unresolved.append(("note", n.v1_id, how))
                    continue
                existing = await conn.fetchval(
                    "SELECT note FROM research.trade_notes WHERE trade_id=$1", tid
                )
                if existing is not None:
                    stats[
                        "note_already_present"
                        if existing == n.note
                        else "note_conflict_v2_kept"
                    ] += 1
                    continue
                stats["note_insert"] += 1
                if apply:
                    await conn.execute(
                        "INSERT INTO research.trade_notes (client_id, trade_id, note) VALUES ($1,$2,$3) "
                        "ON CONFLICT (trade_id) DO NOTHING",
                        cu,
                        tid,
                        n.note,
                    )
            for t in ex.tags:
                cu, tid, how = resolve(
                    t.v1_client_id, t.fingerprint, None, cmap, v1_keys, idx
                )
                stats[f"tag_{how}"] += 1
                if tid is None:
                    unresolved.append(("tag", t.v1_id, how))
                    continue
                tag_id = await conn.fetchval(
                    "SELECT tag_id FROM research.tags WHERE client_id=$1 AND name=$2",
                    cu,
                    t.tag_name,
                )
                if tag_id is None:
                    stats["tag_def_insert"] += 1
                    if not apply:
                        stats["tag_link_insert"] += 1
                        continue
                    tag_id = await conn.fetchval(
                        "INSERT INTO research.tags (client_id, name, colour, description) VALUES ($1,$2,$3,$4) "
                        "ON CONFLICT (client_id, name) DO UPDATE SET name = EXCLUDED.name RETURNING tag_id",
                        cu,
                        t.tag_name,
                        t.colour,
                        t.description,
                    )
                linked = await conn.fetchval(
                    "SELECT 1 FROM research.trade_tags WHERE trade_id=$1 AND tag_id=$2",
                    tid,
                    tag_id,
                )
                if linked:
                    stats["tag_link_already_present"] += 1
                    continue
                stats["tag_link_insert"] += 1
                if apply:
                    await conn.execute(
                        "INSERT INTO research.trade_tags (client_id, trade_id, tag_id) VALUES ($1,$2,$3) "
                        "ON CONFLICT (trade_id, tag_id) DO NOTHING",
                        cu,
                        tid,
                        tag_id,
                    )
            if apply:
                await tx.commit()
            else:
                await tx.rollback()
        except BaseException:
            await tx.rollback()
            raise
        after = await _counts(conn)
    finally:
        await conn.close()

    mode = "APPLY" if apply else "DRY-RUN (no writes)"
    print(f"== reconcile_trade_notes_tags [{mode}]")
    for k in sorted(ex.counts):
        print(f"  v1 {k:<28} {ex.counts[k]}")
    for k in sorted(stats):
        print(f"  {k:<31} {stats[k]}")
    print(f"  pg before: notes={before[0]} tag_links={before[1]} tag_defs={before[2]}")
    print(f"  pg after : notes={after[0]} tag_links={after[1]} tag_defs={after[2]}")
    for kind, vid, how in unresolved:
        print(f"  UNRESOLVED {kind} v1_id={vid} reason={how}")
    return 1 if unresolved else 0


async def _counts(conn) -> tuple[int, int, int]:
    return (
        await conn.fetchval("SELECT count(*) FROM research.trade_notes"),
        await conn.fetchval("SELECT count(*) FROM research.trade_tags"),
        await conn.fetchval("SELECT count(*) FROM research.tags"),
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--dry-run", action="store_true", default=True, help="default; report only"
    )
    g.add_argument("--apply", action="store_true", help="write in one transaction")
    p.add_argument("--mongo-db", default=os.getenv("MONGODB_DB", "stocks"))
    a = p.parse_args()
    pg, mg = os.getenv("PG_DSN"), os.getenv("MONGODB_URL")
    if not pg or not mg:
        sys.exit("PG_DSN and MONGODB_URL must be set")
    sys.exit(asyncio.run(run(pg, mg, a.mongo_db, a.apply)))


if __name__ == "__main__":
    main()
