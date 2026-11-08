"""Health check and ops endpoints."""

from __future__ import annotations

from typing import Dict
from fastapi import APIRouter, Depends
import asyncpg

from pi_api.core.db import get_db_connection
from pi_api.settings import settings

router = APIRouter(tags=["ops"])


@router.get("/healthz")
async def healthz() -> Dict[str, str]:
    """Liveness probe: returns 200 if API process is running."""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.VERSION}


@router.get("/readyz")
async def readyz(conn: asyncpg.Connection = Depends(get_db_connection)) -> Dict[str, str]:
    """Readiness probe: validates DB connection is alive."""
    val = await conn.fetchval("SELECT 1;")
    if val == 1:
        return {"status": "ready", "database": "connected"}
    return {"status": "degraded", "database": "unresponsive"}
