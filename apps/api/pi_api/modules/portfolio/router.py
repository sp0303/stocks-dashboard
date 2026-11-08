"""Portfolio FastAPI router (thin layer: validate -> service -> response)."""

from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from pi_api.core.db import get_db_connection
from pi_api.modules.auth.deps import Principal, require_manager
from pi_api.modules.portfolio.schemas import (
    ClientMetricsResponse,
    ClientSummaryResponse,
    DailySeriesPointResponse,
    ManagerHoldingsItemResponse,
    ManagerMetricsResponse,
    PositionItemResponse,
)
from pi_api.modules.portfolio.service import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(require_manager)])
service = PortfolioService()


@router.get("/clients", response_model=List[ClientSummaryResponse])
async def list_clients(
    manager_id: Optional[UUID] = None,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[ClientSummaryResponse]:
    """Lists all managed clients with scoping enforced:
    - If role is 'manager', strictly scoped to their own manager_id.
    - If role is 'super_admin', can filter by manager_id or retrieve all.
    """
    effective_manager_id = principal.manager_id if principal.role == "manager" else manager_id
    items = await service.list_clients(conn, effective_manager_id)
    return [ClientSummaryResponse(**item) for item in items]


@router.get("/clients/{client_id}/overview", response_model=ClientSummaryResponse)
async def get_client_overview(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ClientSummaryResponse:
    """Returns single client overview, capital deployed, and return on capital with tenant check."""
    allowed = await service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access to client forbidden.")

    item = await service.get_overview(conn, client_id)
    if not item:
        raise HTTPException(status_code=404, detail="Client overview not found.")
    return ClientSummaryResponse(**item)


@router.get("/clients/{client_id}/positions", response_model=List[PositionItemResponse])
async def get_client_positions(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[PositionItemResponse]:
    """Returns all open positions for the client with live valuation."""
    allowed = await service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access to client forbidden.")

    items = await service.get_positions(conn, client_id)
    return [PositionItemResponse(**item) for item in items]


@router.get("/clients/{client_id}/series", response_model=List[DailySeriesPointResponse])
async def get_client_daily_series(
    client_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[DailySeriesPointResponse]:
    """Returns daily time-weighted NAV, open cost, and market value series (Rule R2, R11)."""
    allowed = await service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access to client forbidden.")

    items = await service.get_series(conn, client_id, start_date, end_date)
    return [DailySeriesPointResponse(**item) for item in items]


@router.get("/clients/{client_id}/metrics", response_model=ClientMetricsResponse)
async def get_client_metrics(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ClientMetricsResponse:
    """Returns computed risk metrics: Sharpe, volatility, drawdown, beta, alpha, XIRR (Rule R3, R4)."""
    allowed = await service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access to client forbidden.")

    item = await service.get_metrics(conn, client_id)
    if not item:
        raise HTTPException(status_code=404, detail="Client metrics not found.")
    return ClientMetricsResponse(**item)


@router.get("/managers/{manager_id}/holdings", response_model=List[ManagerHoldingsItemResponse])
async def get_manager_holdings(
    manager_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[ManagerHoldingsItemResponse]:
    """Returns aggregated holdings across all clients of the manager (Rule R5)."""
    if principal.role == "manager" and principal.manager_id != manager_id:
        raise HTTPException(status_code=403, detail="Cannot access holdings of another manager.")

    items = await service.get_manager_holdings(conn, manager_id)
    return [ManagerHoldingsItemResponse(**item) for item in items]


@router.get("/managers/{manager_id}/metrics", response_model=ManagerMetricsResponse)
async def get_manager_metrics(
    manager_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ManagerMetricsResponse:
    """Returns aggregated book metrics across all clients for the manager (Rule R5)."""
    if principal.role == "manager" and principal.manager_id != manager_id:
        raise HTTPException(status_code=403, detail="Cannot access metrics of another manager.")

    item = await service.get_manager_metrics(conn, manager_id)
    return ManagerMetricsResponse(**item)

