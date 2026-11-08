#!/usr/bin/env python3
"""Is the v1 Mongo -> v2 Postgres migration done? Count-level check (POST-RESET-PLAN section 1).

Prints one row per entity: v1 count, v2 count, status. Counts only; no row content.
Exit 0 when every REQUIRED entity passes, 1 otherwise.

Pass rule for required entities: v2 >= v1 (v2 may have gained rows since cutover);
--strict demands v2 == v1. Trades additionally require every v1 fingerprint to exist in
ledger.trades (a count can hide a loss offset by new rows).
Informational entities (deferred ORB data, pdf_uploads awaiting an owner decision, the
watchlist doc->list reshaping) are shown but never fail the run.

--ledger: per-client reconcile (R18) -- v1 vs v2 trade counts, fingerprints missing either
side, and per-symbol raw open quantity (buys - sells; tombstoned v2 trades excluded).
Exit 1 while any client drifts. Prints v2 client ids, client codes and symbols only.

Env: MONGODB_URL, PG_DSN (optional MONGODB_DB, default "stocks").
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    label: str
    v1: int | None
    v2: int | None
    required: bool
    note: str = ""


def status(c: Check, strict: bool) -> str:
    if c.v1 is None or c.v2 is None:
        return "ERROR" if c.required else "n/a"
    ok = c.v2 == c.v1 if strict else c.v2 >= c.v1
    if ok:
        return "OK" if c.v2 == c.v1 else "OK(+v2)"
    return "MISMATCH" if c.required else "info"


def evaluate(
    checks: Iterable[Check], strict: bool
) -> tuple[list[tuple[Check, str]], int]:
    rows = [(c, status(c, strict)) for c in checks]
    failed = any(c.required and s in ("MISMATCH", "ERROR") for c, s in rows)
    return rows, 1 if failed else 0


def render(rows: list[tuple[Check, str]]) -> str:
    out = [
        f"{'entity':<36}{'v1':>12}{'v2':>12}  {'req':<4}{'status':<10}note",
        "-" * 96,
    ]
    for c, s in rows:
        f = lambda x: "-" if x is None else f"{x:,}"
        out.append(
            f"{c.label:<36}{f(c.v1):>12}{f(c.v2):>12}  {'yes' if c.required else 'no':<4}{s:<10}{c.note}"
        )
    return "\n".join(out)


def watchlist_counts(docs: Iterable[dict]) -> tuple[int, int, int]:
    """(docs, lists, distinct-symbol entries). v1 docs hold `lists[].entries` or legacy `entries`/`symbols`."""
    n_docs = n_lists = n_entries = 0
    for d in docs:
        n_docs += 1
        lists = d.get("lists")
        if lists is None and ("entries" in d or "symbols" in d):
            lists = [
                {
                    "entries": d.get("entries")
                    or [{"symbol": s} for s in d.get("symbols") or []]
                }
            ]
        for lst in lists or []:
            n_lists += 1
            syms = {
                (e.get("symbol") if isinstance(e, dict) else e)
                for e in lst.get("entries") or []
            }
            n_entries += len({s for s in syms if s})
    return n_docs, n_lists, n_entries


def missing_fingerprints(v1_fps: Iterable[str], v2_fps: Iterable[str]) -> int:
    return len(set(v1_fps) - set(v2_fps))


# ── per-client ledger reconcile (R18) ─────────────────────────────────────────


@dataclass
class ClientDrift:
    client: str  # v2 client_id (or "v1:<id>" when the v1 client has no v2 row)
    code: str | None
    v1_trades: int
    v2_trades: int
    missing_in_v2: int
    extra_in_v2: int
    qty_drift: dict[str, tuple[float, float]]  # symbol -> (v1 open qty, v2 open qty)

    @property
    def drifted(self) -> bool:
        return bool(self.missing_in_v2 or self.extra_in_v2 or self.qty_drift)


def _open_qty(rows: Iterable[tuple]) -> dict[str, float]:
    """Raw ledger net quantity per symbol (buys - sells), before corporate actions."""
    out: dict[str, float] = {}
    for _fp, sym, side, qty in rows:
        s = str(sym or "").strip().upper()
        out[s] = out.get(s, 0.0) + (float(qty) if str(side).lower() == "buy" else -float(qty))
    return out


def ledger_drift(
    v1_by_client: dict[str, list[tuple]],
    v2_by_client: dict[str, list[tuple]],
    codes: dict[str, str | None],
    tol: float = 1e-6,
) -> list[ClientDrift]:
    """Per client: trade counts, fingerprints missing either side, per-symbol open-qty drift.

    Rows are (fingerprint, symbol, side, quantity); v2 rows exclude tombstoned trades.
    Keys are v2 client ids; a v1 client with no v2 row is keyed "v1:<id>".
    """
    out = []
    for cid in sorted(set(v1_by_client) | set(v2_by_client)):
        a, b = v1_by_client.get(cid, []), v2_by_client.get(cid, [])
        fa, fb = {r[0] for r in a}, {r[0] for r in b}
        qa, qb = _open_qty(a), _open_qty(b)
        qd = {
            s: (round(qa.get(s, 0.0), 6), round(qb.get(s, 0.0), 6))
            for s in sorted(set(qa) | set(qb))
            if abs(qa.get(s, 0.0) - qb.get(s, 0.0)) > tol
        }
        out.append(ClientDrift(cid, codes.get(cid), len(a), len(b), len(fa - fb), len(fb - fa), qd))
    return out


def render_drift(rows: list[ClientDrift], show_ok: bool = False) -> str:
    out = [f"{'client':<40}{'code':<12}{'v1':>7}{'v2':>7}{'miss':>6}{'extra':>6}  symbols drifting", "-" * 100]
    for r in rows:
        if not r.drifted and not show_ok:
            continue
        syms = ", ".join(f"{s} {a:g}->{b:g}" for s, (a, b) in list(r.qty_drift.items())[:8])
        more = f" (+{len(r.qty_drift) - 8})" if len(r.qty_drift) > 8 else ""
        out.append(f"{r.client:<40}{(r.code or '-'):<12}{r.v1_trades:>7}{r.v2_trades:>7}"
                   f"{r.missing_in_v2:>6}{r.extra_in_v2:>6}  {syms}{more}")
    n = sum(r.drifted for r in rows)
    out.append(f"\n{n} of {len(rows)} clients drift")
    return "\n".join(out)


# ── I/O ────────────────────────────────────────────────────────────────────────


async def collect(pg_dsn: str, mongo_url: str, mongo_db: str) -> list[Check]:
    import asyncpg
    from pymongo import MongoClient

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reconcile_trade_notes_tags import extract_journal

    m = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)[mongo_db]
    conn = await asyncpg.connect(pg_dsn, timeout=15, command_timeout=120)

    def mc(name: str) -> int:
        return m[name].count_documents({})

    async def pc(table: str) -> int | None:
        if not await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table):
            return None
        return await conn.fetchval(
            f"SELECT count(*) FROM {table}"
        )  # table names are constants below

    async def est(table: str) -> int | None:
        if not await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table):
            return None
        n = await conn.fetchval(
            "SELECT reltuples::bigint FROM pg_class WHERE oid = $1::regclass", table
        )
        return max(int(n), 0)

    try:
        wl_docs, wl_lists, wl_entries = watchlist_counts(
            m.watchlists.find({}, {"lists": 1, "entries": 1, "symbols": 1})
        )
        board_items = sum(
            len(d.get("items") or []) for d in m.boards.find({}, {"items": 1})
        )
        j = extract_journal(
            m.trade_tags.find({}), m.trade_notes.find({}), m.tags.find({})
        )
        v1_fps = [
            d["fingerprint"]
            for d in m.trades.find({}, {"fingerprint": 1, "_id": 0})
            if d.get("fingerprint")
        ]
        v2_fps = [
            r[0] for r in await conn.fetch("SELECT fingerprint FROM ledger.trades")
        ]
        bars = list(
            m.orb_candles_1m.aggregate([{"$group": {"_id": None, "n": {"$sum": "$n"}}}])
        )
        checks = [
            Check("managers", mc("managers"), await pc("core.managers"), True),
            Check("clients", mc("clients"), await pc("core.clients"), True),
            Check("trades", mc("trades"), await pc("ledger.trades"), True),
            Check(
                "trades: v1 fingerprints found",
                len(set(v1_fps)),
                len(set(v1_fps)) - missing_fingerprints(v1_fps, v2_fps),
                True,
                "every v1 trade present by fingerprint",
            ),
            Check("uploads", mc("uploads"), await pc("ledger.uploads"), True),
            Check(
                "corporate_actions",
                mc("corporate_actions"),
                await pc("ledger.corporate_actions"),
                True,
            ),
            Check("dividends", mc("dividends"), await pc("ledger.dividends"), True),
            Check(
                "benchmark_prices",
                mc("benchmark_prices"),
                await pc("market.benchmark_values"),
                True,
            ),
            Check(
                "watchlists (docs -> lists)",
                wl_lists,
                await pc("research.watchlists"),
                False,
                f"{wl_docs} v1 docs; empty docs collapse (note A)",
            ),
            Check(
                "watchlist entries",
                wl_entries,
                await pc("research.watchlist_entries"),
                True,
            ),
            Check("board items", board_items, await pc("research.board_items"), True),
            Check("tags", mc("tags"), await pc("research.tags"), True),
            Check("thesis", mc("thesis"), await pc("research.stock_theses"), True),
            Check(
                "trade notes (derived)",
                j.counts["expected_notes"],
                await pc("research.trade_notes"),
                True,
                f"trade_tags.note + trade_notes; raw trade_notes docs={j.counts['v1_trade_notes_docs']}",
            ),
            Check(
                "trade tag links (derived)",
                j.counts["expected_tag_links"],
                await pc("research.trade_tags"),
                True,
                f"raw trade_tags docs={j.counts['v1_trade_tags_docs']}, dangling refs={j.counts['dangling_tag_refs']}",
            ),
            Check(
                "pdf_uploads",
                mc("pdf_uploads"),
                await pc("research.pdf_uploads"),
                False,
                "news PDFs; no v2 table; owner decision",
            ),
            Check(
                "screener_snapshots",
                mc("screener_snapshots"),
                await pc("research.screener_snapshots"),
                False,
                "ORB-adjacent, deferred",
            ),
            Check(
                "orb_candles_1m (bars)",
                bars[0]["n"] if bars else 0,
                await est("market.candles_1m"),
                False,
                "v2 ~reltuples; default import is last 20 sessions",
            ),
            Check(
                "orb_calendar",
                mc("orb_calendar"),
                await pc("market.trading_calendar"),
                False,
                "deferred",
            ),
        ]
    finally:
        await conn.close()
    return checks


async def collect_ledger(pg_dsn: str, mongo_url: str, mongo_db: str) -> list[ClientDrift]:
    import asyncpg
    from pymongo import MongoClient

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reconcile_trade_notes_tags import build_client_map

    m = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)[mongo_db]
    conn = await asyncpg.connect(pg_dsn, timeout=15, command_timeout=300)
    try:
        clients = await conn.fetch("SELECT client_id, legacy_id, client_code FROM core.clients")
        cmap = build_client_map(
            m.clients.find({}, {"id": 1}), [(r["client_id"], r["legacy_id"]) for r in clients]
        )
        codes: dict[str, str | None] = {str(r["client_id"]): r["client_code"] for r in clients}
        v1: dict[str, list[tuple]] = {}
        proj = {"client_id": 1, "fingerprint": 1, "symbol": 1, "trade_type": 1, "quantity": 1, "_id": 0}
        for t in m.trades.find({}, proj):
            cu = cmap.get(str(t.get("client_id")))
            key = str(cu) if cu is not None else f"v1:{t.get('client_id')}"
            v1.setdefault(key, []).append(
                (t.get("fingerprint"), t.get("symbol"), t.get("trade_type"), t.get("quantity") or 0)
            )
        v2: dict[str, list[tuple]] = {}
        for r in await conn.fetch(
            "SELECT client_id, fingerprint, symbol, trade_type, quantity FROM ledger.trades "
            "WHERE deleted_at IS NULL"
        ):
            v2.setdefault(str(r["client_id"]), []).append(
                (r["fingerprint"], r["symbol"], r["trade_type"], r["quantity"])
            )
    finally:
        await conn.close()
    return ledger_drift(v1, v2, codes)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--strict", action="store_true", help="require v2 == v1 instead of v2 >= v1"
    )
    p.add_argument("--mongo-db", default=os.getenv("MONGODB_DB", "stocks"))
    p.add_argument(
        "--ledger",
        action="store_true",
        help="per-client R18 reconcile: trade counts + per-symbol open qty; exit 1 on drift",
    )
    p.add_argument("--show-ok", action="store_true", help="with --ledger, list clients without drift too")
    a = p.parse_args()
    pg, mg = os.getenv("PG_DSN"), os.getenv("MONGODB_URL")
    if not pg or not mg:
        sys.exit("PG_DSN and MONGODB_URL must be set")
    if a.ledger:
        drift = asyncio.run(collect_ledger(pg, mg, a.mongo_db))
        print(render_drift(drift, a.show_ok))
        sys.exit(1 if any(r.drifted for r in drift) else 0)
    rows, code = evaluate(asyncio.run(collect(pg, mg, a.mongo_db)), a.strict)
    print(render(rows))
    print(
        f"\nmigration {'COMPLETE' if code == 0 else 'INCOMPLETE'} (required entities)"
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
