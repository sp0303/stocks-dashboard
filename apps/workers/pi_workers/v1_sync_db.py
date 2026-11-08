"""I/O side of the v1 (Mongo) -> v2 (Postgres) market sync.

Shared by ``scripts/sync_v1_market_to_v2.py`` (one-off / backfill) and
``eod_worker --sync-v1`` (daily). Reads Mongo read-only; writes market.* via
COPY -> temp staging -> INSERT .. ON CONFLICT (AGENTS §3.8). Logs counts only.

The whole sync runs in ONE transaction. ``dry_run`` executes every statement
and then rolls back, so the reported counts are exact and nothing persists.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import asyncpg

from pi_workers.v1_sync import (
    EOD_SOURCE,
    TransformStats,
    build_upsert_sql,
    map_symbols_to_securities,
    transform_daily_rows,
)
from pi_workers.v1_sync_ref import sync_benchmarks, sync_calendar

logger = logging.getLogger("pi_workers.v1_sync")

BATCH_SYMBOLS = 200
# Re-read this many days before the last loaded orb_rollup date, so a late or
# corrected v1 rollup is picked up on the next run (idempotent upsert).
DEFAULT_LOOKBACK_DAYS = 10
EOD_COLS = (
    "security_id",
    "price_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
)


class _DryRunRollback(Exception):
    pass


@dataclass
class SyncReport:
    dry_run: bool
    since: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"dry_run": self.dry_run, "since": self.since, **self.counts}


def _mongo_db(mongo_url: str, mongo_db: str | None):
    from pymongo import MongoClient  # local import: only the sync job needs it

    client = MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=10_000,
        socketTimeoutMS=300_000,
        tz_aware=False,
    )
    # v1 reads MONGODB_DB (settings.mongodb_db); fall back to the URL's db, then 'stocks'.
    if mongo_db:
        return client, client[mongo_db]
    return client, client.get_default_database(default="stocks")


async def _default_since(conn: asyncpg.Connection) -> date | None:
    last = await conn.fetchval(
        "SELECT max(price_date) FROM market.eod_prices WHERE source = $1 "
        "AND price_date >= DATE '2000-01-01'",
        EOD_SOURCE,
    )
    return (last - timedelta(days=DEFAULT_LOOKBACK_DAYS)) if last else None


async def _security_map(
    conn, mdb, all_universe: bool, report: SyncReport
) -> dict[str, list[int]]:
    if all_universe:
        v1_syms = await asyncio.to_thread(mdb.orb_candles_1d.distinct, "sym")
        res = await conn.fetch(
            "INSERT INTO market.securities (symbol, exchange) "
            "SELECT s, 'NSE' FROM unnest($1::text[]) s "
            "ON CONFLICT (symbol, exchange) DO NOTHING RETURNING security_id",
            sorted({str(s).upper() for s in v1_syms if s}),
        )
        report.counts["securities_inserted"] = len(res)
    rows = await conn.fetch(
        "SELECT symbol, security_id FROM market.securities WHERE exchange = 'NSE'"
    )
    aliases = await conn.fetch(
        "SELECT old_symbol, new_symbol FROM market.symbol_aliases"
    )
    report.counts["nse_securities"] = len(rows)
    report.counts["bse_only_securities_unpriced"] = await conn.fetchval(
        "SELECT count(*) FROM market.securities b WHERE b.exchange = 'BSE' AND NOT EXISTS "
        "(SELECT 1 FROM market.securities n WHERE n.exchange = 'NSE' AND n.symbol = b.symbol)"
    )
    return map_symbols_to_securities(
        {r["symbol"].upper(): r["security_id"] for r in rows},
        [(a["old_symbol"].upper(), a["new_symbol"].upper()) for a in aliases],
    )


def _fetch_daily_batch(mdb, syms: list[str], since: date | None) -> list[dict]:
    rows_expr: Any = "$rows"
    if since is not None:
        rows_expr = {
            "$filter": {
                "input": "$rows",
                "as": "r",
                "cond": {"$gte": ["$$r.date", (since - timedelta(days=7)).isoformat()]},
            }
        }
    pipeline = [
        {"$match": {"sym": {"$in": syms}}},
        {"$project": {"_id": 0, "sym": 1, "rows": rows_expr}},
    ]
    return list(mdb.orb_candles_1d.aggregate(pipeline, allowDiskUse=True))


async def _copy_and_upsert(
    conn, records: list[tuple], replace_other_sources: bool
) -> Counter:
    out: Counter = Counter()
    if not records:
        return out
    await conn.execute("TRUNCATE stg_eod")
    await conn.copy_records_to_table("stg_eod", records=records, columns=list(EOD_COLS))
    guard = None if replace_other_sources else f"t.source = '{EOD_SOURCE}'"
    sql = build_upsert_sql(
        "market.eod_prices",
        "stg_eod",
        EOD_COLS,
        ("security_id", "price_date"),
        ("open", "high", "low", "close", "volume", "source"),
        guard,
    )
    for r in await conn.fetch(sql):
        out["eod_inserted" if r["inserted"] else "eod_updated"] += 1
    out["eod_staged"] = len(records)
    return out


async def sync_eod_prices(
    conn, mdb, sym_map, since, replace_other_sources, report
) -> None:
    await conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS stg_eod (LIKE market.eod_prices INCLUDING DEFAULTS) ON COMMIT DROP"
    )
    stats, counts = TransformStats(), Counter()
    syms = sorted(sym_map)
    found = 0
    for i in range(0, len(syms), BATCH_SYMBOLS):
        docs = await asyncio.to_thread(
            _fetch_daily_batch, mdb, syms[i : i + BATCH_SYMBOLS], since
        )
        found += len(docs)
        records: list[tuple] = []
        for doc in docs:
            rows, st = transform_daily_rows(doc.get("rows") or [], since)
            stats.merge(st)
            for sid in sym_map.get(str(doc["sym"]).upper(), []):
                records.extend(
                    (
                        sid,
                        r.price_date,
                        r.open,
                        r.high,
                        r.low,
                        r.close,
                        r.volume,
                        EOD_SOURCE,
                    )
                    for r in rows
                )
        counts.update(await _copy_and_upsert(conn, records, replace_other_sources))
    staged = counts.get("eod_staged", 0)
    report.counts.update(
        securities_mapped=len(syms),
        v1_symbols_found=found,
        eod_rows_accepted=stats.accepted,
        eod_rejects=dict(stats.rejects),
        eod_unchanged_or_other_source=staged
        - counts.get("eod_inserted", 0)
        - counts.get("eod_updated", 0),
        **counts,
    )


async def _record_job(
    conn, report: SyncReport, status: str, error: str | None = None
) -> None:
    await conn.execute(
        "INSERT INTO ops.job_runs (job, finished_at, status, rows_in, rows_out, error, meta) "
        "VALUES ('v1_market_sync', now(), $1, $2, $3, $4, $5::jsonb)",
        status,
        report.counts.get("eod_rows_accepted"),
        report.counts.get("eod_inserted", 0) + report.counts.get("eod_updated", 0),
        error,
        json.dumps(report.as_dict(), default=str),
    )


async def run_sync(
    pg_dsn: str,
    mongo_url: str,
    *,
    since: date | None = None,
    all_universe: bool = False,
    dry_run: bool = False,
    replace_other_sources: bool = False,
    mongo_db: str | None = None,
) -> SyncReport:
    report = SyncReport(dry_run=dry_run)
    client, mdb = _mongo_db(mongo_url, mongo_db)
    conn = await asyncpg.connect(pg_dsn, command_timeout=900, timeout=15)
    try:
        since = since or await _default_since(conn)
        report.since = since.isoformat() if since else "full-history"
        try:
            async with conn.transaction():
                sym_map = await _security_map(conn, mdb, all_universe, report)
                await sync_eod_prices(
                    conn, mdb, sym_map, since, replace_other_sources, report
                )
                await sync_calendar(conn, mdb, since, report)
                await sync_benchmarks(conn, mdb, report)
                if dry_run:
                    raise _DryRunRollback()
                await _record_job(conn, report, "OK")
        except _DryRunRollback:
            logger.info("dry-run: transaction rolled back")
        except Exception as exc:
            if not dry_run:
                await _record_job(conn, report, "FAILED", type(exc).__name__)
            raise
    finally:
        await conn.close()
        client.close()
    return report
