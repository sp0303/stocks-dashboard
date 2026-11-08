"""Quote Poller Worker (:8201): Batch-polls quotes and writes to Redis cache (Decision D3).

STATUS: STUB. No live quote provider is wired in v2 yet (no Yahoo/Angel path
exists in apps/ or libs/). ``poll_once`` is a safe no-op that only logs, so the
API falls back to the latest EOD close, flagged ``is_stale`` (R6). When a
provider is added it must be called only from here (AGENTS §3.2), rate-limited,
and it must not log in to Angel (one production identity, AGENTS §10).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional

import asyncpg
from fastapi import FastAPI
import redis.asyncio as redis
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_workers.quotes")

PORT = int(os.environ.get("PORT", 8201))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
REDIS_CACHE_URL = os.environ.get("REDIS_CACHE_URL", "redis://127.0.0.1:6390/0")

_pool: Optional[asyncpg.Pool] = None
_redis: Optional[redis.Redis] = None


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=3)
    return _pool


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_CACHE_URL, decode_responses=True)
    return _redis


async def poll_held_symbols() -> List[Dict]:
    """Gets distinct held symbols across all portfolios."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT s.symbol, s.exchange
            FROM portfolio.positions_latest p
            JOIN market.securities s ON p.security_id = s.security_id
            WHERE p.quantity > 0;
            """
        )
        return [{"symbol": r["symbol"], "exchange": r["exchange"]} for r in rows]


async def update_cached_quote(symbol: str, exchange: str, price: float):
    """Writes quote to Redis cache: q:{exch}:{sym}."""
    r = get_redis()
    key = f"q:{exchange.upper()}:{symbol.upper()}"
    payload = {
        "symbol": symbol,
        "exchange": exchange,
        "price": price,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    await r.setex(key, 60, json.dumps(payload))


async def poll_once() -> int:
    """No-op until a provider is wired: logs and writes nothing. Returns quotes written (0)."""
    logger.info("quote-poller stub: no live provider configured; API serves EOD close (is_stale=True)")
    return 0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting quote-poller on port {PORT}...")
    await get_db_pool()
    yield
    global _pool, _redis
    if _pool:
        await _pool.close()
    if _redis:
        await _redis.close()


app = FastAPI(title="Portfolio Intelligence - Quote Poller", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "worker": "quote-poller", "port": PORT}


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        asyncio.run(poll_once())
    else:
        uvicorn.run(app, host="127.0.0.1", port=PORT)
