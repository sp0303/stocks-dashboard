# ruff: noqa: B008  # FastAPI Depends/Query defaults
"""Client analytics router (thin: authorise -> service -> response). Read-only."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from pi_api.core.db import get_db_connection
from pi_api.modules.analytics.schemas import (
    AnalyticsSectionResponse,
    ClientCorporateActionItem,
)
from pi_api.modules.analytics.service import AnalyticsService
from pi_api.modules.auth.deps import Principal, require_manager
from pi_api.modules.portfolio.service import PortfolioService

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_manager)])
service = AnalyticsService()
portfolio_service = PortfolioService()
NOT_READY = "Analytics not computed yet for this client."


async def _authorise(conn: asyncpg.Connection, client_id: UUID, principal: Principal) -> None:
    """Authorise BEFORE reading anything (AGENTS §3.10)."""
    if not await portfolio_service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    ):
        raise HTTPException(status_code=403, detail="Access to client forbidden.")


async def _section(conn, client_id: UUID, principal: Principal, name: str) -> AnalyticsSectionResponse:
    await _authorise(conn, client_id, principal)
    item = await service.section(conn, client_id, name)
    if item is None:
        raise HTTPException(status_code=404, detail=NOT_READY)
    return AnalyticsSectionResponse(**item)


@router.get("/clients/{client_id}/summary", response_model=AnalyticsSectionResponse)
async def get_summary(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> AnalyticsSectionResponse:
    """Allocation, concentration, health, beta/alpha, intraday pool, highlights, manual trades."""
    return await _section(conn, client_id, principal, "summary")


@router.get("/clients/{client_id}/performance", response_model=AnalyticsSectionResponse)
async def get_performance(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> AnalyticsSectionResponse:
    """Daily P&L vs benchmarks on the same net_invested baseline (R10), CAGR (R3)."""
    return await _section(conn, client_id, principal, "performance")


@router.get("/clients/{client_id}/trades", response_model=AnalyticsSectionResponse)
async def get_trade_analytics(
    client_id: UUID,
    pool: Literal["delivery", "intraday"] = Query("delivery"),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> AnalyticsSectionResponse:
    """Closed-trade statistics for one pool (R9), matched shares only (R7)."""
    return await _section(conn, client_id, principal, f"trades.{pool}")


@router.get("/clients/{client_id}/playbook", response_model=AnalyticsSectionResponse)
async def get_playbook(
    client_id: UUID,
    pool: Literal["delivery", "intraday"] = Query("delivery"),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> AnalyticsSectionResponse:
    """Per-stock round-trip table."""
    return await _section(conn, client_id, principal, f"playbook.{pool}")


@router.get("/clients/{client_id}/playbook/export")
async def export_playbook(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> Response:
    """CSV of both pools. Bearer-authenticated (R14: the UI fetches it as a blob)."""
    await _authorise(conn, client_id, principal)
    body = await service.playbook_csv(conn, client_id)
    if body is None:
        raise HTTPException(status_code=404, detail=NOT_READY)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="playbook_{client_id}.csv"'},
    )


@router.get("/clients/{client_id}/corporate-actions", response_model=list[ClientCorporateActionItem])
async def get_client_corporate_actions(
    client_id: UUID,
    since: date | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> list[ClientCorporateActionItem]:
    """Corporate actions on stocks this client has traded, from its first trade in each (R8)."""
    await _authorise(conn, client_id, principal)
    items = await service.corporate_actions(conn, client_id, since, limit)
    return [ClientCorporateActionItem(**i) for i in items]
