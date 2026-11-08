"""Capital deployed, current invested, and return on capital metrics (Rule R1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pi_core.models import DailySnapshot


@dataclass(frozen=True)
class CapitalMetrics:
    capital_deployed: float
    current_invested: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    return_on_capital: float


def calculate_capital_metrics(snapshots: List[DailySnapshot]) -> Optional[CapitalMetrics]:
    """Computes capital deployed, current invested, and true return on capital per Rule R1."""
    if not snapshots:
        return None

    latest = snapshots[-1]
    cap_deployed = latest.capital_deployed
    curr_invested = latest.open_cost
    mv = latest.market_value
    realized = latest.realized_pnl_cumulative
    unrealized = latest.unrealized_pnl
    total_pnl = realized + unrealized

    roc = (total_pnl / cap_deployed) if cap_deployed > 1.0 else 0.0

    return CapitalMetrics(
        capital_deployed=cap_deployed,
        current_invested=curr_invested,
        market_value=mv,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_pnl=total_pnl,
        return_on_capital=roc,
    )
