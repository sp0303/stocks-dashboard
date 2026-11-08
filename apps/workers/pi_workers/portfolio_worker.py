"""Portfolio Worker (:8202): precomputes portfolio.* from ledger.trades + market.eod_prices.

HLD D1 (precompute, don't compute on request) and R5 (one engine; manager
figures are sums of client figures). Math lives in pi_core via
``portfolio_compute``; this module only reads inputs and writes outputs.

    python -m pi_workers.portfolio_worker --recompute-all   # one-shot (systemd timer)
    python -m pi_workers.portfolio_worker                   # health/admin server
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

if __package__ in (None, ""):  # allow `python pi_workers/portfolio_worker.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import uvicorn
from fastapi import FastAPI

from pi_workers.analytics_compute import recompute_client_analytics_safe
from pi_workers.portfolio_compute import (
    ENGINE_VERSION,
    actions_from_rows,
    build_price_lookup,
    compute_client,
    trades_from_rows,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pi_workers.portfolio")

PORT = int(os.environ.get("PORT", "8202"))
IST = timezone(timedelta(hours=5, minutes=30))
DAILY_COLS = [
    "client_id",
    "as_of",
    "market_value",
    "open_cost",
    "net_invested",
    "realized_pnl",
    "twr_base",
    "day_return",
    "nav",
    "unpriced_cost",
    "engine_version",
]

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL is not set (portfolio-worker needs the pi_worker role)"
        )
    return dsn


async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_dsn(), min_size=1, max_size=3, command_timeout=300
        )
    return _pool


async def _clear_client(conn: asyncpg.Connection, client_id: UUID) -> None:
    for table in (
        "client_overview",
        "client_metrics",
        "client_daily",
        "positions_latest",
    ):
        await conn.execute(
            f"DELETE FROM portfolio.{table} WHERE client_id = $1", client_id
        )


async def _load_inputs(conn: asyncpg.Connection, client_id: UUID):
    trade_rows = await conn.fetch(
        """
        SELECT trade_id, trade_date, symbol, exchange, trade_type, quantity, price,
               charges, segment, extra
        FROM ledger.trades
        WHERE client_id = $1 AND deleted_at IS NULL
        ORDER BY trade_date, trade_id
        """,
        client_id,
    )
    if not trade_rows:
        return None, None, None
    symbols = sorted({r["symbol"] for r in trade_rows})
    first = min(r["trade_date"] for r in trade_rows)
    ca_rows = await conn.fetch(
        "SELECT symbol, type, ex_date, qty_multiplier FROM ledger.corporate_actions "
        "WHERE symbol = ANY($1::text[]) ORDER BY ex_date",
        symbols,
    )
    px_rows = await conn.fetch(
        """
        SELECT s.symbol, s.exchange, e.price_date, e.close::float8 AS close
        FROM market.eod_prices e JOIN market.securities s USING (security_id)
        WHERE s.symbol = ANY($1::text[]) AND e.price_date >= $2::date - 30
        """,
        symbols,
        first,
    )
    prices = [
        (r["symbol"], r["exchange"], r["price_date"], r["close"]) for r in px_rows
    ]
    return trade_rows, ca_rows, prices


async def recompute_client_portfolio(
    conn: asyncpg.Connection,
    client_id: UUID,
    today,
    closed_days: set,
    sec_ids: dict[tuple[str, str], int],
) -> bool:
    trade_rows, ca_rows, prices = await _load_inputs(conn, client_id)
    if trade_rows is None:
        async with conn.transaction():
            await _clear_client(conn, client_id)
        await recompute_client_analytics_safe(conn, client_id, today, closed_days)
        return True
    res = compute_client(
        trades_from_rows(trade_rows),
        actions_from_rows(ca_rows),
        build_price_lookup(prices),
        today,
        closed_days,
    )
    positions = [
        (sec_ids.get((s, x)), q, a, inv, d) for s, x, q, a, inv, d in res.positions
    ]
    skipped = sum(1 for p in positions if p[0] is None)
    async with conn.transaction():
        await _clear_client(conn, client_id)
        await conn.execute(
            "INSERT INTO portfolio.client_overview (client_id, as_of, payload, engine_version) "
            "VALUES ($1, $2, $3::jsonb, $4)",
            client_id,
            today,
            json.dumps(res.overview),
            ENGINE_VERSION,
        )
        await conn.execute(
            "INSERT INTO portfolio.client_metrics (client_id, as_of, obs, payload, engine_version) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            client_id,
            today,
            res.obs,
            json.dumps(res.metrics),
            ENGINE_VERSION,
        )
        await conn.copy_records_to_table(
            "client_daily",
            schema_name="portfolio",
            columns=DAILY_COLS,
            records=[(client_id, *row, ENGINE_VERSION) for row in res.daily],
        )
        await conn.executemany(
            "INSERT INTO portfolio.positions_latest "
            "(client_id, security_id, quantity, avg_cost, invested, entry_date) VALUES ($1,$2,$3,$4,$5,$6)",
            [(client_id, *p) for p in positions if p[0] is not None],
        )
    logger.info(
        "client recomputed: daily=%d positions=%d unpriced_security_skipped=%d warnings=%d",
        len(res.daily),
        len(positions) - skipped,
        skipped,
        len(res.warnings),
    )
    await recompute_client_analytics_safe(conn, client_id, today, closed_days)
    return True


async def recompute_manager_daily(conn: asyncpg.Connection) -> int:
    """R5: manager series = SUM of its active clients' client_daily rows. Chart P&L = realised + unrealised (R7)."""
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM portfolio.manager_daily WHERE as_of >= DATE '1990-01-01'"
        )
        status = await conn.execute(
            """
            INSERT INTO portfolio.manager_daily
                (manager_id, as_of, market_value, open_cost, net_invested, realized_pnl, pnl)
            SELECT c.manager_id, d.as_of, sum(d.market_value), sum(d.open_cost),
                   sum(d.net_invested), sum(d.realized_pnl),
                   sum(d.realized_pnl + d.market_value - d.open_cost)
            FROM portfolio.client_daily d
            JOIN core.clients c USING (client_id)
            WHERE c.status = 'ACTIVE' AND d.as_of >= DATE '1990-01-01'
            GROUP BY c.manager_id, d.as_of
            """
        )
    return int(status.split()[-1])


