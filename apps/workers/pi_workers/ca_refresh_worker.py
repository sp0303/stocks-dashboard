"""Corporate-actions refresh worker: consumes ``stream:ca:refresh``, fetches NSE, upserts.

The API only publishes ``ca.refresh.requested`` ({scope: held|all}); NSE is called here
only (AGENTS §3.2/§3.6). Handlers are idempotent: dedupe on ``event_id`` and the upsert
is keyed on ``ledger.corporate_actions.key``. Failures retry; after 5 tries the message
goes to ``stream:ca:refresh.dlq`` (§3.7). NSE is paced (~1 request / 0.6 s + jitter).

    python -m pi_workers.ca_refresh_worker            # run the consumer loop
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("pi_workers.ca_refresh")
IST = timezone(timedelta(hours=5, minutes=30))

STREAM = "stream:ca:refresh"
DLQ = STREAM + ".dlq"
GROUP = "ca-refresh"
MAX_TRIES = 5
JOB = "ca_refresh"
NSE_HOME = "https://www.nseindia.com"
NSE_CA = NSE_HOME + "/api/corporates-corporateActions"
EQUITY_L = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
PAUSE_S = 0.6
BATCH = 25
FROM_DATE = "01-01-2020"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME + "/companies-listing/corporate-filings-actions",
}
from pi_api.modules.admin.ca_parse import normalize, parse_equity_list


# ----------------------------------------------------------------- NSE I/O (paced, retried)
async def _get(
    client: Any, url: str, params: dict | None = None, tries: int = 3
) -> Any:
    """GET is idempotent: retry 429/5xx/network with jittered exponential backoff (§3.11)."""
    for attempt in range(tries):
        try:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r
            if r.status_code not in (429, 500, 502, 503, 504):
                logger.warning("NSE %s -> HTTP %s", url, r.status_code)
                return None
        except Exception as exc:  # noqa: BLE001 — network errors are retried, then logged
            logger.warning("NSE %s failed (%s/%s): %s", url, attempt + 1, tries, exc)
        await asyncio.sleep((2**attempt) + random.uniform(0, 0.5))
    return None


async def fetch_symbol(client: Any, symbol: str, to_date: str) -> list[dict[str, Any]]:
    r = await _get(
        client,
        NSE_CA,
        {
            "index": "equities",
            "symbol": symbol,
            "from_date": FROM_DATE,
            "to_date": to_date,
        },
    )
    if r is None:
        return []
    try:
        raw = r.json()
    except ValueError:
        return []
    recs = raw if isinstance(raw, list) else raw.get("data", [])
    return [n for n in (normalize(x) for x in recs) if n]


# ----------------------------------------------------------------- persistence
_UPSERT = """
    INSERT INTO ledger.corporate_actions
        (key, isin, symbol, ex_date, type, qty_multiplier, amount_per_share, subject, source)
    SELECT DISTINCT ON (key) key, isin, symbol, ex_date, type, qty_multiplier, amount_per_share, subject, source
    FROM stg_ca ORDER BY key
    ON CONFLICT (key) DO UPDATE SET
        isin = EXCLUDED.isin, qty_multiplier = EXCLUDED.qty_multiplier,
        amount_per_share = EXCLUDED.amount_per_share, subject = EXCLUDED.subject, fetched_at = now()
