"""Risk metrics calculation: Volatility, Sharpe, Beta, Jensen's Alpha (Rule R3)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from pi_core.models import BenchmarkPoint, NAVPoint

DEFAULT_RISK_FREE_RATE = 0.065  # 6.5% constant (Rule R3)


@dataclass(frozen=True)
class RiskSummary:
    annualized_volatility: Optional[float]
    sharpe_ratio: Optional[float]
    beta: Optional[float]
    alpha: Optional[float]
    observations_count: int


def calculate_risk_metrics(
    nav_series: List[NAVPoint],
    benchmark_series: Optional[List[BenchmarkPoint]] = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> RiskSummary:
    """Computes volatility, Sharpe, Beta, and Alpha per Rule R3.

    Sharpe is computed from daily excess returns: mean(r - rf/252) / stdev(r) * sqrt(252).
    Beta is date-aligned with benchmark observations.
    """
    # Exclude day 0 (which has return 0.0)
    daily_returns = [pt.daily_return for pt in nav_series[1:]]
    n = len(daily_returns)

    if n < 2:
        return RiskSummary(
            annualized_volatility=None,
            sharpe_ratio=None,
            beta=None,
            alpha=None,
            observations_count=n,
        )

    # Volatility = stdev(r) * sqrt(252)
    mean_r = sum(daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (n - 1)
    stdev = math.sqrt(variance)
    annualized_vol = stdev * math.sqrt(252)

    # Sharpe ratio
    daily_rf = risk_free_rate / 252.0
    excess_returns = [r - daily_rf for r in daily_returns]
    mean_excess = sum(excess_returns) / n
    sharpe: Optional[float] = None
    if stdev > 1e-7:
        sharpe = (mean_excess / stdev) * math.sqrt(252)

    # Date-aligned Beta and Jensen's Alpha
    beta: Optional[float] = None
    alpha: Optional[float] = None

    if benchmark_series and len(benchmark_series) > 2:
        # Build benchmark daily returns
        bm_returns_by_date: Dict[date, float] = {}
        for i in range(1, len(benchmark_series)):
            p_prev = benchmark_series[i - 1].index_level
            p_curr = benchmark_series[i].index_level
            if p_prev > 0:
                bm_returns_by_date[benchmark_series[i].point_date] = (p_curr / p_prev) - 1.0

        # Date alignment
        aligned_p: List[float] = []
        aligned_b: List[float] = []

        for pt in nav_series[1:]:
            if pt.point_date in bm_returns_by_date:
                aligned_p.append(pt.daily_return)
                aligned_b.append(bm_returns_by_date[pt.point_date])

        n_aligned = len(aligned_p)
        if n_aligned >= 5:
            mean_p = sum(aligned_p) / n_aligned
            mean_b = sum(aligned_b) / n_aligned
            var_b = sum((b - mean_b) ** 2 for b in aligned_b) / (n_aligned - 1)
            cov_pb = sum((aligned_p[k] - mean_p) * (aligned_b[k] - mean_b) for k in range(n_aligned)) / (n_aligned - 1)

            if var_b > 1e-8:
                beta = cov_pb / var_b

                # Annualized total returns for Jensen's Alpha: R_p - [rf + β(R_b - rf)]
                ann_p = mean_p * 252
                ann_b = mean_b * 252
                alpha = ann_p - (risk_free_rate + beta * (ann_b - risk_free_rate))

    return RiskSummary(
        annualized_volatility=annualized_vol,
        sharpe_ratio=sharpe,
        beta=beta,
        alpha=alpha,
        observations_count=n,
    )
