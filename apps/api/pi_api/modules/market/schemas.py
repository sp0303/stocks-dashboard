"""Market API schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


class SecuritySearchItem(BaseModel):
    security_id: int
    symbol: str
    exchange: str
    isin: Optional[str] = None
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    cap: Optional[str] = None
    is_active: bool = True


class QuoteResponse(BaseModel):
    symbol: str
    exchange: str
    price: float
    as_of: datetime
    source: str
    is_stale: bool = False


class LatestCloseItem(BaseModel):
    symbol: str  # as requested (upper-cased)
    exchange: str
    price: float
    price_date: date  # as_of (R6)
    source: str
    security_symbol: Optional[str] = None  # master symbol when the request was normalised
    sessions_behind: Optional[int] = None
    is_stale: bool = False


class CalendarDayResponse(BaseModel):
    cal_date: date
    is_open: bool
    session_open: Optional[str] = None
    session_close: Optional[str] = None
    note: Optional[str] = None


class BenchmarkHealthItem(BaseModel):
    code: str
    last_date: Optional[date] = None
    last_session: Optional[date] = None
    sessions_behind: Optional[int] = None  # None = no values at all (alarms)
    is_alarm: bool = True


class BenchmarkSeriesPointResponse(BaseModel):
    as_of: date
    value: float
    source: str

