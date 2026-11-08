"""Closed trades: FIFO-matched lots grouped into one trade per sell fill (R7).

A "trade" is one sell execution and every buy lot it consumed. Win rate and the
other trade statistics count these, never individual FIFO lots. Only matched
shares appear here: unmatched sells have no cost basis and are excluded (R7).
Pure: no I/O, no clock.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from pi_core.models import MatchedTrade

EPS = 1e-4


@dataclass(frozen=True)
class ClosedTrade:
    sell_trade_id: str
    buy_trade_ids: tuple[str, ...]
    symbol: str
    exchange: str
    first_buy_date: date
    sell_date: date
    quantity: float
    buy_value: float  # quantity x buy price (gross, as traded: R17)
    sell_value: float  # quantity x sell price (gross)
    cost_basis: float  # buy value + buy charges
    proceeds: float  # sell value - sell charges
    holding_days: float  # quantity-weighted across the consumed lots

    @property
    def pnl(self) -> float:
        return self.proceeds - self.cost_basis

    @property
    def pnl_pct(self) -> float | None:
        """Decimal return on cost (R12); None when the cost is not positive."""
        return self.pnl / self.cost_basis if self.cost_basis > EPS else None

    @property
    def avg_buy_price(self) -> float:
        return self.buy_value / self.quantity if self.quantity > 0 else 0.0

    @property
    def avg_sell_price(self) -> float:
        return self.sell_value / self.quantity if self.quantity > 0 else 0.0

    @property
    def is_win(self) -> bool:
        return self.pnl > EPS

    @property
    def is_loss(self) -> bool:
        return self.pnl < -EPS


def _group(lots: list[MatchedTrade]) -> ClosedTrade:
    first = lots[0]
    qty = sum(m.quantity for m in lots)
    buy_ids: list[str] = []
    for m in lots:
        if m.buy_trade_id not in buy_ids:
            buy_ids.append(m.buy_trade_id)
    days = sum(m.holding_days * m.quantity for m in lots) / qty if qty > 0 else 0.0
    return ClosedTrade(
        sell_trade_id=first.sell_trade_id,
        buy_trade_ids=tuple(buy_ids),
        symbol=first.symbol,
        exchange=first.exchange,
        first_buy_date=min(m.buy_date for m in lots),
        sell_date=max(m.sell_date for m in lots),
        quantity=qty,
        buy_value=sum(m.quantity * m.buy_price for m in lots),
        sell_value=sum(m.quantity * m.sell_price for m in lots),
        cost_basis=sum(m.cost_basis for m in lots),
        proceeds=sum(m.proceeds for m in lots),
        holding_days=days,
    )


def closed_trades_from_matches(matched: Iterable[MatchedTrade]) -> list[ClosedTrade]:
    """Groups matched lots by sell fill; ordered by (sell_date, sell_trade_id)."""
    grouped: dict[str, list[MatchedTrade]] = defaultdict(list)
    for m in matched:
        if m.quantity > 0:
            grouped[m.sell_trade_id].append(m)
    trades = [_group(lots) for lots in grouped.values()]
    trades.sort(key=lambda t: (t.sell_date, t.sell_trade_id))
    return trades
