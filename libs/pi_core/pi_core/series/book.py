"""Manager-book time-weighted NAV from client figures (Rules R2, R3, R5, R12, R16).

R5: the book is not re-derived from merged trades. Each client's engine run already
produced, per day, its return ``r_i`` on its capital base ``B_i``; the book's day is

    r_book,t = Σ_i r_i,t · B_i,t / Σ_i B_i,t

i.e. total measured gain over total capital at work, which is exactly the R2 formula on
the union of the clients' measured holdings. Ratios are decimals (R12).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from pi_core.metrics.drawdown import calculate_drawdown_series
from pi_core.metrics.returns import calculate_returns
from pi_core.metrics.risk import DEFAULT_RISK_FREE_RATE, calculate_risk_metrics
from pi_core.models import NAVPoint


def book_nav_series(
    rows: Iterable[tuple[date, float | None, float | None, float]],
    initial_nav: float = 100.0,
) -> list[NAVPoint]:
    """rows: (as_of, day_return, twr_base, market_value) per client per day."""
    gain: dict[date, float] = defaultdict(float)
    base: dict[date, float] = defaultdict(float)
    value: dict[date, float] = defaultdict(float)
    for d, r, b, mv in rows:
        value[d] += max(mv or 0.0, 0.0)
        if r is None or b is None or b < 1.0:
            base[d] += 0.0
            continue
        gain[d] += r * b
        base[d] += b
    days = sorted(value)
    out: list[NAVPoint] = []
    nav = initial_nav
    for i, d in enumerate(days):
        r_t = 0.0
        if i > 0 and base[d] >= 1.0:  # R16: nothing at work → no return
            r_t = gain[d] / base[d]
            if r_t <= -1.0:  # R16: data error, hold flat
                r_t = 0.0
        nav = max(0.01, nav * (1.0 + r_t))
        out.append(NAVPoint(d, nav, r_t, base[d], value[d], 0.0))
    return out


def book_metrics(
    rows: Iterable[tuple[date, float | None, float | None, float]],
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> dict[str, Any]:
    """Book total return, CAGR (None < 365 d), volatility, Sharpe, drawdowns — decimals."""
    nav = book_nav_series(rows)
    ret = calculate_returns(nav)
    risk = calculate_risk_metrics(nav, risk_free_rate=risk_free_rate)
    dd = calculate_drawdown_series(nav)
    return {
        "book_total_return": ret.total_return if ret else None,
        "book_cagr": ret.cagr if ret else None,
        "book_volatility": risk.annualized_volatility,
        "book_sharpe": risk.sharpe_ratio,
        "book_max_drawdown": dd.max_drawdown if dd else None,
        "book_current_drawdown": dd.current_drawdown if dd else None,
        "book_observations": len(nav),
        "book_series_start": nav[0].point_date if nav else None,
        "book_series_end": nav[-1].point_date if nav else None,
    }