async def _load_context(conn: asyncpg.Connection, today) -> tuple[set, dict]:
    """Closed trading days up to `today` and the (symbol, exchange) -> security_id map."""
    closed = {
        r["cal_date"]
        for r in await conn.fetch(
            "SELECT cal_date FROM market.trading_calendar WHERE NOT is_open AND cal_date <= $1",
            today,
        )
    }
    sec_ids = {
        (r["symbol"], r["exchange"]): r["security_id"]
        for r in await conn.fetch("SELECT symbol, exchange, security_id FROM market.securities")
    }
    return closed, sec_ids


async def recompute_single_client(conn: asyncpg.Connection, client_id: UUID) -> bool:
    """One client's books after an upload or manual trade, plus the manager roll-up (R5).

    Takes (conn, client_id) — the signature the ingest and ledger paths call with.
    """
    today = datetime.now(IST).date()
    closed, sec_ids = await _load_context(conn, today)
    ok = await recompute_client_portfolio(conn, client_id, today, closed, sec_ids)
    await recompute_manager_daily(conn)
    return ok


async def recompute_all_clients() -> int:
    """Batch recompute for all active clients, then the manager roll-up."""
    pool = await get_db_pool()
    today = datetime.now(IST).date()
    async with pool.acquire() as conn:
        closed, sec_ids = await _load_context(conn, today)
        clients = await conn.fetch(
            "SELECT client_id FROM core.clients WHERE status = 'ACTIVE'"
        )
        ok = failed = 0
        for r in clients:
            try:
                await recompute_client_portfolio(
                    conn, r["client_id"], today, closed, sec_ids
                )
                ok += 1
            except Exception:  # one bad book must not stop the others
                failed += 1
                logger.exception(
                    "client recompute failed (client index %d)", ok + failed
                )
        rows = await recompute_manager_daily(conn)
        await conn.execute(
            "INSERT INTO ops.job_runs (job, finished_at, status, rows_in, rows_out, meta) "
            "VALUES ('portfolio_recompute', now(), $1, $2, $3, $4::jsonb)",
            "OK" if failed == 0 else "FAILED",
            len(clients),
            ok,
            json.dumps(
                {
                    "failed": failed,
                    "manager_daily_rows": rows,
                    "as_of": today.isoformat(),
                }
            ),
        )
    logger.info(
        "recompute done: ok=%d failed=%d manager_daily_rows=%d", ok, failed, rows
    )
    return ok if failed == 0 else -failed


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f"Starting portfolio-worker on port {PORT}...")
    await get_db_pool()
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="Portfolio Intelligence - Portfolio Worker", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "worker": "portfolio-worker", "port": PORT}


@app.post("/recompute/all")
async def trigger_recompute_all():
    count = await recompute_all_clients()
    return {"status": "ok" if count >= 0 else "partial", "clients_recomputed": count}


if __name__ == "__main__":
    if "--recompute-all" in sys.argv:
        sys.exit(0 if asyncio.run(recompute_all_clients()) >= 0 else 1)
    uvicorn.run(app, host="127.0.0.1", port=PORT)
