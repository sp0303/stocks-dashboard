"""Portfolio concentration analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ConcentrationMetrics:
    top_5_weight: float
    top_10_weight: float
    herfindahl_index: float
    holdings_count: int


def calculate_concentration(position_market_values: Dict[Tuple[str, str], float]) -> ConcentrationMetrics:
    """Computes concentration metrics from open position market values."""
    positive_values = [v for v in position_market_values.values() if v > 0]
    total_mv = sum(positive_values)

    if total_mv <= 0.0 or not positive_values:
        return ConcentrationMetrics(
            top_5_weight=0.0,
            top_10_weight=0.0,
            herfindahl_index=0.0,
            holdings_count=0,
        )

    weights = sorted([v / total_mv for v in positive_values], reverse=True)

    top_5 = sum(weights[:5])
    top_10 = sum(weights[:10])
    hhi = sum(w ** 2 for w in weights)  # Range 0.0 to 1.0

    return ConcentrationMetrics(
        top_5_weight=top_5,
        top_10_weight=top_10,
        herfindahl_index=hhi,
        holdings_count=len(positive_values),
    )
