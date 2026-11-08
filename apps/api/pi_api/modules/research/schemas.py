"""Research schemas: Watchlists, Kanban Board, Theses, and Screener."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class WatchlistEntryItem(BaseModel):
    symbol: str
    added_date: date
    added_price: Optional[float] = None
    why: Optional[str] = None
    remarks: Optional[str] = None
    risks: Optional[str] = None
    sector: Optional[str] = None  # entry's own, else security master, else screener industry
    alert_price: Optional[float] = None
    alert_date: Optional[date] = None


class WatchlistResponse(BaseModel):
    watchlist_id: UUID
    owner_type: str
    owner_id: UUID
    name: str
    is_default: bool
    entries: List[WatchlistEntryItem] = Field(default_factory=list)


class WatchlistCreate(BaseModel):
    owner_type: str = "MANAGER"
    owner_id: UUID
    name: str
    is_default: bool = False


class WatchlistEntryAdd(BaseModel):
    symbol: str
    added_price: Optional[float] = None
    why: Optional[str] = None
    remarks: Optional[str] = None
    risks: Optional[str] = None
    sector: Optional[str] = None
    alert_price: Optional[float] = None


class BoardItemResponse(BaseModel):
    item_id: UUID
    owner_type: str
    owner_id: UUID
    symbol: str
    lane: str  # 'watching' | 'holding' | 'exit'
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    why: Optional[str] = None
    colour: Optional[str] = None
    sort_order: int = 0


class BoardItemCreate(BaseModel):
    owner_type: str = "MANAGER"
    owner_id: UUID
    symbol: str
    lane: str = "watching"
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    why: Optional[str] = None
    colour: Optional[str] = None
    sort_order: int = 0


class BoardItemUpdate(BaseModel):
    lane: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    why: Optional[str] = None
    colour: Optional[str] = None
    sort_order: Optional[int] = None


class StockThesisResponse(BaseModel):
    client_id: UUID
    symbol: str
    thesis: Dict[str, Any]
    updated_at: datetime


class StockThesisCreate(BaseModel):
    thesis: Dict[str, Any]


class ScreenerEvent(BaseModel):
    kind: str  # RESULTS | DIVIDEND | BONUS | SPLIT | RIGHTS | BUYBACK | DEMERGER
    date: date
    amount: Optional[float] = None


class ScreenerRow(BaseModel):
    """One stock in a screener snapshot. Momentum fields are decimals (Rule R12)."""

    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    setup: Optional[str] = None
    typical_hold_days: Optional[float] = None
    score: Optional[float] = None
    rank: Optional[float] = None
    value_score: Optional[float] = None
    quality_score: Optional[float] = None
    rsi: Optional[float] = None
    rel_strength: Optional[float] = None
    price: Optional[float] = None
    d1: Optional[float] = None
    w1: Optional[float] = None
    m1: Optional[float] = None
    y1: Optional[float] = None
    from_52w_high: Optional[float] = None
    events: List[ScreenerEvent] = Field(default_factory=list)


class ScreenerRegime(BaseModel):
    state: Optional[str] = None  # on | caution | off
    size_multiplier: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    breadth: Optional[float] = None  # decimal fraction (R12)
    vix: Optional[float] = None


class ScreenerExpiry(BaseModel):
    next_expiry: Optional[date] = None
    sessions_to_expiry: Optional[float] = None
    phase: Optional[str] = None
    in_entry_window: Optional[bool] = None
    calendar: Optional[str] = None


class ScreenerMarketContext(BaseModel):
    regime: Optional[ScreenerRegime] = None
    expiry: Optional[ScreenerExpiry] = None
    regime_basis: Optional[str] = None
    events_window: Optional[Dict[str, Any]] = None


class ScreenerSnapshotResponse(BaseModel):
    as_of: Optional[date] = None
    model: Optional[str] = None
    count: int = 0
    rows: List[ScreenerRow] = Field(default_factory=list)
    data_as_of: Optional[date] = None  # the close the screen was computed from
    generated_at: Optional[str] = None
    source: Optional[str] = None
    market: Optional[ScreenerMarketContext] = None
    sessions_behind: Optional[int] = None
    is_stale: bool = False  # older than one trading session (or no snapshot)


class ScreenerSnapshotMeta(BaseModel):
    as_of: date
    model: str
