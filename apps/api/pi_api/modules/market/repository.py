"""Market repository: SQL queries on securities, calendar, quotes, and benchmarks."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
import asyncpg

from pi_api.modules.market import health


class MarketRepository:

    @staticmethod
    async def search_securities(
        conn: asyncpg.Connection,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        search_pattern = f"%{query.upper()}%"
        sql = """
            SELECT security_id, symbol, exchange, isin, name, sector, industry, cap, is_active
            FROM market.securities
            WHERE (symbol ILIKE $1 OR name ILIKE $1)
            ORDER BY 
                CASE WHEN symbol = $2 THEN 0 WHEN symbol ILIKE $3 THEN 1 ELSE 2 END,
                symbol ASC
            LIMIT $4;
        """
        rows = await conn.fetch(sql, search_pattern, query.upper(), f"{query.upper()}%", limit)
        return [dict(r) for r in rows]

    @staticmethod
    async def get_trading_calendar(
        conn: asyncpg.Connection,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT cal_date, is_open, session_open::TEXT, session_close::TEXT, note
            FROM market.trading_calendar
            WHERE cal_date >= $1 AND cal_date <= $2
            ORDER BY cal_date ASC;
        """
        rows = await conn.fetch(sql, start_date, end_date)
        return [dict(r) for r in rows]

    @staticmethod
    async def get_benchmark_health(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """R10 dead-ticker guard: sessions behind the trading calendar, alarm > 2.

        Computed in Python rather than via the market.benchmark_health view: the
        view counts only stored calendar rows (0 when the calendar is empty or
        stops with the data) and so reported stale benchmarks as healthy.
        """
        benches = await conn.fetch(
            """
            SELECT b.code, max(v.value_date) AS last_date
            FROM market.benchmarks b
            LEFT JOIN market.benchmark_values v USING (benchmark_id)
            WHERE b.is_active
            GROUP BY b.code
            ORDER BY b.code;
            """
        )
        now = health.now_utc()
        upto = now.astimezone(health.IST).date()
        cal = await conn.fetch(
            """
            SELECT cal_date, is_open FROM market.trading_calendar
            WHERE cal_date >= $1 AND cal_date <= $2
            ORDER BY cal_date;
            """,
            upto - timedelta(days=400),
            upto,
        )
        open_days = [r["cal_date"] for r in cal if r["is_open"]]
        cal_max = cal[-1]["cal_date"] if cal else None
        sessions = health.expected_sessions(open_days, cal_max, upto)
        last_session = health.last_expected_session(now, sessions)
        results = []
        for r in benches:
            behind = health.sessions_behind(r["last_date"], sessions, last_session)
            results.append({
                "code": r["code"],
                "last_date": r["last_date"],
                "last_session": last_session,
                "sessions_behind": behind,
                "is_alarm": health.is_alarm(behind),
            })
        return results

    @staticmethod
    async def get_latest_closes(
        conn: asyncpg.Connection, symbols: List[str], lookback_days: int = 400
    ) -> List[Dict[str, Any]]:
        """Latest stored close per symbol within ``lookback_days`` (NSE preferred on a tie).

        R6: no row = unpriced. The window used to be 30 days, which made every board
        card unpriced whenever the EOD sync lagged; staleness is flagged by the service.
        """
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (s.symbol)
                   s.symbol, s.exchange, e.close::FLOAT AS price, e.price_date, e.source
            FROM market.securities s
            JOIN market.eod_prices e ON e.security_id = s.security_id
            WHERE s.symbol = ANY($1::text[])
              AND e.price_date >= current_date - $2::int
            ORDER BY s.symbol, e.price_date DESC, (s.exchange = 'NSE') DESC
            """,
            symbols,
            lookback_days,
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def get_open_days(conn: asyncpg.Connection, start: date, end: date) -> List[date]:
        rows = await conn.fetch(
            "SELECT cal_date FROM market.trading_calendar "
            "WHERE cal_date >= $1 AND cal_date <= $2 AND is_open ORDER BY cal_date;",
            start,
            end,
        )
        return [r["cal_date"] for r in rows]

    @staticmethod
    async def get_latest_eod_price(
        conn: asyncpg.Connection,
        symbol: str,
        exchange: str,
    ) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT e.close::FLOAT, e.price_date
            FROM market.eod_prices e
            JOIN market.securities s ON e.security_id = s.security_id
            WHERE s.symbol = $1 AND s.exchange = $2
            ORDER BY e.price_date DESC
            LIMIT 1;
        """
        row = await conn.fetchrow(sql, symbol.upper(), exchange.upper())
        return dict(row) if row else None

    @staticmethod
    async def get_benchmark_series(
        conn: asyncpg.Connection,
        code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT v.value_date AS as_of, v.value::FLOAT AS value, v.source
            FROM market.benchmark_values v
            JOIN market.benchmarks b USING (benchmark_id)
            WHERE b.code = $1
              AND ($2::DATE IS NULL OR v.value_date >= $2)
              AND ($3::DATE IS NULL OR v.value_date <= $3)
            ORDER BY v.value_date ASC;
        """
        rows = await conn.fetch(sql, code, start_date, end_date)
        return [dict(r) for r in rows]

