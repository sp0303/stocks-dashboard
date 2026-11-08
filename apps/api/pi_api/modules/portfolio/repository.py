"""Portfolio repository: strictly SQL queries returning typed records."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from pi_core.pricing import MAX_PRICE_CARRY_DAYS


class PortfolioRepository:
    @staticmethod
    async def list_clients_summary(
        conn: asyncpg.Connection, manager_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        query = """
            SELECT 
                c.client_id,
                c.name,
                c.client_code,
                c.broker,
                c.status,
                co.as_of,
                co.payload
            FROM core.clients c
            LEFT JOIN portfolio.client_overview co ON c.client_id = co.client_id
            WHERE ($1::UUID IS NULL OR c.manager_id = $1)
              AND c.deleted_at IS NULL
            ORDER BY c.name;
        """
        rows = await conn.fetch(query, manager_id)
        results = []
        for r in rows:
            payload = json.loads(r["payload"]) if r["payload"] else {}
            results.append(
                {
                    "client_id": r["client_id"],
                    "name": r["name"],
                    "client_code": r["client_code"],
                    "broker": r["broker"],
                    "status": r["status"],
                    "as_of": r["as_of"],
                    "market_value": payload.get("market_value", 0.0),
                    "capital_deployed": payload.get("capital_deployed", 0.0),
                    "current_invested": payload.get("current_invested", 0.0),
                    "realized_pnl": payload.get("realized_pnl", 0.0),
                    "unrealized_pnl": payload.get("unrealized_pnl", 0.0),
                    "total_pnl": payload.get("total_pnl", 0.0),
                    "return_on_capital": payload.get("return_on_capital", 0.0),
                    "cagr": payload.get("cagr"),
                }
            )
        return results

    @staticmethod
    async def get_client_overview(
        conn: asyncpg.Connection, client_id: UUID
    ) -> dict[str, Any] | None:
        query = """
            SELECT 
                c.client_id,
                c.name,
                c.client_code,
                c.broker,
                c.status,
                co.as_of,
                co.payload
            FROM core.clients c
            LEFT JOIN portfolio.client_overview co ON c.client_id = co.client_id
            WHERE c.client_id = $1;
        """
        row = await conn.fetchrow(query, client_id)
        if not row:
            return None
        payload = json.loads(row["payload"]) if row["payload"] else {}
        return {
            "client_id": row["client_id"],
            "name": row["name"],
            "client_code": row["client_code"],
            "broker": row["broker"],
            "status": row["status"],
            "as_of": row["as_of"],
            **payload,
        }

    @staticmethod
    async def get_client_positions(
        conn: asyncpg.Connection, client_id: UUID
    ) -> list[dict[str, Any]]:
        """Open holdings, priced and unpriced (R6).

        A holding the engine found unpriced on its last run, or with no close at all,
        has price/value/P&L = None and ``priced = False``: never shown at cost with 0 %.
        """
        query = """
            SELECT
                p.security_id,
                s.symbol,
                s.exchange,
                p.quantity::FLOAT,
                p.avg_cost::FLOAT,
                p.invested::FLOAT,
                p.entry_date,
                eod.close::FLOAT AS current_price,
                eod.price_date AS price_as_of,
                eod.priced_on
            FROM portfolio.positions_latest p
            JOIN market.securities s ON p.security_id = s.security_id
            LEFT JOIN LATERAL (
                SELECT e.close, e.price_date, s2.exchange AS priced_on
                FROM market.securities s2
                JOIN market.eod_prices e ON e.security_id = s2.security_id
                WHERE s2.symbol = s.symbol
                  AND e.price_date >= CURRENT_DATE - 400
                ORDER BY (e.price_date >= CURRENT_DATE - $2::int) DESC,
                         (s2.security_id = p.security_id) DESC,
                         e.price_date DESC
                LIMIT 1
            ) eod ON true
            WHERE p.client_id = $1
            ORDER BY s.symbol, s.exchange;
        """
        rows = await conn.fetch(query, client_id, MAX_PRICE_CARRY_DAYS)
        payload = await conn.fetchval(
            "SELECT payload FROM portfolio.client_overview WHERE client_id = $1",
            client_id,
        )
        unpriced = unpriced_keys(payload)
        return [position_row(dict(r), unpriced) for r in rows]

    @staticmethod
    async def get_client_daily_series(
        conn: asyncpg.Connection,
        client_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT 
                as_of,
                market_value::FLOAT,
                open_cost::FLOAT,
                net_invested::FLOAT,
                realized_pnl::FLOAT,
                nav::FLOAT,
                day_return::FLOAT
            FROM portfolio.client_daily
            WHERE client_id = $1
              AND ($2::DATE IS NULL OR as_of >= $2)
              AND ($3::DATE IS NULL OR as_of <= $3)
            ORDER BY as_of ASC;
        """
        rows = await conn.fetch(query, client_id, start_date, end_date)
        return [dict(r) for r in rows]

    @staticmethod
    async def get_client_metrics(
        conn: asyncpg.Connection, client_id: UUID
    ) -> dict[str, Any] | None:
        query = """
            SELECT as_of, obs, payload
            FROM portfolio.client_metrics
            WHERE client_id = $1;
        """
        row = await conn.fetchrow(query, client_id)
        if not row:
            return None
        payload = json.loads(row["payload"]) if row["payload"] else {}
        return {
            "client_id": client_id,
            "as_of": row["as_of"],
            "total_return": payload.get("total_return", 0.0),
            "cagr": payload.get("cagr"),
            "annualized_volatility": payload.get("annualized_volatility"),
            "sharpe_ratio": payload.get("sharpe_ratio"),
            "max_drawdown": payload.get("max_drawdown"),
            "current_drawdown": payload.get("current_drawdown"),
            "beta": payload.get("beta"),
            "alpha": payload.get("alpha"),
            "xirr": payload.get("xirr"),
            "payload": payload,
        }

    @staticmethod
    async def validate_client_access(
        conn: asyncpg.Connection,
        client_id: UUID,
        role: str,
        manager_id: UUID | None,
        user_client_id: UUID | None,
    ) -> bool:
        if role == "super_admin":
            return True
        if role == "manager" and manager_id:
            row = await conn.fetchval(
                "SELECT 1 FROM core.clients WHERE client_id = $1 AND manager_id = $2",
                client_id,
                manager_id,
            )
            return bool(row)
        if role == "client" and user_client_id:
            return user_client_id == client_id
        return False

    @staticmethod
    async def get_manager_aggregated_holdings(
        conn: asyncpg.Connection, manager_id: UUID
    ) -> list[dict[str, Any]]:
        """Holdings summed across the manager's clients (R5), with a per-client breakdown.

        R6: a security with no price leaves price, value and P&L as None — never cost.
        """
        query = """
            SELECT
                p.security_id,
                s.symbol,
                s.exchange,
                SUM(p.quantity)::FLOAT AS quantity,
                SUM(p.invested)::FLOAT AS invested,
                COUNT(DISTINCT p.client_id) AS client_count,
                eod.close::FLOAT AS current_price,
                eod.price_date AS price_as_of,
                eod.priced_on,
                json_agg(json_build_object(
                    'client_id', c.client_id, 'name', c.name,
                    'quantity', p.quantity::FLOAT, 'invested', p.invested::FLOAT
                ) ORDER BY c.name) AS clients
            FROM portfolio.positions_latest p
            JOIN core.clients c ON p.client_id = c.client_id AND c.deleted_at IS NULL
            JOIN market.securities s ON p.security_id = s.security_id
            LEFT JOIN LATERAL (
                SELECT e.close, e.price_date, s2.exchange AS priced_on
                FROM market.securities s2
                JOIN market.eod_prices e ON e.security_id = s2.security_id
                WHERE s2.symbol = s.symbol
                  AND e.price_date >= CURRENT_DATE - $2::int
                ORDER BY (s2.security_id = p.security_id) DESC, e.price_date DESC
                LIMIT 1
            ) eod ON true
            WHERE c.manager_id = $1
            GROUP BY p.security_id, s.symbol, s.exchange, eod.close, eod.price_date, eod.priced_on
            ORDER BY s.symbol;
        """
        rows = await conn.fetch(query, manager_id, MAX_PRICE_CARRY_DAYS)
        results = []
        for r in rows:
            qty = r["quantity"]
            invested = r["invested"]
            price = r["current_price"]
            mv = qty * price if price is not None else None
            unrealized = mv - invested if mv is not None else None
            ret_pct = (
                unrealized / invested
                if unrealized is not None and invested > 0
                else None
            )
            results.append(
                {
                    "security_id": r["security_id"],
                    "symbol": r["symbol"],
                    "exchange": r["exchange"],
                    "quantity": qty,
                    "avg_cost": (invested / qty) if qty > 0 else 0.0,
                    "invested": invested,
                    "client_count": r["client_count"],
                    "current_price": price,
                    "price_as_of": r["price_as_of"],
                    "priced_on": r.get("priced_on") if r.get("priced_on") != r["exchange"] else None,
                    "market_value": mv,
                    "unrealized_pnl": unrealized,
                    "return_pct": ret_pct,
                    "clients": json.loads(r["clients"])
                    if isinstance(r["clients"], str)
                    else (r["clients"] or []),
                }
            )
        return results

    @staticmethod
    async def get_manager_client_daily(
        conn: asyncpg.Connection, manager_id: UUID
    ) -> list[tuple]:
        """(as_of, day_return, twr_base, market_value) of the manager's active clients (R5)."""
        rows = await conn.fetch(
            """
            SELECT d.as_of, d.day_return::FLOAT AS day_return,
                   d.twr_base::FLOAT AS twr_base, d.market_value::FLOAT AS market_value
            FROM portfolio.client_daily d
            JOIN core.clients c USING (client_id)
            WHERE c.manager_id = $1 AND c.status = 'ACTIVE'
              AND d.as_of >= DATE '1990-01-01'
            ORDER BY d.as_of
            """,
            manager_id,
        )
        return [
            (r["as_of"], r["day_return"], r["twr_base"], r["market_value"])
            for r in rows
        ]

    @staticmethod
    async def get_manager_metrics(
        conn: asyncpg.Connection, manager_id: UUID
    ) -> dict[str, Any]:
        """Book-level totals summed from client figures (Rule R5)."""
        clients = await PortfolioRepository.list_clients_summary(conn, manager_id)
        client_count = len(clients)
        total_cd = sum(c.get("capital_deployed", 0.0) for c in clients)
        total_mv = sum(c.get("market_value", 0.0) for c in clients)
        total_inv = sum(c.get("current_invested", 0.0) for c in clients)
        total_realized = sum(c.get("realized_pnl", 0.0) for c in clients)
        total_unrealized = sum(c.get("unrealized_pnl", 0.0) for c in clients)
        total_pnl = sum(c.get("total_pnl", 0.0) for c in clients)
        roc = (total_pnl / total_cd) if total_cd > 0 else 0.0

        m_daily = await conn.fetchrow(
            "SELECT as_of FROM portfolio.manager_daily WHERE manager_id = $1 "
            "AND as_of >= DATE '1990-01-01' ORDER BY as_of DESC LIMIT 1",
            manager_id,
        )
        as_of_date = (
            m_daily["as_of"]
            if m_daily
            else (clients[0]["as_of"] if clients and clients[0]["as_of"] else None)
        )

        return {
            "manager_id": manager_id,
            "client_count": client_count,
            "total_capital_deployed": total_cd,
            "total_market_value": total_mv,
            "total_current_invested": total_inv,
            "total_realized_pnl": total_realized,
            "total_unrealized_pnl": total_unrealized,
            "total_pnl": total_pnl,
            "return_on_capital": roc,
            "as_of": as_of_date,
        }


