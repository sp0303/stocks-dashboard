"""Returns and CAGR calculation adhering to Rule R3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pi_core.models import NAVPoint


@dataclass(frozen=True)
class ReturnsSummary:
    total_return: float
    cagr: Optional[float]
    total_days: int
    is_annualized: bool


def calculate_returns(nav_series: List[NAVPoint]) -> Optional[ReturnsSummary]:
    """Calculates total return and CAGR per Rule R3.

    CAGR is strictly suppressed (returns None) if total_days < 365 (GIPS standard).
    """
    if not nav_series or len(nav_series) < 1:
        return None

    first = nav_series[0]
    last = nav_series[-1]

    if first.nav <= 0.0:
        return None

    total_return = (last.nav / first.nav) - 1.0
    total_days = (last.point_date - first.point_date).days

    cagr: Optional[float] = None
    if total_days >= 365 and last.nav > 0:
        cagr = (last.nav / first.nav) ** (365.25 / total_days) - 1.0

    return ReturnsSummary(
        total_return=total_return,
        cagr=cagr,
        total_days=total_days,
        is_annualized=(cagr is not None),
    )
