"""Portfolio service layer."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from pi_api.modules.portfolio.repository import PortfolioRepository
from pi_core.series.book import book_metrics


class PortfolioService:
    def __init__(self, repo: PortfolioRepository | None = None) -> None:
        self.repo = repo or PortfolioRepository()

    async def list_clients(
        self, conn: asyncpg.Connection, manager_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        return await self.repo.list_clients_summary(conn, manager_id)

    async def get_overview(
        self, conn: asyncpg.Connection, client_id: UUID
    ) -> dict[str, Any] | None:
        return await self.repo.get_client_overview(conn, client_id)

    async def get_positions(
        self, conn: asyncpg.Connection, client_id: UUID
    ) -> list[dict[str, Any]]:
        return await self.repo.get_client_positions(conn, client_id)

    async def get_series(
        self,
        conn: asyncpg.Connection,
        client_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        return await self.repo.get_client_daily_series(
            conn, client_id, start_date, end_date
        )

    async def get_metrics(
        self, conn: asyncpg.Connection, client_id: UUID
    ) -> dict[str, Any] | None:
        return await self.repo.get_client_metrics(conn, client_id)

    async def validate_client_access(
        self,
        conn: asyncpg.Connection,
        client_id: UUID,
        role: str,
        manager_id: UUID | None,
        user_client_id: UUID | None,
    ) -> bool:
        return await self.repo.validate_client_access(
            conn, client_id, role, manager_id, user_client_id
        )

    async def get_manager_holdings(
        self, conn: asyncpg.Connection, manager_id: UUID
    ) -> list[dict[str, Any]]:
        return await self.repo.get_manager_aggregated_holdings(conn, manager_id)

    async def get_manager_metrics(
        self, conn: asyncpg.Connection, manager_id: UUID
    ) -> dict[str, Any]:
        out = await self.repo.get_manager_metrics(conn, manager_id)
        # R2/R3/R5: book TWR from the clients' own daily (return, base) rows — the same
        # pi_core function the worker exposes (compute_manager_metrics). Interim: computed
        # here (O(days x clients), no provider call) until portfolio_worker persists it.
        rows = await self.repo.get_manager_client_daily(conn, manager_id)
        book = book_metrics(rows)
        out.update(book)
        out["weighted_volatility"] = book["book_volatility"]
        out["weighted_sharpe"] = book["book_sharpe"]
        out["max_drawdown"] = book["book_max_drawdown"]
        return out
