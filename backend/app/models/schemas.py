"""Request/response models (no auth in Phase 1)."""
from __future__ import annotations

from pydantic import BaseModel


class ManagerCreate(BaseModel):
    name: str
    email: str | None = None
    firm: str | None = None


class ManagerUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    firm: str | None = None
    status: str | None = None


class ClientCreate(BaseModel):
    name: str
    portfolio_manager_id: str
    client_code: str | None = None   # Zerodha Client ID (e.g. QPJ806)
    email: str | None = None
    phone: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    client_code: str | None = None
    status: str | None = None


class TagCreate(BaseModel):
    """A reusable trade-journal tag: name + color, applied to any number of trades.
    The strategy/rationale lives on the tag (via description), not retyped per trade."""
    name: str
    color: str
    description: str | None = None


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None


class TradeTagsUpdate(BaseModel):
    """Full replacement of the tag set applied to one trade."""
    tag_ids: list[str]


class TradeNoteUpdate(BaseModel):
    """One-off free-text note on a trade — the specific 'why' this time, alongside
    the reusable tags."""
    note: str


class DividendCreate(BaseModel):
    symbol: str
    ex_date: str
    amount_per_share: float
    quantity: float
    source: str = "manual"


class DividendUpdate(BaseModel):
    symbol: str | None = None
    ex_date: str | None = None
    amount_per_share: float | None = None
    quantity: float | None = None
