"""Core data structures and types for Portfolio Intelligence v2.

Adheres strictly to docs/v2/DOMAIN-RULES.md.
Pure domain structures: immutable, serializable, zero I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Segment(str, Enum):
    EQUITY = "EQ"
    INTRADAY = "INTRADAY"
    DERIVATIVE = "FO"


class ActionType(str, Enum):
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    DIVIDEND = "DIVIDEND"
    DEMERGER = "DEMERGER"
    MERGER = "MERGER"
    RIGHTS = "RIGHTS"
    BUYBACK = "BUYBACK"
    OTHER = "OTHER"  # unknown type from the feed: stored and warned about, never ignored (R8)


@dataclass(frozen=True)
class Trade:
    """Individual trade fill from broker ledger."""

    trade_id: str
    trade_date: date
    symbol: str
    exchange: str
    side: Side
    quantity: float
    price: float
    charges: float | None = None
    segment: Segment = Segment.EQUITY
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def gross_amount(self) -> float:
        return self.quantity * self.price

    @property
    def net_amount(self) -> float:
        chg = self.charges if self.charges is not None else 0.0
        if self.side == Side.BUY:
            return self.gross_amount + chg
        return self.gross_amount - chg


@dataclass(frozen=True)
class CorporateAction:
    """Corporate action event applied on ex-date before same-day trades."""

    symbol: str
    action_type: ActionType
    ex_date: date
    ratio_from: float
    ratio_to: float

    @property
    def multiplier(self) -> float:
        """Ratio applied to quantities (e.g. 1:5 split ratio_to=5, ratio_from=1 -> 5.0)."""
        if self.ratio_from <= 0:
            return 1.0
        return self.ratio_to / self.ratio_from


@dataclass
class Lot:
    """Open holding lot held in inventory."""

    lot_id: str
    buy_date: date
    symbol: str
    exchange: str
    quantity: float
    original_quantity: float
    price: float
    charges_per_unit: float = 0.0

    @property
    def unit_cost(self) -> float:
        return self.price + self.charges_per_unit

    @property
    def total_cost(self) -> float:
        return self.quantity * self.unit_cost


@dataclass(frozen=True)
class MatchedTrade:
    """Realized sell matched against an open buy lot (Rule R7)."""

    sell_trade_id: str
    buy_trade_id: str
    symbol: str
    exchange: str
    buy_date: date
    sell_date: date
    quantity: float
    buy_price: float
    sell_price: float
    buy_charges: float
    sell_charges: float

    @property
    def cost_basis(self) -> float:
        return (self.quantity * self.buy_price) + self.buy_charges

    @property
    def proceeds(self) -> float:
        return (self.quantity * self.sell_price) - self.sell_charges

    @property
    def realized_pnl(self) -> float:
        return self.proceeds - self.cost_basis

    @property
    def holding_days(self) -> int:
        return (self.sell_date - self.buy_date).days


@dataclass(frozen=True)
class UnmatchedSell:
    """Sell with missing buy allotment (Rule R7)."""

    trade_id: str
    trade_date: date
    symbol: str
    exchange: str
    quantity: float
    sell_price: float
    proceeds: float


@dataclass(frozen=True)
class PositionMark:
    """End-of-day state of one (symbol, exchange) holding, as the engine saw it.

    ``price`` is None when the holding had no usable close that day (R6): it is then
    outside both cost and market value. ``flow`` is the day's cash attributed to this
    key (buys + charges − matched sell proceeds); ``buys``/``sells`` are the day's
    (quantity, execution price) legs; ``prev_price`` is the close on the previous
    session, looked up only when the key traded. The TWR series (R2) is built from these.
    """

    quantity: float
    cost: float
    price: float | None
    flow: float = 0.0
    buys: tuple[tuple[float, float], ...] = ()
    sells: tuple[tuple[float, float], ...] = ()
    prev_price: float | None = None

    @property
    def is_open(self) -> bool:
        return self.quantity > 1e-6

    @property
    def priced(self) -> bool:
        return self.price is not None and self.price > 0

    @property
    def value(self) -> float:
        """Market value; 0 when closed or unpriced (an unpriced holding is excluded, R6)."""
        return self.quantity * self.price if self.is_open and self.priced else 0.0  # type: ignore[operator]


@dataclass
class DailySnapshot:
    """Portfolio state at the end of a given calendar market session.

    ``open_cost`` and ``market_value`` cover **priced** holdings only (R6.4); the cost of
    holdings with no usable price is in ``unpriced_cost`` and their keys in ``unpriced``.
    """

    snapshot_date: date
    open_cost: float
    market_value: float
    realized_pnl_cumulative: float
    unrealized_pnl: float
    capital_deployed: float
    net_cash_flow: float
    open_positions_count: int
    unmatched_sells_value: float = 0.0
    unpriced_cost: float = 0.0
    unpriced: tuple[tuple[str, str], ...] = ()
    marks: dict[tuple[str, str], PositionMark] = field(default_factory=dict)

    @property
    def total_pnl(self) -> float:
        """Chart identity: Total PnL = Realized + Unrealized (Rule R7)."""
        return self.realized_pnl_cumulative + self.unrealized_pnl


@dataclass(frozen=True)
class NAVPoint:
    """Time-weighted NAV and performance point on a given market date (Rule R2)."""

    point_date: date
    nav: float
    daily_return: float
    capital_base: float
    market_value: float
    net_flow: float


@dataclass(frozen=True)
class BenchmarkPoint:
    """Index-units benchmark tracking point aligned to portfolio (Rule R10)."""

    point_date: date
    units: float
    index_level: float
    market_value: float
    net_invested: float
    pnl: float
