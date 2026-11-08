"""ORB data for v2 (:8205). Source-pluggable; the only source today is a READ-ONLY v1-Mongo sync.

AGENTS §10: one production Angel identity, held by v1's live feed. Nothing here logs into
Angel, calls SmartAPI or opens a websocket. `V1MongoSource` reads v1's orb_* collections;
at cutover a live source replaces it behind `OrbSource`, mappers and writer unchanged.
One pass: scripts/sync_v1_orb_to_v2.py (pi-orb-sync.timer). `python pi_workers/orb_feed.py`
serves /healthz only. Candles are owned by market.candles_1m / market.eod_prices.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

PORT = int(os.environ.get("PORT", "8205"))
SOURCE_V1_MONGO, HEARTBEAT_ID = "v1_mongo", "orb-heartbeat"


def to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date) or not isinstance(v, str):
        return v if isinstance(v, date) else None
    return _coerce(v[:10], date.fromisoformat)


def to_ts(v: Any) -> datetime | None:
    if isinstance(v, str):
        v = _coerce(v, datetime.fromisoformat)
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return _coerce(v, lambda x: datetime.fromtimestamp(float(x), tz=timezone.utc))


def _coerce(v: Any, fn: Callable[[Any], Any]) -> Any:
    if v is None or isinstance(v, bool):
        return None
    try:
        return fn(v)
    except (TypeError, ValueError, ArithmeticError):
        return None


def to_int(v: Any) -> int | None:
    return _coerce(v, int)


def to_num(v: Any) -> Decimal | None:
    return _coerce(v, lambda x: Decimal(str(x)) if math.isfinite(float(x)) else None)


def _finite(v: Any) -> Any:
    """jsonb rejects NaN/Infinity; v1 floats can carry them."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {str(k): _finite(x) for k, x in v.items()}
    return [_finite(x) for x in v] if isinstance(v, (list, tuple)) else v


def to_json(v: Any) -> str | None:
    return None if v is None else json.dumps(_finite(v), default=str, sort_keys=True)


def _text(v: Any) -> str | None:
    return None if v is None else str(v)


def doc_hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, default=str, sort_keys=True).encode()).hexdigest()


def _base(doc: dict, used: Iterable[str]) -> dict:
    skip = set(used) | {"_id"}
    return {
        "legacy_id": str(doc["_id"]),
        "source": SOURCE_V1_MONGO,
        "source_hash": doc_hash(doc),
        "extra": to_json({k: v for k, v in doc.items() if k not in skip}),
    }


def _date_or_id(doc: dict) -> date | None:
    return to_date(doc.get("date")) or to_date(str(doc.get("_id", "")))


# ── mappers: v1 document -> orb.* row (pure; None = rejected) ─────────
def map_universe(doc: dict) -> dict | None:
    d = _date_or_id(doc)
    if d is None:
        return None
    used = ("date", "size", "min_turnover_cr", "pool", "members", "ranked")
    return {**_base(doc, used), "trade_date": d, "size": to_int(doc.get("size")),
            "min_turnover_cr": to_num(doc.get("min_turnover_cr")),
            "pool": to_json(doc.get("pool")), "members": to_json(doc.get("members") or []),
            "ranked": to_json(doc.get("ranked"))}


_SIGNAL_PAISE = ("entry", "stop", "t1", "t2", "risk")


def map_signal(doc: dict) -> dict | None:
    d = _date_or_id(doc)
    if d is None:
        return None
    used = ("date", "kind", "sym", "minute", "side", "qty", "candidates", "passed",
            "shortlist", "rows", "trace", "config", "at") + _SIGNAL_PAISE
    row = {**_base(doc, used), "trade_date": d, "kind": str(doc.get("kind") or "unknown"),
           "sym": doc.get("sym"), "minute": to_int(doc.get("minute")),
           "side": to_int(doc.get("side")), "qty": to_int(doc.get("qty")),
           "candidates": to_int(doc.get("candidates")), "passed": to_int(doc.get("passed")),
           "shortlist": to_json(doc.get("shortlist")), "screen_rows": to_json(doc.get("rows")),
           "trace": to_json(doc.get("trace")), "config": _text(doc.get("config")),
           "at": to_ts(doc.get("at"))}
    for k in _SIGNAL_PAISE:
        row[f"{k}_paise"] = to_int(doc.get(k))
    return row


