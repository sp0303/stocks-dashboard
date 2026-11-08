"""Redis Streams event backbone adhering to AGENTS.md Rule 6 and 7."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
import redis.asyncio as redis

from pi_api.settings import settings

logger = logging.getLogger("pi_api.events")

PORTFOLIO_EVENTS_STREAM = "stream:portfolio:events"
PORTFOLIO_EVENTS_DLQ = "stream:portfolio:dlq"

_redis_streams_client: Optional[redis.Redis] = None


def get_redis_streams() -> redis.Redis:
    global _redis_streams_client
    if _redis_streams_client is None:
        _redis_streams_client = redis.from_url(
            settings.REDIS_STREAMS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return _redis_streams_client


async def publish_event(
    stream: str,
    event_type: str,
    data: Dict[str, Any],
    event_id: Optional[str] = None,
) -> str:
    """Publishes an idempotent event to a Redis Stream (Rule 7)."""
    r = get_redis_streams()
    eid = event_id or str(uuid.uuid4())
    payload = {
        "event_id": eid,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": json.dumps(data),
    }
    msg_id = await r.xadd(stream, payload)
    logger.info(f"Published event {event_type} ({eid}) to {stream} as {msg_id}")
    return msg_id
