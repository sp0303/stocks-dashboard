"""Broker (market-data) connectivity status.

Angel One authenticates from the .env TOTP secret with no browser step, so there's just
a status endpoint the UI polls to show which data source is live.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.services import angel

router = APIRouter(prefix="/api/angel", tags=["angel"])


@router.get("/status")
async def angel_status():
    return {"data": angel.status()}
