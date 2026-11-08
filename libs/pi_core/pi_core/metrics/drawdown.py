"""Drawdown series and peak-to-trough analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from pi_core.models import NAVPoint


@dataclass(frozen=True)
class DrawdownSummary:
    max_drawdown: float
    current_drawdown: float
    peak_date: Optional[date]
    trough_date: Optional[date]
    drawdown_series: List[Tuple[date, float]]


def calculate_drawdown_series(nav_series: List[NAVPoint]) -> Optional[DrawdownSummary]:
    """Calculates drawdown series and maximum peak-to-trough drop."""
    if not nav_series:
        return None

    running_peak = nav_series[0].nav
    running_peak_date = nav_series[0].point_date

    max_dd = 0.0
    best_peak_date: Optional[date] = running_peak_date
    worst_trough_date: Optional[date] = running_peak_date

    series: List[Tuple[date, float]] = []

    for pt in nav_series:
        if pt.nav > running_peak:
            running_peak = pt.nav
            running_peak_date = pt.point_date

        dd = (pt.nav - running_peak) / running_peak if running_peak > 0 else 0.0
        # Sanity bound: cannot lose more than 100% of capital (Rule R16)
        dd = max(-1.0, min(0.0, dd))
        series.append((pt.point_date, dd))

        if dd < max_dd:
            max_dd = dd
            best_peak_date = running_peak_date
            worst_trough_date = pt.point_date

    current_dd = series[-1][1] if series else 0.0

    return DrawdownSummary(
        max_drawdown=max_dd,
        current_drawdown=current_dd,
        peak_date=best_peak_date,
        trough_date=worst_trough_date,
        drawdown_series=series,
    )
