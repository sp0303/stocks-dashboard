"""Market service layer adhering to Rules R6, R10, R17."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import asyncpg

from pi_api.core.cache import get_redis_cache
from pi_api.modules.market import closes, health
from pi_api.modules.market.repository import MarketRepository


class MarketService:

    def __init__(self, repo: MarketRepository = MarketRepository()) -> None:
        self.repo = repo

    async def search_securities(
        self,
        conn: asyncpg.Connection,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return await self.repo.search_securities(conn, query, limit)

    async def get_quote(
        self,
        conn: asyncpg.Connection,
        symbol: str,
        exchange: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolves quote via Redis cache -> EOD fallback -> cost (Rule R6)."""
        sym = symbol.upper()
        exch = exchange.upper()
        key = f"q:{exch}:{sym}"

        # 1. Try Redis live quote cache
        try:
            r = get_redis_cache()
            cached = await r.get(key)
            if cached:
                data = json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
                return {
                    "symbol": sym,
                    "exchange": exch,
                    "price": float(data["price"]),
                    "as_of": data["as_of"],
                    "source": "REDIS_LIVE",
                    "is_stale": False,
                }
        except Exception:
            pass

        # 2. Fallback to latest EOD close price
        eod = await self.repo.get_latest_eod_price(conn, sym, exch)
        if eod:
            return {
                "symbol": sym,
                "exchange": exch,
                "price": eod["close"],
                "as_of": datetime.combine(eod["price_date"], datetime.min.time(), tzinfo=timezone.utc),
                "source": "EOD_CLOSE",
                "is_stale": True,
            }

        return None

    async def get_latest_closes(self, conn: asyncpg.Connection, symbols: List[str]) -> List[Dict[str, Any]]:
        """Latest close per requested symbol, with as_of and a staleness flag (R6)."""
        requested = closes.request_map(symbols)
        if not requested:
            return []
        found = await self.repo.get_latest_closes(conn, sorted(requested), closes.LOOKBACK_DAYS)
        if not found:
            return []
        sessions, last_session = await self._sessions(conn)
        return closes.build_rows(found, requested, sessions, last_session)

    async def _sessions(self, conn: asyncpg.Connection) -> tuple[list[date], Optional[date]]:
        """Expected sessions over the lookback (stored calendar, weekdays past its end)."""
        now = health.now_utc()
        upto = now.astimezone(health.IST).date()
        start = upto - timedelta(days=closes.LOOKBACK_DAYS)
        try:
            open_days = await self.repo.get_open_days(conn, start, upto)
        except (asyncpg.PostgresError, AttributeError):
            open_days = []
        cal_max = open_days[-1] if open_days else None
        sessions = health.expected_sessions(open_days, cal_max, upto)
        return sessions, health.last_expected_session(now, sessions)

    async def get_calendar(
        self,
        conn: asyncpg.Connection,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        return await self.repo.get_trading_calendar(conn, start_date, end_date)

    async def get_benchmark_health(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        return await self.repo.get_benchmark_health(conn)

    async def get_benchmark_series(
        self,
        conn: asyncpg.Connection,
        code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        return await self.repo.get_benchmark_series(conn, code, start_date, end_date)

