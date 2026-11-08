"""Client roster SQL for the manager book: create / edit / soft delete (core.clients).

A soft delete sets ``deleted_at`` and ``status = 'INACTIVE'``. The ledger is append-only
(R13), so the client's trades, uploads and dividends are kept untouched.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_COLS = "client_id, manager_id, name, client_code, broker, status, created_at"


class ClientsRepository:
    @staticmethod
    async def get_client(
        conn: asyncpg.Connection, client_id: UUID
    ) -> dict[str, Any] | None:
        row = await conn.fetchrow(
            f"SELECT {_COLS} FROM core.clients WHERE client_id = $1 AND deleted_at IS NULL",
            client_id,
        )
        return dict(row) if row else None

    @staticmethod
    async def manager_exists(conn: asyncpg.Connection, manager_id: UUID) -> bool:
        ok = await conn.fetchval(
            "SELECT 1 FROM core.managers WHERE manager_id = $1 AND deleted_at IS NULL",
            manager_id,
        )
        return bool(ok)

    @staticmethod
    async def code_taken(
        conn: asyncpg.Connection,
        manager_id: UUID,
        client_code: str,
        exclude_client_id: UUID | None = None,
    ) -> bool:
        hit = await conn.fetchval(
            """
            SELECT 1 FROM core.clients
            WHERE manager_id = $1 AND client_code = $2
              AND ($3::uuid IS NULL OR client_id <> $3)
            """,
            manager_id,
            client_code,
            exclude_client_id,
        )
        return bool(hit)

    @staticmethod
    async def create_client(
        conn: asyncpg.Connection,
        manager_id: UUID,
        name: str,
        client_code: str | None,
        broker: str | None,
    ) -> dict[str, Any]:
        row = await conn.fetchrow(
            f"""
            INSERT INTO core.clients (manager_id, name, client_code, broker)
            VALUES ($1, $2, $3, $4)
            RETURNING {_COLS}
            """,
            manager_id,
            name,
            client_code,
            broker,
        )
        return dict(row)

    @staticmethod
    async def update_client(
        conn: asyncpg.Connection, client_id: UUID, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        allowed = ("name", "client_code", "broker", "manager_id", "status")
        params: list[Any] = [client_id]
        fields: list[str] = []
        for col in allowed:  # column names come from this whitelist only
            if col in changes:
                params.append(changes[col])
                fields.append(f"{col} = ${len(params)}")
        if not fields:
            return await ClientsRepository.get_client(conn, client_id)
        row = await conn.fetchrow(
            f"UPDATE core.clients SET {', '.join(fields)} "
            f"WHERE client_id = $1 AND deleted_at IS NULL RETURNING {_COLS}",
            *params,
        )
        return dict(row) if row else None

    @staticmethod
    async def soft_delete_client(conn: asyncpg.Connection, client_id: UUID) -> bool:
        done = await conn.execute(
            "UPDATE core.clients SET deleted_at = now(), status = 'INACTIVE' "
            "WHERE client_id = $1 AND deleted_at IS NULL",
            client_id,
        )
        if done.endswith(" 0"):
            return False
        await conn.execute(
            "UPDATE auth.users SET is_active = false WHERE client_id = $1 AND role = 'client'",
            client_id,
        )
        return True
