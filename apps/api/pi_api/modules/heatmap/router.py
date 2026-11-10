# ruff: noqa: B008  # FastAPI Depends/Query defaults
"""Holdings heatmap router (thin: authorise -> service -> response). Read-only."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from pi_api.core.db import get_db_connection
from pi_api.modules.auth.deps import Principal, require_manager
from pi_api.modules.heatmap.schemas import HeatmapResponse
from pi_api.modules.heatmap.service import HeatmapService

router = APIRouter(
    prefix="/portfolio", tags=["heatmap"], dependencies=[Depends(require_manager)]
)
service = HeatmapService()
IST = ZoneInfo("Asia/Kolkata")  # trading dates are IST; the server clock is UTC


def _client_ids(raw: str | None) -> list[UUID] | None:
    if not raw:
        return None
    try:
        return [UUID(x) for x in raw.split(",") if x]
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="client_ids must be comma-separated UUIDs."
        ) from exc


@router.get("/managers/{manager_id}/heatmap", response_model=HeatmapResponse)
async def manager_heatmap(
    manager_id: UUID,
    client_ids: str | None = Query(
        None, description="Comma-separated; omitted = all clients"
    ),
    mode: Literal["day", "range"] = "day",
    day: date | None = Query(None, description="day mode; omitted = latest close"),
    start: date | None = Query(
        None, description="range mode; omitted = each stock's tracking day"
    ),
    grain: Literal["auto", "day", "week", "month"] = "auto",
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> HeatmapResponse:
    """Per-stock moves for what the selected clients hold (v1 My Board heatmap). Decimals."""
    if principal.role == "manager" and principal.manager_id != manager_id:
        raise HTTPException(
            status_code=403, detail="Cannot access another manager's book."
        )
    ids = _client_ids(client_ids)
    data = await service.build(
        conn, manager_id, ids, mode, day, start, grain, datetime.now(IST).date()
    )
    return HeatmapResponse(**data)
