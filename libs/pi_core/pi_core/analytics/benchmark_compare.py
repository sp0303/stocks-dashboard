"""Benchmark comparison on the portfolio's own net_invested baseline (R10) + beta/alpha.

Index-units method, driven by the client's daily net_invested series (R11 calendar):
    flow_t   = net_invested_t - net_invested_{t-1}
    units_t += flow_t / P_t ;  value_t = units_t * P_t ;  pnl_t = value_t - net_invested_t
Dead-ticker guard: a level is carried over at most MAX_STALE_SESSIONS sessions. Past
that the benchmark P&L is None (the line stops; it never flatlines) and ``stale`` is
raised so the UI alarms. Pure: no I/O, no clock.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from pi_core.metrics.returns import calculate_returns
from pi_core.metrics.risk import calculate_risk_metrics
from pi_core.models import BenchmarkPoint, NAVPoint

MAX_STALE_SESSIONS = 2


def _first_level_from(levels: Mapping[date, float], known: list[date], d: date) -> float | None:
    i = bisect_left(known, d)
    return levels[known[i]] if i < len(known) else None


def benchmark_track(
    days: Sequence[date], net_invested: Sequence[float], levels: Mapping[date, float]
) -> dict[str, Any]:
    """Benchmark P&L per day (None where the index is missing or stale) + freshness flags."""
    known = sorted(d for d, v in levels.items() if v and v > 0)
    pnl: list[float | None] = []
    units, prev_ni, last_p, gap, plotted = 0.0, 0.0, None, 0, []
    for d, ni in zip(days, net_invested):
        if d in levels and levels[d] > 0:
            last_p, gap = levels[d], 0
        else:
            gap += 1
        p = last_p if last_p is not None else _first_level_from(levels, known, d)
        if p is not None:
            units += (ni - prev_ni) / p
        prev_ni = ni
        if last_p is None or gap > MAX_STALE_SESSIONS:
            pnl.append(None)
            continue
        pnl.append(units * last_p - ni)
        plotted.append(last_p)
    last_index_date = known[-1] if known else None
    behind = sum(1 for d in days if last_index_date is None or d > last_index_date)
    return {
        "pnl": pnl,
        "last_index_date": last_index_date.isoformat() if last_index_date else None,
        "sessions_behind": behind,
        "stale": last_index_date is None or behind > MAX_STALE_SESSIONS,
        "index_return": plotted[-1] / plotted[0] - 1.0 if len(plotted) >= 2 else None,
        "start_backfilled": bool(days) and bool(known) and known[0] > days[0],
    }


def nav_points(days: Sequence[date], navs: Sequence[float], day_returns: Sequence[float | None]) -> list[NAVPoint]:
    return [
        NAVPoint(d, nav, r if r is not None else 0.0, 0.0, 0.0, 0.0)
        for d, nav, r in zip(days, navs, day_returns)
    ]


def beta_alpha(nav: Sequence[NAVPoint], levels: Mapping[date, float]) -> dict[str, Any]:
    """Date-aligned beta and Jensen's alpha via pi_core's risk engine (one code path, R5).

    Only days with a real index print are used: carried levels would fake 0 % returns.
    """
    if not nav:
        return {"beta": None, "alpha": None}
    first, last = nav[0].point_date, nav[-1].point_date
    bench = [
        BenchmarkPoint(d, 0.0, levels[d], 0.0, 0.0, 0.0)
        for d in sorted(levels)
        if first <= d <= last and levels[d] > 0
    ]
    risk = calculate_risk_metrics(list(nav), benchmark_series=bench)
    return {"beta": risk.beta, "alpha": risk.alpha}


def portfolio_returns(nav: Sequence[NAVPoint]) -> dict[str, Any]:
    """Total TWR return and CAGR (None under 365 days, R3) from the same NAV series."""
    r = calculate_returns(list(nav))
    return {
        "total_return": r.total_return if r else None,
        "cagr": r.cagr if r else None,
        "days": r.total_days if r else 0,
    }
