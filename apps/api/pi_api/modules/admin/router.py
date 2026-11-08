# ruff: noqa: B008 — FastAPI Depends/Query defaults are the framework idiom
"""Admin FastAPI routers.

``router`` (imported by main.py) bundles:
* ``admin_router`` — ``/admin/*``, super_admin only;
* ``book_router``  — ``/book/*``, manager scope (see book_router.py).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from pi_api.core.db import get_db_connection
from pi_api.modules.admin.book_router import router as book_router
from pi_api.modules.admin.schemas import (
    ClientReassignRequest,
    CorporateActionsRefreshRequest,
    CorporateActionsRefreshResponse,
    CorporateActionsStatusResponse,
    ManagerCreateRequest,
    ManagerItemResponse,
    ManagerUpdateRequest,
    PlatformOverviewResponse,
)
from pi_api.modules.admin.service import AdminError, AdminService
from pi_api.modules.auth.deps import Principal, require_super_admin

admin_router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_super_admin)]
)
service = AdminService()


def _raise(err: AdminError) -> None:
    raise HTTPException(status_code=err.status, detail=err.detail)


@admin_router.get("/overview", response_model=PlatformOverviewResponse)
async def get_overview(
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> PlatformOverviewResponse:
    """Platform tiles: active managers, active clients, trades stored, AUM."""
    return PlatformOverviewResponse(**await service.get_overview(conn))


@admin_router.get("/managers", response_model=list[ManagerItemResponse])
async def list_managers(
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> list[ManagerItemResponse]:
    """Every non-deleted manager, including those with zero clients."""
    return [ManagerItemResponse(**m) for m in await service.list_managers(conn)]


@admin_router.post("/managers", response_model=ManagerItemResponse, status_code=201)
async def create_manager(
    body: ManagerCreateRequest, conn: asyncpg.Connection = Depends(get_db_connection)
) -> ManagerItemResponse:
    try:
        mgr = await service.create_manager(
            conn, body.name, str(body.email), body.firm, body.password
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409, detail="A manager or login with that email already exists."
        )
    return ManagerItemResponse(**mgr)


@admin_router.patch("/managers/{manager_id}", response_model=ManagerItemResponse)
async def update_manager(
    manager_id: UUID,
    body: ManagerUpdateRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ManagerItemResponse:
    """Edit name / firm / email, or deactivate (is_active=false also disables the manager's login)."""
    email = str(body.email) if body.email is not None else None
    try:
        res = await service.update_manager(
            conn, manager_id, body.name, body.firm, body.is_active, email
        )
    except AdminError as err:
        _raise(err)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="That email is already in use.")
    return ManagerItemResponse(**res)


@admin_router.delete("/managers/{manager_id}", status_code=204, response_model=None)
async def delete_manager(
    manager_id: UUID, conn: asyncpg.Connection = Depends(get_db_connection)
) -> None:
    """Soft delete (deleted_at). 409 while the manager still has clients."""
    try:
        await service.delete_manager(conn, manager_id)
    except AdminError as err:
        _raise(err)


@admin_router.patch("/clients/{client_id}/reassign", status_code=204, response_model=None)
async def reassign_client(
    client_id: UUID,
    body: ClientReassignRequest,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> None:
    if not await service.reassign_client(conn, client_id, body.manager_id):
        raise HTTPException(
            status_code=400, detail="Failed to reassign client. Verify manager exists."
        )


@admin_router.get(
    "/corporate-actions/status", response_model=CorporateActionsStatusResponse
)
async def corporate_actions_status(
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> CorporateActionsStatusResponse:
    """'N actions stored · M symbols' plus the last ca_refresh run."""
    return CorporateActionsStatusResponse(
        **await service.corporate_actions_status(conn)
    )


@admin_router.post(
    "/corporate-actions/refresh",
    response_model=CorporateActionsRefreshResponse,
    status_code=202,
)
async def corporate_actions_refresh(
    body: CorporateActionsRefreshRequest,
    principal: Principal = Depends(require_super_admin),
) -> CorporateActionsRefreshResponse:
    """Queue a refresh (scope=held: symbols in the ledger; scope=all: every NSE equity)."""
    try:
        res = await service.request_corporate_actions_refresh(
            body.scope, principal.user_id
        )
    except AdminError as err:
        _raise(err)
    return CorporateActionsRefreshResponse(**res)


router = APIRouter()
router.include_router(admin_router)
router.include_router(book_router)
