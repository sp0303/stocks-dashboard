"""Round trips and trade-level win rate adhering to Rule R167."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from pi_core.models import MatchedTrade


@dataclass(frozen=True)
class TradeRoundTrip:
    sell_trade_id: str
    symbol: str
    exchange: str
    total_quantity: float
    total_cost_basis: float
    total_proceeds: float
    realized_pnl: float
    average_holding_days: float

    @property
    def is_win(self) -> bool:
        return self.realized_pnl > 1e-4

    @property
    def is_loss(self) -> bool:
        return self.realized_pnl < -1e-4


@dataclass(frozen=True)
class RoundTripSummary:
    total_trades_count: int
    winning_trades_count: int
    losing_trades_count: int
    breakeven_trades_count: int
    win_rate: float  # wins / total_trades (Rule R167)
    total_realized_pnl: float
    average_holding_days: float
    round_trips: List[TradeRoundTrip]


def calculate_round_trips(matched_lots: List[MatchedTrade]) -> RoundTripSummary:
    """Aggregates FIFO matched lots by distinct sell_trade_id into discrete trade round trips.

    Rule R167: Win rate = wins ÷ trades (not FIFO lots); ₹0 P&L is neither a win nor a loss.
    """
    if not matched_lots:
        return RoundTripSummary(
            total_trades_count=0,
            winning_trades_count=0,
            losing_trades_count=0,
            breakeven_trades_count=0,
            win_rate=0.0,
            total_realized_pnl=0.0,
            average_holding_days=0.0,
            round_trips=[],
        )

    # Group lots by sell_trade_id
    grouped = defaultdict(list)
    for m in matched_lots:
        grouped[m.sell_trade_id].append(m)

    trips: List[TradeRoundTrip] = []

    for sell_id, lots in grouped.items():
        first = lots[0]
        tot_qty = sum(l.quantity for l in lots)
        tot_cost = sum(l.cost_basis for l in lots)
        tot_proceeds = sum(l.proceeds for l in lots)
        pnl = tot_proceeds - tot_cost

        # Weighted average holding days by quantity
        avg_days = sum(l.holding_days * l.quantity for l in lots) / tot_qty if tot_qty > 0 else 0.0

        trips.append(
            TradeRoundTrip(
                sell_trade_id=sell_id,
                symbol=first.symbol,
                exchange=first.exchange,
                total_quantity=tot_qty,
                total_cost_basis=tot_cost,
                total_proceeds=tot_proceeds,
                realized_pnl=pnl,
                average_holding_days=avg_days,
            )
        )

    wins = sum(1 for t in trips if t.is_win)
    losses = sum(1 for t in trips if t.is_loss)
    breakeven = len(trips) - wins - losses
    win_rate = (wins / len(trips)) if trips else 0.0
    tot_pnl = sum(t.realized_pnl for t in trips)
    overall_avg_days = sum(t.average_holding_days for t in trips) / len(trips) if trips else 0.0

    return RoundTripSummary(
        total_trades_count=len(trips),
        winning_trades_count=wins,
        losing_trades_count=losses,
        breakeven_trades_count=breakeven,
        win_rate=win_rate,
        total_realized_pnl=tot_pnl,
        average_holding_days=overall_avg_days,
        round_trips=trips,
    )
