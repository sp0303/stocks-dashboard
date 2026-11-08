"""Benchmark PME (Public Market Equivalent) series calculation adhering to Rule R10."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import date

from pi_core.models import BenchmarkPoint, DailySnapshot, Side, Trade


def calculate_benchmark_pme(
    snapshots: List[DailySnapshot],
    trades: List[Trade],
    index_price_by_date: Dict[date, float],
    benchmark_name: str = "Nifty 50",
) -> Tuple[List[BenchmarkPoint], List[str]]:
    """Calculates index-units benchmark curve matched to portfolio cash flows.

    Formula (Rule R10):
        buy  amount at index level P:  units += amount / P
        sell amount at index level P:  units -= amount / P
        value_t = units_t · P_t
        pnl_t   = value_t − net_invested_t
    """
    if not snapshots:
        return [], []

    warnings: List[str] = []
    points: List[BenchmarkPoint] = []

    # Map net trades cash flow per day
    day_flows: Dict[date, float] = {}
    for snap in snapshots:
        day_flows[snap.snapshot_date] = snap.net_cash_flow

    units = 0.0
    net_invested = 0.0
    last_known_p = 1000.0  # fallback baseline

    # Dead-ticker guard check (Rule R10)
    if index_price_by_date:
        latest_calendar_date = max(snapshots, key=lambda s: s.snapshot_date).snapshot_date
        latest_index_date = max(index_price_by_date.keys())
        if (latest_calendar_date - latest_index_date).days > 4:
            warnings.append(
                f"Dead-ticker guard: Benchmark {benchmark_name} stopped on {latest_index_date}, "
                f"which is behind calendar {latest_calendar_date}."
            )

    for snap in snapshots:
        d = snap.snapshot_date
        p = index_price_by_date.get(d, last_known_p)
        last_known_p = p

        flow = day_flows.get(d, 0.0)
        net_invested += flow

        if p > 0:
            units += flow / p

        market_val = units * p
        pnl = market_val - net_invested

        points.append(
            BenchmarkPoint(
                point_date=d,
                units=units,
                index_level=p,
                market_value=market_val,
                net_invested=net_invested,
                pnl=pnl,
            )
        )

    return points, warnings