def unpriced_keys(payload: Any) -> set:
    """(symbol, exchange) keys the engine excluded as unpriced on its last run (R6.4)."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    items = (payload or {}).get("unpriced") or []
    return {(u.get("symbol"), u.get("exchange")) for u in items if isinstance(u, dict)}


def position_row(r: dict[str, Any], unpriced: set) -> dict[str, Any]:
    """R6: price/value/P&L are None for an unpriced holding — never cost and 0 %."""
    price = r.get("current_price")
    priced = (
        price is not None and price > 0 and (r["symbol"], r["exchange"]) not in unpriced
    )
    mv = r["quantity"] * price if priced else None
    unrealized = mv - r["invested"] if mv is not None else None
    return {
        "security_id": r["security_id"],
        "symbol": r["symbol"],
        "exchange": r["exchange"],
        "quantity": r["quantity"],
        "avg_cost": r["avg_cost"],
        "invested": r["invested"],
        "current_price": price if priced else None,
        "price_as_of": r.get("price_as_of") if priced else None,
        "priced": priced,
        "priced_on": r.get("priced_on") if priced and r.get("priced_on") != r["exchange"] else None,
        "market_value": mv,
        "unrealized_pnl": unrealized,
        "return_pct": (unrealized / r["invested"])
        if unrealized is not None and r["invested"] > 0
        else None,
        "entry_date": r["entry_date"],
    }
