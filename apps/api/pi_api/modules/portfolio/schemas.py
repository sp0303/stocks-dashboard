"""Portfolio API schemas (Pydantic v2 contract)."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ClientSummaryResponse(BaseModel):
    client_id: UUID
    name: str
    client_code: str | None = None
    broker: str | None = None
    status: str = "ACTIVE"
    market_value: float = 0.0
    capital_deployed: float = 0.0
    current_invested: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    return_on_capital: float = 0.0
    cagr: float | None = None
    as_of: date | None = None
    # R6.4: holdings with no usable price, outside current_invested and market_value
    unpriced: list[UnpricedHolding] = []
    unpriced_cost: float = 0.0
    priced_on_other_exchange: list[dict[str, str]] = []  # lots valued at the other exchange's close
    open_positions: int | None = None  # priced + unpriced, matches the holdings table
    priced_positions: int | None = None
    intraday: PoolPnl | None = None  # R9: P&L only, never capital
    derivatives: PoolPnl | None = None
    warnings: list[str] = []


class UnpricedHolding(BaseModel):
    symbol: str
    exchange: str
    quantity: float
    cost: float


class PoolPnl(BaseModel):
    trades: int = 0
    pnl: float = 0.0


class PositionItemResponse(BaseModel):
    security_id: int
    symbol: str
    exchange: str
    quantity: float
    avg_cost: float
    invested: float
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    return_pct: float | None = None
    entry_date: date | None = None
    priced: bool = True  # False = no usable price: excluded from cost and value (R6.4)
    price_as_of: date | None = None
    priced_on: str | None = None  # set when valued at the other exchange's close (ADR-0009)


class DailySeriesPointResponse(BaseModel):
    as_of: date
    market_value: float
    open_cost: float
    net_invested: float
    realized_pnl: float
    nav: float
    day_return: float | None = None


class ClientMetricsResponse(BaseModel):
    client_id: UUID
    as_of: date
    total_return: float
    cagr: float | None = None
    annualized_volatility: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    current_drawdown: float | None = None
    beta: float | None = None
    alpha: float | None = None
    xirr: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class HoldingClientItem(BaseModel):
    client_id: UUID
    name: str
    quantity: float
    invested: float


class ManagerHoldingsItemResponse(BaseModel):
    security_id: int
    symbol: str
    exchange: str
    quantity: float
    avg_cost: float
    invested: float
    client_count: int
    current_price: float | None = None  # None = unpriced (R6), never cost
    price_as_of: date | None = None
    priced_on: str | None = None  # set when valued at the other exchange's close (ADR-0009)
    market_value: float | None = None
    unrealized_pnl: float | None = None
    return_pct: float | None = None
    clients: list[HoldingClientItem] = []


class ManagerMetricsResponse(BaseModel):
    manager_id: UUID
    client_count: int
    total_capital_deployed: float
    total_market_value: float
    total_current_invested: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float
    return_on_capital: float
    weighted_volatility: float | None = None
    weighted_sharpe: float | None = None
    max_drawdown: float | None = None
    as_of: date | None = None
    # Book time-weighted series metrics (R2/R3/R5), decimals (R12). None = not enough data.
    book_total_return: float | None = None
    book_cagr: float | None = None  # None under 365 days (R3)
    book_volatility: float | None = None
    book_sharpe: float | None = None
    book_max_drawdown: float | None = None
    book_current_drawdown: float | None = None
    book_observations: int = 0
    book_series_start: date | None = None
    book_series_end: date | None = None


ClientSummaryResponse.model_rebuild()
