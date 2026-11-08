"""Analytics API schemas. Section bodies are the worker's JSON (shape: pi_core.analytics.client_report)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class AnalyticsSectionResponse(BaseModel):
    client_id: str
    as_of: date
    computed_at: datetime
    engine_version: str
    data: Any


class ClientCorporateActionItem(BaseModel):
    action_id: int
    symbol: str
    ex_date: date
    type: str
    qty_multiplier: float | None = None
    amount_per_share: float | None = None
    subject: str | None = None
    source: str
    # R8: split/bonus are applied by the engine; anything else needs a human look.
    applied_by_engine: bool
    needs_review: bool
