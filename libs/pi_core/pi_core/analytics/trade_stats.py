"""Trade statistics: Profit factor, payoff ratio, and win/loss averages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pi_core.analytics.round_trips import RoundTripSummary


@dataclass(frozen=True)
class TradeStatistics:
    profit_factor: Optional[float]
    payoff_ratio: Optional[float]
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float


def calculate_trade_statistics(summary: RoundTripSummary) -> TradeStatistics:
    """Computes advanced trade statistics from round trip summary."""
    wins = [t.realized_pnl for t in summary.round_trips if t.is_win]
    losses = [abs(t.realized_pnl) for t in summary.round_trips if t.is_loss]

    total_gains = sum(wins)
    total_losses = sum(losses)

    avg_win = (total_gains / len(wins)) if wins else 0.0
    avg_loss = (total_losses / len(losses)) if losses else 0.0

    profit_factor: Optional[float] = None
    if total_losses > 1e-4:
        profit_factor = total_gains / total_losses
    elif total_gains > 1e-4:
        profit_factor = float("inf")

    payoff_ratio: Optional[float] = None
    if avg_loss > 1e-4:
        payoff_ratio = avg_win / avg_loss

    largest_win = max(wins, default=0.0)
    largest_loss = max(losses, default=0.0)

    return TradeStatistics(
        profit_factor=profit_factor,
        payoff_ratio=payoff_ratio,
        average_win=avg_win,
        average_loss=avg_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
    )
