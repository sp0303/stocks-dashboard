"""Versioned cache helper adhering to LLD-cache and AGENTS.md Rule 10."""

from __future__ import annotations

import inspect
import logging
from typing import Callable, Optional
import redis.asyncio as redis

from pi_api.settings import settings

logger = logging.getLogger("pi_api.cache")

_redis_client: Optional[redis.Redis] = None


def get_redis_cache() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_CACHE_URL,
            encoding="utf-8",
            decode_responses=False,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_client


async def cached_bytes(
    key: str,
    ttl_seconds: int,
    fetch_fn: Callable[[], bytes | str],
) -> bytes:
    """Reads cached bytes from Redis; falls through to fetch_fn on miss or failure (Rule 10)."""
    try:
        r = get_redis_cache()
        cached = await r.get(key)
        if cached is not None:
            return cached if isinstance(cached, bytes) else cached.encode("utf-8")
    except Exception as e:
        logger.warning(f"Redis cache read fall-through on key {key}: {e}")

    # Fetch fresh value
    result = fetch_fn()
    if inspect.isawaitable(result):  # async fetch fns return a coroutine
        result = await result
    data_bytes = result if isinstance(result, bytes) else str(result).encode("utf-8")

    try:
        r = get_redis_cache()
        await r.setex(key, ttl_seconds, data_bytes)
    except Exception as e:
        logger.warning(f"Redis cache write failure on key {key}: {e}")

    return data_bytes
