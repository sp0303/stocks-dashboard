"""Admin repository — SQL for platform management (managers, overview).

Soft-deleted rows (``deleted_at IS NOT NULL``, migration 0004) are never listed or counted.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_MANAGER_COLS = "m.manager_id, m.name, m.email, m.firm, m.is_active, m.created_at"

# LEFT JOIN so a manager with zero clients is still listed (v1 parity: manager "SP").
# Only live, ACTIVE clients count toward client_count.
_LIST_MANAGERS = f"""
    SELECT {_MANAGER_COLS},
           COUNT(c.client_id) FILTER (
               WHERE c.status = 'ACTIVE' AND c.deleted_at IS NULL
           ) AS client_count
    FROM core.managers m
    LEFT JOIN core.clients c ON c.manager_id = m.manager_id
    WHERE m.deleted_at IS NULL
    GROUP BY m.manager_id, m.name, m.email, m.firm, m.is_active, m.created_at
    ORDER BY m.name
"""

_OVERVIEW = """
    SELECT
      (SELECT COUNT(*) FROM core.managers
        WHERE is_active AND deleted_at IS NULL)                         AS manager_count,
      (SELECT COUNT(*) FROM core.clients
        WHERE status = 'ACTIVE' AND deleted_at IS NULL)                 AS client_count,
      (SELECT COUNT(*) FROM ledger.trades WHERE deleted_at IS NULL)     AS trade_count,
      COALESCE(SUM((co.payload->>'market_value')::float8), 0)           AS total_market_value,
      COALESCE(SUM((co.payload->>'capital_deployed')::float8), 0)       AS total_capital_deployed,
      COALESCE(SUM((co.payload->>'total_pnl')::float8), 0)              AS total_pnl
    FROM portfolio.client_overview co
    JOIN core.clients c ON c.client_id = co.client_id
    WHERE c.status = 'ACTIVE' AND c.deleted_at IS NULL
"""


class AdminRepository:
    @staticmethod
    async def get_platform_overview(conn: asyncpg.Connection) -> dict[str, Any]:
        row = await conn.fetchrow(_OVERVIEW)
        out = dict(row) if row else {}
        return {
            "total_market_value": float(out.get("total_market_value") or 0.0),
            "total_capital_deployed": float(out.get("total_capital_deployed") or 0.0),
            "total_pnl": float(out.get("total_pnl") or 0.0),
            "client_count": int(out.get("client_count") or 0),
            "manager_count": int(out.get("manager_count") or 0),
            "trade_count": int(out.get("trade_count") or 0),
        }

    @staticmethod
    async def list_managers(conn: asyncpg.Connection) -> list[dict[str, Any]]:
        rows = await conn.fetch(_LIST_MANAGERS)
        return [dict(r) for r in rows]

    @staticmethod
    async def get_manager(
        conn: asyncpg.Connection, manager_id: UUID
    ) -> dict[str, Any] | None:
        row = await conn.fetchrow(
            f"""
            SELECT {_MANAGER_COLS},
                   (SELECT COUNT(*) FROM core.clients c
                     WHERE c.manager_id = m.manager_id AND c.status = 'ACTIVE'
                       AND c.deleted_at IS NULL) AS client_count
            FROM core.managers m
            WHERE m.manager_id = $1 AND m.deleted_at IS NULL
            """,
            manager_id,
        )
        return dict(row) if row else None

    @staticmethod
    async def create_manager(
        conn: asyncpg.Connection, name: str, email: str, firm: str | None = None
    ) -> dict[str, Any]:
        row = await conn.fetchrow(
            """
            INSERT INTO core.managers (name, email, firm)
            VALUES ($1, $2, $3)
            RETURNING manager_id, name, email, firm, is_active, created_at
            """,
            name,
            email,
            firm,
        )
        res = dict(row)
        res["client_count"] = 0
        return res

    @staticmethod
    async def update_manager(
        conn: asyncpg.Connection,
        manager_id: UUID,
        name: str | None = None,
        firm: str | None = None,
        is_active: bool | None = None,
        email: str | None = None,
    ) -> dict[str, Any] | None:
        # Whitelisted column names only; values are always bound parameters.
        params: list[Any] = [manager_id]
        fields: list[str] = []
        for col, val in (
            ("name", name),
            ("firm", firm),
            ("is_active", is_active),
            ("email", email),
        ):
            if val is not None:
                params.append(val)
                fields.append(f"{col} = ${len(params)}")
        if fields:
            done = await conn.execute(
                f"UPDATE core.managers SET {', '.join(fields)} "
                "WHERE manager_id = $1 AND deleted_at IS NULL",
                *params,
            )
            if done.endswith(" 0"):
                return None
            if is_active is not None:
                await AdminRepository.set_manager_logins_active(
                    conn, manager_id, is_active
                )
            if email is not None:
                await conn.execute(
                    "UPDATE auth.users SET email = $2 WHERE manager_id = $1 AND role = 'manager'",
                    manager_id,
                    email,
                )
        return await AdminRepository.get_manager(conn, manager_id)

    @staticmethod
    async def set_manager_logins_active(
        conn: asyncpg.Connection, manager_id: UUID, active: bool
    ) -> None:
        await conn.execute(
            "UPDATE auth.users SET is_active = $2 WHERE manager_id = $1 AND role = 'manager'",
            manager_id,
            active,
        )

    @staticmethod
    async def count_live_clients(conn: asyncpg.Connection, manager_id: UUID) -> int:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM core.clients WHERE manager_id = $1 AND deleted_at IS NULL",
            manager_id,
        )
        return int(n or 0)

    @staticmethod
    async def soft_delete_manager(conn: asyncpg.Connection, manager_id: UUID) -> bool:
        done = await conn.execute(
            "UPDATE core.managers SET deleted_at = now(), is_active = false "
            "WHERE manager_id = $1 AND deleted_at IS NULL",
            manager_id,
        )
        if done.endswith(" 0"):
            return False
        await AdminRepository.set_manager_logins_active(conn, manager_id, False)
        return True

    @staticmethod
    async def reassign_client(
        conn: asyncpg.Connection, client_id: UUID, new_manager_id: UUID
    ) -> bool:
        mgr = await conn.fetchval(
            "SELECT 1 FROM core.managers WHERE manager_id = $1 AND deleted_at IS NULL",
            new_manager_id,
        )
        if not mgr:
            return False
        result = await conn.execute(
            "UPDATE core.clients SET manager_id = $1 WHERE client_id = $2 AND deleted_at IS NULL",
            new_manager_id,
            client_id,
        )
        return result.endswith(" 1")
