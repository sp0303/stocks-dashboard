"""ORB router: read-only views over orb.* (manager / super_admin only).

Pre-cutover the data is a mirror of v1's Mongo, written by pi-orb-sync. Nothing here
calls a provider (AGENTS §3.2) or writes.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, Query
from pi_api.core.db import get_db_connection
from pi_api.modules.auth.deps import require_manager
from pi_api.modules.orb.schemas import (
    HealthResponse,
    JournalResponse,
    SignalsResponse,
    UniverseResponse,
)
from pi_api.modules.orb.service import OrbService, today_ist

router = APIRouter(prefix="/orb", tags=["orb"], dependencies=[Depends(require_manager)])
service = OrbService()


@router.get("/universe", response_model=UniverseResponse)
async def get_universe(
    on: date | None = Query(None, alias="date"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> UniverseResponse:
    """Latest ORB universe on or before `date` (default: today IST)."""
    return UniverseResponse(**await service.universe(conn, on or today_ist()))


@router.get("/signals", response_model=SignalsResponse)
async def get_signals(
    on: date | None = Query(None, alias="date"),
    kind: Literal["screen", "entry"] | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> SignalsResponse:
    """The day's screen (shortlist + candidates) and entry signals, as v1 produced them."""
    return SignalsResponse(**await service.signals(conn, on, kind))


@router.get("/health", response_model=HealthResponse)
async def get_health(
    days: int = Query(15, ge=1, le=90),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> HealthResponse:
    """Feed reconciliation sessions, exit test, heartbeat, recent jobs, and sync freshness."""
    return HealthResponse(**await service.health(conn, days))


@router.get("/journal", response_model=JournalResponse)
async def get_journal(
    days: int = Query(30, ge=1, le=365),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> JournalResponse:
    """Closed paper trades and the running result in R."""
    return JournalResponse(**await service.journal(conn, days))
