"""Heatmap reads: held quantities, daily closes, split/bonus actions. SQL only (AGENTS §3.3)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import asyncpg

_HOLDINGS = """
SELECT s.symbol,
       SUM(p.quantity)::FLOAT AS qty,
       SUM(p.invested)::FLOAT AS invested,
       COUNT(DISTINCT p.client_id)::INT AS clients,
       MIN(p.entry_date) AS entry_date
FROM portfolio.positions_latest p
JOIN core.clients c ON c.client_id = p.client_id AND c.deleted_at IS NULL
JOIN market.securities s ON s.security_id = p.security_id
WHERE c.manager_id = $1
  AND ($2::uuid[] IS NULL OR p.client_id = ANY($2::uuid[]))
  AND p.quantity > 0
GROUP BY s.symbol
"""

# Every exchange's closes for the held symbols; the service keeps one exchange per symbol
# (never mixes them day to day, which would invent moves). Time predicate on both ends (§3.9).
_CLOSES = """
SELECT s.symbol, s.exchange, e.price_date, e.close::FLOAT AS close
FROM market.securities s
JOIN market.eod_prices e ON e.security_id = s.security_id
WHERE s.symbol = ANY($1::text[])
  AND e.price_date >= $2 AND e.price_date <= $3
ORDER BY s.symbol, s.exchange, e.price_date
"""

_ACTIONS = """
SELECT symbol, ex_date, type, qty_multiplier::FLOAT AS qty_multiplier
FROM ledger.corporate_actions
WHERE symbol = ANY($1::text[]) AND type IN ('SPLIT', 'BONUS') AND ex_date >= $2
"""


class HeatmapRepository:
    @staticmethod
    async def holdings(
        conn: asyncpg.Connection, manager_id: UUID, client_ids: list[UUID] | None
    ) -> list[dict]:
        return [dict(r) for r in await conn.fetch(_HOLDINGS, manager_id, client_ids)]

    @staticmethod
    async def closes(
        conn: asyncpg.Connection, symbols: list[str], since: date, until: date
    ) -> list[dict]:
        return [dict(r) for r in await conn.fetch(_CLOSES, symbols, since, until)]

    @staticmethod
    async def actions(
        conn: asyncpg.Connection, symbols: list[str], since: date
    ) -> list[dict]:
        return [dict(r) for r in await conn.fetch(_ACTIONS, symbols, since)]
