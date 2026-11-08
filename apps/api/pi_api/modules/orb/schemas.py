"""ORB API response schemas. Prices in rupees; ratios are decimals (R12)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class UniverseResponse(BaseModel):
    trade_date: date | None = None
    size: int | None = None
    min_turnover_cr: float | None = None
    pool: Any = None
    sector_mapped: int = 0
    members: list[dict[str, Any]] = Field(default_factory=list)
    synced_at: datetime | None = None


class ScreenRow(BaseModel):
    sym: str
    passed: bool
    failed: str | None = None
    or_high: float | None = None
    or_low: float | None = None
    or_width: float | None = None  # decimal ratio (R12)
    rvol: float | None = None
    turnover_cr: float | None = None


class Screen(BaseModel):
    candidates: int | None = None
    passed: int | None = None
    shortlist: list[str] = Field(default_factory=list)
    rows: list[ScreenRow] = Field(default_factory=list)
    config: str | None = None
    at: datetime | None = None


class EntrySignal(BaseModel):
    sym: str | None = None
    minute: int | None = None
    time: str | None = None
    side: str | None = None
    entry: float | None = None
    stop: float | None = None
    t1: float | None = None
    t2: float | None = None
    qty: int | None = None
    risk: float | None = None
    config: str | None = None
    at: datetime | None = None


class SignalsResponse(BaseModel):
    trade_date: date | None = None
    screen: Screen | None = None
    entries: list[EntrySignal] = Field(default_factory=list)


class HealthSession(BaseModel):
    trade_date: date | None = None
    agree_ratio: float | None = None
    passes_exit_test: bool | None = None
    symbols: int | None = None
    minutes_compared: int | None = None
    minutes_matched: int | None = None
    at: datetime | None = None


class ExitTest(BaseModel):
    sessions_required: int
    sessions_scored: int
    sessions_passing: int
    worst_agree_ratio: float | None = None
    passed: bool


class Heartbeat(BaseModel):
    trade_date: date | None = None
    minute: int | None = None
    time: str | None = None
    market_open: bool | None = None
    at: datetime | None = None


class JobRun(BaseModel):
    trade_date: date | None = None
    job: str
    ok: bool | None = None
    minute: int | None = None
    detail: str | None = None
    seconds: float | None = None
    at: datetime | None = None


class HealthResponse(BaseModel):
    source: str = "v1_mongo"
    last_synced_at: datetime | None = None
    sessions: list[HealthSession] = Field(default_factory=list)
    exit_test: ExitTest
    heartbeat: Heartbeat | None = None
    jobs: list[JobRun] = Field(default_factory=list)


class JournalTrade(BaseModel):
    trade_date: date
    sym: str
    reason: str | None = None
    side: str | None = None
    time: str | None = None
    qty: int | None = None
    price: float | None = None
    entry: float | None = None
    stop: float | None = None
    r: float | None = None
    cum_r: float = 0.0


class JournalResponse(BaseModel):
    since: date
    count: int
    total_r: float
    win_rate: float | None = None
    expectancy_r: float | None = None
    trades: list[JournalTrade] = Field(default_factory=list)
