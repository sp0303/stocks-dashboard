"""Admin service layer: managers, platform overview, corporate-actions panel."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import asyncpg

from pi_api.core.events import publish_event
from pi_api.modules.admin.ca_repository import CorporateActionsRepository
from pi_api.modules.admin.repository import AdminRepository
from pi_api.modules.auth.repository import create_user as create_auth_user
from pi_api.modules.auth.service import hash_password

CA_REFRESH_STREAM = "stream:ca:refresh"
CA_REFRESH_EVENT = "ca.refresh.requested"
CA_SCOPES = ("held", "all")

Publisher = Callable[..., Awaitable[str]]


class AdminError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class AdminService:
    def __init__(
        self,
        repo: AdminRepository | None = None,
        ca_repo: CorporateActionsRepository | None = None,
        publisher: Publisher = publish_event,
    ) -> None:
        self.repo = repo or AdminRepository()
        self.ca_repo = ca_repo or CorporateActionsRepository()
        self.publisher = publisher

    async def get_overview(self, conn: asyncpg.Connection) -> dict[str, Any]:
        return await self.repo.get_platform_overview(conn)

    async def list_managers(self, conn: asyncpg.Connection) -> list[dict[str, Any]]:
        return await self.repo.list_managers(conn)

    async def create_manager(
        self,
        conn: asyncpg.Connection,
        name: str,
        email: str,
        firm: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        async with conn.transaction():
            mgr = await self.repo.create_manager(conn, name, email, firm)
            if password:
                await create_auth_user(
                    conn,
                    email=email,
                    password_hash=hash_password(password),  # argon2id
                    role="manager",
                    manager_id=mgr["manager_id"],
                    client_id=None,
                )
        return mgr

    async def update_manager(
        self,
        conn: asyncpg.Connection,
        manager_id: UUID,
        name: str | None = None,
        firm: str | None = None,
        is_active: bool | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        async with conn.transaction():
            res = await self.repo.update_manager(
                conn, manager_id, name, firm, is_active, email
            )
        if not res:
            raise AdminError(404, "Manager not found.")
        return res

    async def delete_manager(self, conn: asyncpg.Connection, manager_id: UUID) -> None:
        """Soft delete. Refused while the manager still has clients (reassign them first)."""
        n = await self.repo.count_live_clients(conn, manager_id)
        if n:
            raise AdminError(
                409, f"Manager still has {n} client(s). Reassign or delete them first."
            )
        async with conn.transaction():
            ok = await self.repo.soft_delete_manager(conn, manager_id)
        if not ok:
            raise AdminError(404, "Manager not found.")

    async def reassign_client(
        self, conn: asyncpg.Connection, client_id: UUID, new_manager_id: UUID
    ) -> bool:
        return await self.repo.reassign_client(conn, client_id, new_manager_id)

    # ------------------------------------------------------------ corporate actions
    async def corporate_actions_status(
        self, conn: asyncpg.Connection
    ) -> dict[str, Any]:
        stats = await self.ca_repo.stats(conn)
        run = await self.ca_repo.last_run(conn)
        if run and isinstance(run.get("meta"), (str, bytes)):
            run["meta"] = json.loads(run["meta"])
        return {
            "actions": int(stats.get("actions") or 0),
            "symbols": int(stats.get("symbols") or 0),
            "last_fetched_at": stats.get("last_fetched_at"),
            "last_run": run,
        }

    async def request_corporate_actions_refresh(
        self, scope: str, requested_by: UUID
    ) -> dict[str, Any]:
        """No provider call here (AGENTS §3.2): publish, and ca_refresh_worker does the NSE fetch."""
        if scope not in CA_SCOPES:
            raise AdminError(422, f"scope must be one of {', '.join(CA_SCOPES)}")
        try:
            msg_id = await self.publisher(
                CA_REFRESH_STREAM,
                CA_REFRESH_EVENT,
                {"scope": scope, "requested_by": str(requested_by)},
            )
        except Exception as exc:
            raise AdminError(503, "Event bus unavailable; try again shortly.") from exc
        return {"accepted": True, "scope": scope, "message_id": msg_id}
