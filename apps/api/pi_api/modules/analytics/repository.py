"""Analytics repository: SQL only. Reads the worker's precomputed JSONB (HLD D1)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

# Whitelisted JSONB paths (never interpolate request input into SQL).
SECTION_PATHS: dict[str, list[str]] = {
    "summary": ["summary"],
    "performance": ["performance"],
    "trades.delivery": ["trades", "delivery"],
    "trades.intraday": ["trades", "intraday"],
    "playbook.delivery": ["playbook", "delivery"],
    "playbook.intraday": ["playbook", "intraday"],
}

_SECTION_SQL = """
    SELECT as_of, computed_at, engine_version, payload #> $2::text[] AS section
    FROM portfolio.client_analytics
    WHERE client_id = $1
"""

_CLIENT_CA_SQL = """
    WITH held AS (
        SELECT symbol, min(trade_date) AS first_date
        FROM ledger.trades
        WHERE client_id = $1 AND deleted_at IS NULL
        GROUP BY symbol
    )
    SELECT ca.action_id, ca.symbol, ca.ex_date, ca.type,
           ca.qty_multiplier::float8 AS qty_multiplier,
           ca.amount_per_share::float8 AS amount_per_share,
           ca.subject, ca.source
    FROM ledger.corporate_actions ca
    JOIN held h ON h.symbol = ca.symbol
    WHERE ca.ex_date >= h.first_date AND ca.ex_date >= $2
    ORDER BY ca.ex_date DESC, ca.action_id DESC
    LIMIT $3
"""


class AnalyticsRepository:
    @staticmethod
    async def get_section(
        conn: asyncpg.Connection, client_id: UUID, section: str
    ) -> dict[str, Any] | None:
        path = SECTION_PATHS[section]  # KeyError = programming error, not user input
        row = await conn.fetchrow(_SECTION_SQL, client_id, path)
        if row is None:
            return None
        raw = row["section"]
        return {
            "as_of": row["as_of"],
            "computed_at": row["computed_at"],
            "engine_version": row["engine_version"],
            "data": json.loads(raw) if isinstance(raw, str) else raw,
        }

    @staticmethod
    async def list_client_corporate_actions(
        conn: asyncpg.Connection, client_id: UUID, since: date, limit: int
    ) -> list[dict[str, Any]]:
        rows = await conn.fetch(_CLIENT_CA_SQL, client_id, since, limit)
        return [dict(r) for r in rows]
