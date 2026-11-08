"""Analytics service: authorisation-free business logic over the repository.

Not cached: each read is one primary-key lookup of a precomputed row. (core.cache
.cached_bytes cannot take an async fetch function today -- it would cache the
coroutine's repr -- so it is deliberately not used here.)
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg
from pi_core.analytics.playbook import playbook_csv

from pi_api.modules.analytics.repository import AnalyticsRepository

APPLIED_TYPES = {"SPLIT", "BONUS"}
REVIEW_TYPES = {"DEMERGER", "MERGER", "RIGHTS", "BUYBACK", "DELISTING", "OTHER"}
EARLIEST = date(1990, 1, 1)


def _ca_item(row: dict[str, Any]) -> dict[str, Any]:
    t = str(row["type"]).upper()
    return {**row, "applied_by_engine": t in APPLIED_TYPES, "needs_review": t in REVIEW_TYPES}


class AnalyticsService:
    def __init__(self, repo: AnalyticsRepository | None = None) -> None:
        self.repo = repo or AnalyticsRepository()

    async def section(
        self, conn: asyncpg.Connection, client_id: UUID, section: str
    ) -> dict[str, Any] | None:
        row = await self.repo.get_section(conn, client_id, section)
        if row is None:
            return None
        return {"client_id": str(client_id), **row}

    async def playbook_rows(
        self, conn: asyncpg.Connection, client_id: UUID, pool: str
    ) -> list[dict[str, Any]] | None:
        pools = ("delivery", "intraday") if pool == "all" else (pool,)
        rows: list[dict[str, Any]] = []
        found = False
        for p in pools:
            sec = await self.repo.get_section(conn, client_id, f"playbook.{p}")
            if sec is not None:
                found = True
                rows.extend(sec["data"] or [])
        return rows if found else None

    async def playbook_csv(self, conn: asyncpg.Connection, client_id: UUID) -> str | None:
        rows = await self.playbook_rows(conn, client_id, "all")
        return None if rows is None else playbook_csv(rows)

    async def corporate_actions(
        self, conn: asyncpg.Connection, client_id: UUID, since: date | None, limit: int
    ) -> list[dict[str, Any]]:
        rows = await self.repo.list_client_corporate_actions(
            conn, client_id, since or EARLIEST, limit
        )
        return [_ca_item(r) for r in rows]