def health_kind(doc: dict) -> str:
    if doc.get("_id") == HEARTBEAT_ID:
        return "heartbeat"
    return str(doc.get("kind") or ("reconcile" if "agree_pct" in doc else "other"))


def map_health(doc: dict) -> dict | None:
    used = ("date", "kind", "agree_pct", "passes_exit_test", "symbols",
            "minutes_compared", "minutes_matched", "at")
    pet = doc.get("passes_exit_test")
    return {**_base(doc, used), "trade_date": to_date(doc.get("date")),
            "kind": health_kind(doc), "agree_pct": to_num(doc.get("agree_pct")),
            "passes_exit_test": pet if isinstance(pet, bool) else None,
            "symbols": to_int(doc.get("symbols")),
            "minutes_compared": to_int(doc.get("minutes_compared")),
            "minutes_matched": to_int(doc.get("minutes_matched")), "at": to_ts(doc.get("at"))}


def map_job(doc: dict) -> dict | None:
    used = ("date", "job", "ok", "minute", "detail", "seconds", "owner", "at")
    ok = doc.get("ok")
    return {**_base(doc, used), "trade_date": to_date(doc.get("date")), "job": doc.get("job"),
            "ok": ok if isinstance(ok, bool) else None, "minute": to_int(doc.get("minute")),
            "detail": _text(doc.get("detail")), "seconds": to_num(doc.get("seconds")),
            "owner": _text(doc.get("owner")), "at": to_ts(doc.get("at"))}


def map_journal(doc: dict) -> dict | None:
    d = to_date(doc.get("date"))
    if d is None or not doc.get("sym"):
        return None
    used = ("date", "sym", "reason", "side", "minute", "qty", "price", "entry", "stop",
            "r", "config", "at")
    return {**_base(doc, used), "trade_date": d, "sym": doc["sym"],
            "reason": _text(doc.get("reason")), "side": to_int(doc.get("side")),
            "minute": to_int(doc.get("minute")), "qty": to_int(doc.get("qty")),
            "price_paise": to_int(doc.get("price")), "entry_paise": to_int(doc.get("entry")),
            "stop_paise": to_int(doc.get("stop")), "r": to_num(doc.get("r")),
            "config": _text(doc.get("config")), "at": to_ts(doc.get("at"))}


@dataclass(frozen=True)
class TableSpec:
    table: str
    collection: str
    mapper: Callable[[dict], dict | None]


TABLES: tuple[TableSpec, ...] = (
    TableSpec("universe", "orb_universe", map_universe),
    TableSpec("signals", "orb_signals", map_signal),
    TableSpec("health", "orb_health", map_health),
    TableSpec("jobs", "orb_jobs", map_job),
    TableSpec("journal", "orb_journal", map_journal),
)


# ── sources ───────────────────────────────────────────────────────────
class OrbSource(Protocol):
    name: str
    def fetch(self, collection: str, since: date | None) -> list[dict]: ...


class V1MongoSource:
    """Read-only window onto v1's Mongo. Never writes, never touches Angel."""

    name = SOURCE_V1_MONGO
    def __init__(self, url: str, db: str) -> None:
        from pymongo import MongoClient  # lazy: only the sync path needs it

        self._client = MongoClient(url, tz_aware=True, serverSelectionTimeoutMS=5000,
                                   socketTimeoutMS=30000, connectTimeoutMS=5000)
        self._db = self._client[db]

    def fetch(self, collection: str, since: date | None) -> list[dict]:
        query: dict = {}
        if since is not None:
            query = {"$or": [{"date": {"$gte": since.isoformat()}},
                             {"date": {"$exists": False}}]}
        return list(self._db[collection].find(query))

    def close(self) -> None:
        self._client.close()