"""
_COLS = (
    "key",
    "isin",
    "symbol",
    "ex_date",
    "type",
    "qty_multiplier",
    "amount_per_share",
    "subject",
    "source",
)


async def upsert_actions(conn: Any, rows: list[dict[str, Any]]) -> int:
    """COPY -> temp staging -> upsert on key (§3.8). Re-running the same rows is a no-op change."""
    if not rows:
        return 0
    async with conn.transaction():
        await conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS stg_ca (LIKE ledger.corporate_actions INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        await conn.copy_records_to_table(
            "stg_ca",
            records=[tuple(r[c] for c in _COLS) for r in rows],
            columns=list(_COLS),
        )
        status = await conn.execute(_UPSERT)
    return int(status.split()[-1])


async def held_symbols(conn: Any) -> list[str]:
    rows = await conn.fetch(
        "SELECT DISTINCT symbol FROM ledger.trades WHERE deleted_at IS NULL AND exchange = 'NSE' "
        "AND trade_date >= DATE '1990-01-01' ORDER BY symbol"
    )
    return [r["symbol"] for r in rows]


# ----------------------------------------------------------------- handler
Fetcher = Callable[[str], Awaitable[list[dict[str, Any]]]]


async def refresh(
    conn: Any, symbols: list[str], fetch: Fetcher, pause: float = PAUSE_S
) -> dict[str, int]:
    """Fetch every symbol (paced) and persist in batches so a long 'all' run survives a crash."""
    pending: list[dict[str, Any]] = []
    stored = fetched = 0
    for i, sym in enumerate(symbols):
        recs = await fetch(sym)
        fetched += len(recs)
        pending.extend(recs)
        if (i + 1) % BATCH == 0 or i == len(symbols) - 1:
            stored += await upsert_actions(conn, pending)
            pending = []
        if pause and i < len(symbols) - 1:
            await asyncio.sleep(pause + random.uniform(0, pause / 2))
    return {"symbols": len(symbols), "fetched": fetched, "stored": stored}


async def handle_event(
    conn: Any,
    data: dict[str, Any],
    fetch: Fetcher,
    list_all: Callable[[], Awaitable[list[str]]],
) -> dict[str, Any]:
    scope = data.get("scope", "held")
    if scope not in ("held", "all"):
        raise ValueError(f"unknown scope {scope!r}")
    symbols = await list_all() if scope == "all" else await held_symbols(conn)
    if scope == "all" and not symbols:
        symbols = await held_symbols(conn)  # EQUITY_L unavailable: fall back, as v1 did
    run_id = await conn.fetchval(
        "INSERT INTO ops.job_runs (job, status, rows_in, meta) VALUES ($1, 'RUNNING', $2, $3::jsonb) RETURNING run_id",
        JOB,
        len(symbols),
        json.dumps({"scope": scope, "event_id": data.get("event_id")}),
    )
    try:
        res = await refresh(conn, symbols, fetch)
    except Exception as exc:
        await conn.execute(
            "UPDATE ops.job_runs SET status='FAILED', finished_at=now(), error=$2 WHERE run_id=$1",
            run_id,
            str(exc)[:500],
        )
        raise
    await conn.execute(
        "UPDATE ops.job_runs SET status='OK', finished_at=now(), rows_out=$2, meta = meta || $3::jsonb WHERE run_id=$1",
        run_id,
        res["stored"],
        json.dumps(res),
    )
    return {"scope": scope, **res}


# ----------------------------------------------------------------- stream consumer
async def process_message(
    redis: Any,
    conn: Any,
    msg_id: str,
    fields: dict[str, str],
    handler: Callable[..., Awaitable[Any]],
) -> str:
    """Returns 'done' | 'duplicate' | 'retry' | 'dlq'. Idempotent on event_id."""
    eid = fields.get("event_id") or msg_id
    if await redis.exists(f"ca:done:{eid}"):
        await redis.xack(STREAM, GROUP, msg_id)
        return "duplicate"
    tries = await redis.incr(f"ca:tries:{eid}")
    await redis.expire(f"ca:tries:{eid}", 7 * 86400)
    try:
        data = json.loads(fields.get("data") or "{}")
        data["event_id"] = eid
        await handler(conn, data)
    except Exception as exc:
        logger.exception("ca refresh %s failed (try %s/%s)", eid, tries, MAX_TRIES)
        if tries >= MAX_TRIES:
            await redis.xadd(
                DLQ,
                {
                    **fields,
                    "error": str(exc)[:500],
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await redis.xack(STREAM, GROUP, msg_id)
            return "dlq"
        return "retry"  # stays pending; re-claimed after the idle timeout
    await redis.set(f"ca:done:{eid}", "1", ex=30 * 86400)
    await redis.xack(STREAM, GROUP, msg_id)
    return "done"


async def run_consumer() -> None:  # pragma: no cover — needs Redis, Postgres and NSE
    import asyncpg
    import httpx
    import redis.asyncio as aioredis

    r = aioredis.from_url(
        os.environ.get("REDIS_STREAMS_URL", "redis://127.0.0.1:6391/0"),
        decode_responses=True,
        socket_timeout=10,
    )
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as exc:  # noqa: BLE001 — BUSYGROUP: already exists
        logger.debug("xgroup_create: %s", exc)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], command_timeout=120)
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=20, follow_redirects=True
    ) as http:
        await _get(http, NSE_HOME, tries=1)  # prime cookies like a browser session
        today = datetime.now(IST).strftime("%d-%m-%Y")

        async def list_all() -> list[str]:
            resp = await _get(http, EQUITY_L)
            return parse_equity_list(resp.text) if resp is not None else []

        async def handler(c: Any, data: dict[str, Any]) -> Any:
            return await handle_event(
                c, data, lambda s: fetch_symbol(http, s, today), list_all
            )

        while True:
            _, claimed, _ = await r.xautoclaim(
                STREAM, GROUP, "ca-1", min_idle_time=120_000, count=1
            )
            batch = (
                [(STREAM, claimed)]
                if claimed
                else await r.xreadgroup(
                    GROUP, "ca-1", {STREAM: ">"}, count=1, block=5000
                )
            )
            for _, msgs in batch or []:
                for msg_id, fields in msgs:
                    await process_message(r, conn, msg_id, fields, handler)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_consumer())
