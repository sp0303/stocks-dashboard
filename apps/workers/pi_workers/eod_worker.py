"""EOD Worker (:8203): end-of-day prices, trading calendar and benchmarks.

Interim source (until the v2 ORB feed owns market.candles_1m): v1's Mongo
``orb_candles_1d`` / ``benchmark_prices``, synced by ``v1_sync_db.run_sync``.
No provider calls and no broker login here: it only reads v1's stored rows.

    python -m pi_workers.eod_worker --sync-v1 [--since YYYY-MM-DD] [--dry-run]   # one-shot
    python -m pi_workers.eod_worker                                              # health server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):  # allow `python pi_workers/eod_worker.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import uvicorn
from fastapi import FastAPI

from pi_workers.v1_sync import EOD_SOURCE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_workers.eod")

IST = timezone(timedelta(hours=5, minutes=30))
PORT = int(os.environ.get("PORT", "8203"))

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    dsn = os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL (or PG_DSN) is not set")
    return dsn


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_dsn(), min_size=1, max_size=3, command_timeout=300
        )
    return _pool


async def rollup_orb_to_eod_prices(business_date: date) -> int:
    """Future path: roll market.candles_1m (paise) into market.eod_prices (rupees) for one date."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO market.eod_prices (security_id, price_date, open, high, low, close, volume, source)
            SELECT security_id, $1::date,
                   (array_agg(o ORDER BY ts ASC))[1]::numeric / 100.0,
                   max(h)::numeric / 100.0,
                   min(l)::numeric / 100.0,
                   (array_agg(c ORDER BY ts DESC))[1]::numeric / 100.0,
                   sum(v)::bigint,
                   $2
            FROM market.candles_1m
            WHERE ts >= $1::date AND ts < ($1::date + interval '1 day') AND NOT synthetic
            GROUP BY security_id
            ON CONFLICT (security_id, price_date) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
            WHERE market.eod_prices.source = EXCLUDED.source
            """,
            business_date,
            EOD_SOURCE,
        )
        logger.info("EOD candles_1m rollup for %s: %s", business_date, result)
        return int(result.split()[-1])


async def sync_v1(since: date | None, dry_run: bool) -> dict:
    from pi_workers.v1_sync_db import run_sync

    mongo_url = os.environ.get("MONGODB_URL")
    if not mongo_url:
        raise RuntimeError("MONGODB_URL is not set")
    report = await run_sync(
        _dsn(),
        mongo_url,
        since=since,
        dry_run=dry_run,
        mongo_db=os.environ.get("MONGODB_DB"),
    )
    return report.as_dict()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting eod-worker on port {PORT}...")
    await get_db_pool()
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="Portfolio Intelligence - EOD Worker", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "worker": "eod-worker", "port": PORT}


@app.post("/eod/rollup")
async def trigger_rollup(business_date: date | None = None):
    d = business_date or datetime.now(IST).date()
    count = await rollup_orb_to_eod_prices(d)
    return {"status": "ok", "date": d, "rolled_up": count}


def _cli() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync-v1", action="store_true")
    ap.add_argument("--since", type=date.fromisoformat)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.sync_v1:
        uvicorn.run(app, host="127.0.0.1", port=PORT)
        return 0
    report = asyncio.run(sync_v1(args.since, args.dry_run))
    print(json.dumps(report, default=str, sort_keys=True))  # counts only
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
