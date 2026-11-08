"""AsyncPG database connection pool management."""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional
import asyncpg

from pi_api.settings import settings

logger = logging.getLogger("pi_api.db")

_pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> asyncpg.Pool:
    """Initializes asyncpg connection pool."""
    global _pool
    loop_closed = _pool is not None and getattr(_pool, "_loop", None) is not None and _pool._loop.is_closed()
    if _pool is None or loop_closed:
        logger.info("Connecting to PostgreSQL database pool...")
        db_url = settings.DATABASE_URL
        _pool = await asyncpg.create_pool(
            dsn=db_url,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            command_timeout=15.0,
        )
    return _pool


async def close_db_pool() -> None:
    """Closes asyncpg connection pool."""
    global _pool
    if _pool is not None:
        logger.info("Closing PostgreSQL database pool...")
        try:
            if not getattr(_pool, "_loop", None) or not _pool._loop.is_closed():
                await _pool.close()
        except Exception:
            pass
        _pool = None


async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """FastAPI dependency for obtaining a connection from the pool."""
    global _pool
    loop_closed = _pool is not None and getattr(_pool, "_loop", None) is not None and _pool._loop.is_closed()
    if _pool is None or loop_closed:
        _pool = await init_db_pool()
    async with _pool.acquire() as conn:
        yield conn
