"""Research service layer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID
import asyncpg

from pi_api.modules.market import health
from pi_api.modules.market.repository import MarketRepository
from pi_api.modules.research.repository import ResearchRepository
from pi_api.modules.research.screener import market_context, normalise_snapshot, snapshot_meta

# The screener is "stale" once its close is more than one trading session old.
SCREENER_STALE_AFTER_SESSIONS = 1


class ResearchService:

    def __init__(self, repo: ResearchRepository = ResearchRepository()) -> None:
        self.repo = repo

    async def list_watchlists(self, conn: asyncpg.Connection, owner_id: UUID) -> List[Dict[str, Any]]:
        return await self.repo.list_watchlists(conn, owner_id)

    async def create_watchlist(
        self,
        conn: asyncpg.Connection,
        owner_type: str,
        owner_id: UUID,
        name: str,
        is_default: bool = False,
    ) -> Dict[str, Any]:
        return await self.repo.create_watchlist(conn, owner_type, owner_id, name, is_default)

    async def add_watchlist_entry(
        self,
        conn: asyncpg.Connection,
        watchlist_id: UUID,
        symbol: str,
        added_price: Optional[float] = None,
        why: Optional[str] = None,
        remarks: Optional[str] = None,
        risks: Optional[str] = None,
        sector: Optional[str] = None,
        alert_price: Optional[float] = None,
    ) -> None:
        await self.repo.add_watchlist_entry(
            conn, watchlist_id, symbol, added_price, why, remarks, risks, sector, alert_price
        )

    async def delete_watchlist_entry(self, conn: asyncpg.Connection, watchlist_id: UUID, symbol: str) -> None:
        await self.repo.delete_watchlist_entry(conn, watchlist_id, symbol)

    async def list_board(self, conn: asyncpg.Connection, owner_id: UUID) -> List[Dict[str, Any]]:
        return await self.repo.list_board_items(conn, owner_id)

    async def create_board_item(
        self,
        conn: asyncpg.Connection,
        owner_type: str,
        owner_id: UUID,
        symbol: str,
        lane: str,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        why: Optional[str] = None,
        colour: Optional[str] = None,
        sort_order: int = 0,
    ) -> Dict[str, Any]:
        return await self.repo.create_board_item(
            conn, owner_type, owner_id, symbol, lane, entry_price, exit_price, why, colour, sort_order
        )

    async def update_board_item(
        self,
        conn: asyncpg.Connection,
        item_id: UUID,
        lane: Optional[str] = None,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None,
        why: Optional[str] = None,
        colour: Optional[str] = None,
        sort_order: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        return await self.repo.update_board_item(
            conn, item_id, lane, entry_price, exit_price, why, colour, sort_order
        )

    async def delete_board_item(self, conn: asyncpg.Connection, item_id: UUID) -> None:
        await self.repo.delete_board_item(conn, item_id)

    async def get_watchlist_owner(self, conn: asyncpg.Connection, watchlist_id: UUID) -> Optional[UUID]:
        return await self.repo.get_watchlist_owner(conn, watchlist_id)

    async def get_board_item_owner(self, conn: asyncpg.Connection, item_id: UUID) -> Optional[UUID]:
        return await self.repo.get_board_item_owner(conn, item_id)

    async def get_thesis(self, conn: asyncpg.Connection, client_id: UUID, symbol: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get_stock_thesis(conn, client_id, symbol)

    async def save_thesis(self, conn: asyncpg.Connection, client_id: UUID, symbol: str, thesis: Dict[str, Any]) -> Dict[str, Any]:
        return await self.repo.upsert_stock_thesis(conn, client_id, symbol, thesis)

    async def get_latest_screener(self, conn: asyncpg.Connection, model: Optional[str]) -> Dict[str, Any]:
        snap = await self.repo.get_latest_screener_snapshot(conn, model)
        if not snap:
            return {"as_of": None, "model": model, "count": 0, "rows": [], "is_stale": True}
        payload = snap["payload"]
        rows = normalise_snapshot(payload)
        await self._fill_sectors(conn, rows)
        meta = snapshot_meta(payload)
        data_as_of = _as_date(meta["data_as_of"]) or snap["as_of"]
        behind = await self._sessions_behind(conn, data_as_of)
        return {
            "as_of": snap["as_of"],
            "model": snap["model"],
            "count": len(rows),
            "rows": rows,
            "data_as_of": data_as_of,
            "generated_at": meta["generated_at"],
            "source": meta["source"],
            "market": market_context(payload),
            "sessions_behind": behind,
            "is_stale": behind is None or behind > SCREENER_STALE_AFTER_SESSIONS,
        }

    async def _fill_sectors(self, conn: asyncpg.Connection, rows: List[Dict[str, Any]]) -> None:
        """Rows without a sector take the security master's (else they group as Unclassified)."""
        missing = sorted({r["symbol"] for r in rows if not r.get("sector")})
        if not missing:
            return
        try:
            sectors = await self.repo.get_security_sectors(conn, missing)
        except (asyncpg.PostgresError, AttributeError):
            return
        for r in rows:
            if not r.get("sector"):
                r["sector"] = sectors.get(r["symbol"])

    async def _sessions_behind(self, conn: asyncpg.Connection, as_of: Optional[date]) -> Optional[int]:
        if as_of is None:
            return None
        now = health.now_utc()
        upto = now.astimezone(health.IST).date()
        try:
            open_days = await MarketRepository.get_open_days(conn, upto - timedelta(days=60), upto)
        except (asyncpg.PostgresError, AttributeError):
            open_days = []
        sessions = health.expected_sessions(open_days, open_days[-1] if open_days else None, upto)
        return health.sessions_behind(as_of, sessions, health.last_expected_session(now, sessions))

    async def list_screener_snapshots(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        return await self.repo.list_screener_snapshots(conn)


def _as_date(v: Any) -> Optional[date]:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None
