# ruff: noqa: B008 — FastAPI Depends/Query defaults are the framework idiom
"""Manager-book router (``/book/*``): roster CRUD and book read models.

Scope: super_admin sees every manager; a manager only their own book. Authorisation runs
before any read (AGENTS §3.10).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from pi_api.core.db import get_db_connection
from pi_api.modules.admin.book_service import EPOCH, BookError, BookService
from pi_api.modules.admin.schemas import (
    BookClientCreateRequest,
    BookClientResponse,
    BookClientUpdateRequest,
    BookPerformanceResponse,
    BookSummaryResponse,
    ClientReturnSeries,
    ClosedTradeItem,
)
from pi_api.modules.auth.deps import Principal, require_manager

router = APIRouter(
    prefix="/book", tags=["manager-book"], dependencies=[Depends(require_manager)]
)
service = BookService()


def _check_manager(principal: Principal, manager_id: UUID) -> None:
    if principal.role != "super_admin" and principal.manager_id != manager_id:
        raise HTTPException(
            status_code=403, detail="Cannot access another manager's book."
        )


def _codes(raw: str | None) -> list[str]:
    return [c.strip() for c in (raw or "").split(",") if c.strip()][:8]


@router.get("/managers/{manager_id}/summary", response_model=BookSummaryResponse)
async def book_summary(
    manager_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> BookSummaryResponse:
    """Tiles + roster: totals (sum of client overviews, R5), most invested/traded, top holding, best/worst."""
    _check_manager(principal, manager_id)
    return BookSummaryResponse(**await service.summary(conn, manager_id))


@router.get(
    "/managers/{manager_id}/performance", response_model=BookPerformanceResponse
)
async def book_performance(
    manager_id: UUID,
    benchmarks: str | None = Query(
        None, description="comma-separated benchmark codes; default all active"
    ),
    start_date: date = Query(EPOCH),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> BookPerformanceResponse:
    """Book P&L (market value − net invested) vs index-units benchmark P&L on the same baseline (R10)."""
    _check_manager(principal, manager_id)
    return BookPerformanceResponse(
        **await service.performance(conn, manager_id, _codes(benchmarks), start_date)
    )


@router.get(
    "/managers/{manager_id}/client-returns", response_model=list[ClientReturnSeries]
)
async def book_client_returns(
    manager_id: UUID,
    start_date: date = Query(EPOCH),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> list[ClientReturnSeries]:
    """Each client's time-weighted return (decimal), rebased to 0 at its first day."""
    _check_manager(principal, manager_id)
    return [
        ClientReturnSeries(**c)
        for c in await service.client_returns(conn, manager_id, start_date)
    ]


@router.get(
    "/managers/{manager_id}/closed-trades", response_model=list[ClosedTradeItem]
)
async def book_closed_trades(
    manager_id: UUID,
    start_date: date = Query(EPOCH),
    limit: int = Query(2000, ge=1, le=10000),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> list[ClosedTradeItem]:
    """Closed round trips across every account (from portfolio.round_trips)."""
    _check_manager(principal, manager_id)
    return [
        ClosedTradeItem(**r)
        for r in await service.closed_trades(conn, manager_id, start_date, limit)
    ]


@router.post(
    "/managers/{manager_id}/clients", response_model=BookClientResponse, status_code=201
)
async def create_client(
    manager_id: UUID,
    body: BookClientCreateRequest,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> BookClientResponse:
    _check_manager(principal, manager_id)
    target = (
        body.manager_id
        if principal.role == "super_admin" and body.manager_id
        else manager_id
    )
    try:
        row = await service.create_client(
            conn, target, body.name.strip(), _blank(body.client_code), body.broker
        )
    except BookError as err:
        raise HTTPException(status_code=err.status, detail=err.detail)
    return BookClientResponse(**row)


@router.patch("/clients/{client_id}", response_model=BookClientResponse)
async def update_client(
    client_id: UUID,
    body: BookClientUpdateRequest,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> BookClientResponse:
    changes = body.model_dump(exclude_unset=True)
    if "manager_id" in changes and principal.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Only a super-admin can move a client to another manager.",
        )
    if changes.get("manager_id") is None:
        changes.pop("manager_id", None)
    if "client_code" in changes:
        changes["client_code"] = _blank(changes["client_code"])
    try:
        current = await service.get_client(conn, client_id)
        _check_manager(principal, current["manager_id"])
        row = await service.update_client(conn, current, changes)
    except BookError as err:
        raise HTTPException(status_code=err.status, detail=err.detail)
    return BookClientResponse(**row)


@router.delete("/clients/{client_id}", status_code=204, response_model=None)
async def delete_client(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> None:
    """Soft delete: hidden from the book; ledger rows are kept (R13)."""
    try:
        current = await service.get_client(conn, client_id)
        _check_manager(principal, current["manager_id"])
        await service.delete_client(conn, client_id)
    except BookError as err:
        raise HTTPException(status_code=err.status, detail=err.detail)


def _blank(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None
