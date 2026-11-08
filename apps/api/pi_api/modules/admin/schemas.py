"""Admin and manager-book API schemas. Ratios are decimals (R12); None = unknown."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

Broker = Literal["ZERODHA", "UPSTOX", "ANGEL", "OTHER"]


class PlatformOverviewResponse(BaseModel):
    total_market_value: float = 0.0
    total_capital_deployed: float = 0.0
    total_pnl: float = 0.0
    client_count: int = 0
    manager_count: int = 0
    trade_count: int = 0


class ManagerItemResponse(BaseModel):
    manager_id: UUID
    name: str
    email: str
    firm: str | None = None
    is_active: bool = True
    client_count: int = 0
    created_at: datetime


class ManagerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    firm: str | None = None
    password: str | None = Field(default=None, min_length=8)


class ManagerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    firm: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None


class ClientReassignRequest(BaseModel):
    manager_id: UUID


class CorporateActionsRunItem(BaseModel):
    run_id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    rows_in: int | None = None
    rows_out: int | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class CorporateActionsStatusResponse(BaseModel):
    actions: int = 0
    symbols: int = 0
    last_fetched_at: datetime | None = None
    last_run: CorporateActionsRunItem | None = None


class CorporateActionsRefreshRequest(BaseModel):
    scope: Literal["held", "all"] = "held"


class CorporateActionsRefreshResponse(BaseModel):
    accepted: bool
    scope: str
    message_id: str


# ------------------------------------------------------------------ manager book


class BookClientCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    client_code: str | None = Field(default=None, max_length=40)
    broker: Broker | None = None
    manager_id: UUID | None = (
        None  # super_admin only; managers always create under themselves
    )


class BookClientUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    client_code: str | None = Field(default=None, max_length=40)
    broker: Broker | None = None
    manager_id: UUID | None = None  # super_admin only


class BookClientResponse(BaseModel):
    client_id: UUID
    manager_id: UUID
    name: str
    client_code: str | None = None
    broker: str | None = None
    status: str
    created_at: datetime


class BookRosterItem(BaseModel):
    client_id: UUID
    name: str
    client_code: str | None = None
    broker: str | None = None
    status: str
    as_of: date | None = None
    computed: bool = False
    trade_count: int = 0
    market_value: float | None = None
    capital_deployed: float | None = None
    current_invested: float | None = None
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    total_pnl: float | None = None
    return_on_capital: float | None = None


class BookTotals(BaseModel):
    client_count: int = 0
    market_value: float = 0.0
    capital_deployed: float = 0.0
    current_invested: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    return_on_capital: float | None = None


class SymbolStat(BaseModel):
    symbol: str
    value: float


class BookInsights(BaseModel):
    unique_stocks: int = 0
    unpriced_symbols: list[str] = []
    most_invested: SymbolStat | None = None
    most_traded: SymbolStat | None = None  # value = trade count
    top_holding: SymbolStat | None = None
    best_performer: SymbolStat | None = None  # value = decimal return
    worst_performer: SymbolStat | None = None


class BookSummaryResponse(BaseModel):
    manager_id: UUID
    as_of: date | None = None
    totals: BookTotals
    insights: BookInsights
    clients: list[BookRosterItem]


class BenchmarkPnlSeries(BaseModel):
    code: str
    label: str
    points: list[float | None]
    last_date: date | None = None
    sessions_behind: int = 0
    stale: bool = False


class BookPerformanceResponse(BaseModel):
    dates: list[date]
    book_pnl: list[float]
    net_invested: list[float]
    benchmarks: list[BenchmarkPnlSeries]


class ReturnPoint(BaseModel):
    as_of: date
    value: float


class ClientReturnSeries(BaseModel):
    client_id: UUID
    name: str
    series: list[ReturnPoint]


class ClosedTradeItem(BaseModel):
    client_id: UUID
    client_name: str
    client_code: str | None = None
    symbol: str
    buy_date: date
    sell_date: date
    quantity: float
    buy_price: float
    sell_price: float
    pnl: float
    pnl_pct: float | None = None
    days: int
