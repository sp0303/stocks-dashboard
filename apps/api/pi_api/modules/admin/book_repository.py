"""Manager-book SQL: roster, per-symbol positions, series, closed trades.

Reads precomputed rows only (portfolio.* is written by portfolio-worker; HLD D1).
Every time-series query carries a date predicate (AGENTS §3.9). Only live, ACTIVE clients.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

_LIVE = "c.manager_id = $1 AND c.status = 'ACTIVE' AND c.deleted_at IS NULL"

_ROSTER = f"""
    SELECT c.client_id, c.name, c.client_code, c.broker, c.status, co.as_of, co.payload,
           (SELECT COUNT(*) FROM ledger.trades t
             WHERE t.client_id = c.client_id AND t.deleted_at IS NULL) AS trade_count
    FROM core.clients c
    LEFT JOIN portfolio.client_overview co ON co.client_id = c.client_id
    WHERE {_LIVE}
    ORDER BY c.name
"""

# One row per (client, symbol) with the latest as-traded close (R6: NULL = unpriced).
_POSITIONS = f"""
    SELECT p.client_id, s.symbol, s.exchange,
           p.quantity::float8 AS quantity, p.invested::float8 AS invested,
           eod.close::float8 AS price
    FROM portfolio.positions_latest p
    JOIN core.clients c ON c.client_id = p.client_id
    JOIN market.securities s ON s.security_id = p.security_id
    LEFT JOIN LATERAL (
        SELECT e.close FROM market.eod_prices e
        WHERE e.security_id = p.security_id AND e.price_date >= CURRENT_DATE - 30
        ORDER BY e.price_date DESC LIMIT 1
    ) eod ON true
    WHERE {_LIVE} AND p.quantity > 0
"""

_TRADE_COUNTS = f"""
    SELECT t.symbol, COUNT(*) AS n
    FROM ledger.trades t
    JOIN core.clients c ON c.client_id = t.client_id
    WHERE {_LIVE} AND t.deleted_at IS NULL AND t.trade_date >= $2
    GROUP BY t.symbol
"""

_BOOK_SERIES = """
    SELECT as_of, market_value::float8, open_cost::float8, net_invested::float8,
           realized_pnl::float8, pnl::float8
    FROM portfolio.manager_daily
    WHERE manager_id = $1 AND as_of >= $2
    ORDER BY as_of
"""

_BENCH_VALUES = """
    SELECT b.code, b.label, v.value_date, v.value::float8 AS value
    FROM market.benchmark_values v
    JOIN market.benchmarks b ON b.benchmark_id = v.benchmark_id
    WHERE b.code = ANY($1::text[]) AND b.is_active AND v.value_date >= $2
    ORDER BY b.code, v.value_date
"""

_CLIENT_NAV = f"""
    SELECT d.client_id, c.name, d.as_of, d.nav
    FROM portfolio.client_daily d
    JOIN core.clients c ON c.client_id = d.client_id
    WHERE {_LIVE} AND d.as_of >= $2
    ORDER BY d.client_id, d.as_of
"""

_CLOSED = f"""
    SELECT r.client_id, c.name AS client_name, c.client_code, r.symbol,
           r.buy_date, r.sell_date, r.quantity::float8 AS quantity,
           r.buy_price::float8 AS buy_price, r.sell_price::float8 AS sell_price,
           r.pnl::float8 AS pnl, r.days
    FROM portfolio.round_trips r
    JOIN core.clients c ON c.client_id = r.client_id
    WHERE {_LIVE} AND r.sell_date >= $2
    ORDER BY r.sell_date DESC, c.name, r.symbol
    LIMIT $3
"""


def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in records]


class BookRepository:
    @staticmethod
    async def roster(
        conn: asyncpg.Connection, manager_id: UUID
    ) -> list[dict[str, Any]]:
        return _rows(await conn.fetch(_ROSTER, manager_id))

    @staticmethod
    async def positions(
        conn: asyncpg.Connection, manager_id: UUID
    ) -> list[dict[str, Any]]:
        return _rows(await conn.fetch(_POSITIONS, manager_id))

    @staticmethod
    async def trade_counts(
        conn: asyncpg.Connection, manager_id: UUID, since: date
    ) -> dict[str, int]:
        return {
            r["symbol"]: int(r["n"])
            for r in await conn.fetch(_TRADE_COUNTS, manager_id, since)
        }

    @staticmethod
    async def book_series(
        conn: asyncpg.Connection, manager_id: UUID, since: date
    ) -> list[dict[str, Any]]:
        return _rows(await conn.fetch(_BOOK_SERIES, manager_id, since))

    @staticmethod
    async def active_benchmark_codes(conn: asyncpg.Connection) -> list[str]:
        rows = await conn.fetch(
            "SELECT code FROM market.benchmarks WHERE is_active ORDER BY benchmark_id"
        )
        return [r["code"] for r in rows]

    @staticmethod
    async def benchmark_values(
        conn: asyncpg.Connection, codes: list[str], since: date
    ) -> list[dict[str, Any]]:
        return _rows(await conn.fetch(_BENCH_VALUES, codes, since))

    @staticmethod
    async def client_navs(
        conn: asyncpg.Connection, manager_id: UUID, since: date
    ) -> list[dict[str, Any]]:
        return _rows(await conn.fetch(_CLIENT_NAV, manager_id, since))

    @staticmethod
    async def closed_trades(
        conn: asyncpg.Connection, manager_id: UUID, since: date, limit: int
    ) -> list[dict[str, Any]]:
        return _rows(await conn.fetch(_CLOSED, manager_id, since, limit))
