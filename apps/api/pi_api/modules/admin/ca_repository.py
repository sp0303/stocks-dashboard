"""Corporate-actions data-panel SQL (read-only; the refresh itself runs in a worker)."""

from __future__ import annotations

from typing import Any

import asyncpg

CA_JOB = "ca_refresh"


class CorporateActionsRepository:
    @staticmethod
    async def stats(conn: asyncpg.Connection) -> dict[str, Any]:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS actions,
                   COUNT(DISTINCT symbol) AS symbols,
                   MAX(fetched_at) AS last_fetched_at
            FROM ledger.corporate_actions
            """
        )
        return (
            dict(row) if row else {"actions": 0, "symbols": 0, "last_fetched_at": None}
        )

    @staticmethod
    async def last_run(conn: asyncpg.Connection) -> dict[str, Any] | None:
        row = await conn.fetchrow(
            """
            SELECT run_id, started_at, finished_at, status, rows_in, rows_out, error, meta
            FROM ops.job_runs
            WHERE job = $1 AND started_at >= now() - interval '90 days'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            CA_JOB,
        )
        return dict(row) if row else None