# ── writer: COPY -> staging -> upsert (AGENTS §3.8) ────────────────────
async def existing_hashes(conn: Any, table: str, ids: list[str]) -> dict[str, str]:
    recs = await conn.fetch(
        f"SELECT legacy_id, source_hash FROM orb.{table} WHERE legacy_id = ANY($1::text[])", ids)
    return {r["legacy_id"]: r["source_hash"] for r in recs}


async def upsert(conn: Any, table: str, rows: list[dict]) -> tuple[int, int]:
    """Returns (inserted, updated). Rows whose source_hash is unchanged are not touched."""
    if not rows:
        return 0, 0
    cols = list(rows[0].keys())
    col_sql = ", ".join(cols)
    stg = f"stg_orb_{table}"
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "legacy_id")
    async with conn.transaction():
        await conn.execute(
            f"CREATE TEMP TABLE {stg} ON COMMIT DROP AS "
            f"SELECT {col_sql} FROM orb.{table} WITH NO DATA")
        await conn.copy_records_to_table(
            stg, records=[tuple(r[c] for c in cols) for r in rows], columns=cols)
        recs = await conn.fetch(
            f"INSERT INTO orb.{table} ({col_sql}) SELECT {col_sql} FROM {stg} "
            f"ON CONFLICT (legacy_id) DO UPDATE SET {sets}, synced_at = now() "
            f"WHERE orb.{table}.source_hash IS DISTINCT FROM EXCLUDED.source_hash "
            f"RETURNING (xmax = 0) AS inserted")
    ins = sum(1 for r in recs if r["inserted"])
    return ins, len(recs) - ins


async def _since(conn: Any, table: str, lookback_days: int) -> date | None:
    last = await conn.fetchval(f"SELECT max(trade_date) FROM orb.{table}")
    return None if last is None else last - timedelta(days=lookback_days)


async def sync_table(conn: Any, source: OrbSource, spec: TableSpec, *, full: bool,
                     dry_run: bool, lookback_days: int) -> dict[str, int]:
    since = None if (full or conn is None) else await _since(conn, spec.table, lookback_days)
    docs = source.fetch(spec.collection, since)
    mapped = [spec.mapper(doc) for doc in docs]
    rows = [r for r in mapped if r is not None]
    out = {"fetched": len(docs), "rejected": len(docs) - len(rows)}
    if conn is None:
        return out
    if dry_run:
        have = await existing_hashes(conn, spec.table, [r["legacy_id"] for r in rows])
        out["would_insert"] = sum(1 for r in rows if r["legacy_id"] not in have)
        out["would_update"] = sum(1 for r in rows if have.get(r["legacy_id"])
                                  not in (None, r["source_hash"]))
        return out
    out["inserted"], out["updated"] = await upsert(conn, spec.table, rows)
    out["unchanged"] = len(rows) - out["inserted"] - out["updated"]
    return out


async def run_sync(source: OrbSource, dsn: str | None, *, full: bool = False,
                   dry_run: bool = False, lookback_days: int = 3) -> dict[str, dict]:
    """One pass over every ORB collection. Counts only; never logs document contents."""
    import asyncpg

    conn = await asyncpg.connect(dsn=dsn, timeout=10, command_timeout=60) if dsn else None
    try:
        return {spec.table: await sync_table(conn, source, spec, full=full, dry_run=dry_run,
                                             lookback_days=lookback_days)
                for spec in TABLES}
    finally:
        if conn is not None:
            await conn.close()


def serve() -> None:
    """Long-running health endpoint for pi-orb-feed.service; no feed, no sync loop."""
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI(title="Portfolio Intelligence - ORB feed")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "worker": "orb-feed", "port": PORT,
                "source": SOURCE_V1_MONGO, "live_feed": False,
                "note": "pre-cutover: data synced from v1 Mongo by pi-orb-sync.timer",
                "restart_restricted": "08:45-15:30 IST (applies once the live feed moves here)"}

    uvicorn.run(app, host="127.0.0.1", port=PORT)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
