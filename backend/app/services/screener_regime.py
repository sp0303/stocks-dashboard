"""Momentum crash protection — continuous volatility scaling (Barroso & Santa-Clara 2015,
*Momentum Has Its Moments*; related: Daniel & Moskowitz 2016, *Momentum Crashes*).

The finding the swing book kept running into: momentum's edge is real for years, then a chunk
reverses violently — and the crashes cluster in *high realized-volatility* regimes (the panic
rebounds where beaten-down names rip and prior winners collapse). Our Phase-2 breakout book's
second-half decay is exactly this profile, and a binary breadth gate is too coarse to catch it.

Barroso & Santa-Clara's fix is continuous, not binary: target a constant strategy volatility
by scaling exposure to `target / recent_realized_vol`. When trailing volatility spikes, the
scale falls below 1 and the book de-risks *before* the crash; when it is calm, the scale rises
toward its cap. This roughly doubled momentum's Sharpe and removed the worst drawdowns in their
sample — using only past data at each point.

Everything here is pure arithmetic on a return series; the scale decision at time t uses only
returns up to t. The volatility *target* is a normalising constant (it sets average leverage,
not the timing) — pass a fixed one, or calibrate it to the series' own median so average
exposure ≈ 1 and the effect is pure redistribution from turbulent to calm periods.
"""
from __future__ import annotations

from statistics import median, pstdev


def realized_vol(returns: list[float], lookback: int = 63) -> float | None:
    """Trailing realized volatility = population stdev of the last `lookback` daily returns.
    None until there are enough observations. Uses only the window ending 'now'."""
    if len(returns) < max(5, lookback // 4):
        return None
    window = returns[-lookback:]
    return pstdev(window) if len(window) >= 2 else None


def vol_scale(rv: float | None, target: float, cap: float = 2.5, floor: float = 0.0) -> float:
    """Exposure multiplier `target / rv`, clamped to [floor, cap]. rv is trailing realized
    vol; target is the constant vol we aim to hold. High trailing vol → scale < 1 (de-risk);
    calm → scale toward cap. Unknown/zero vol falls back to the cap (calm assumption is not
    made — we only reach here with too little data, so treat as neutral 1.0)."""
    if rv is None:
        return 1.0
    if rv <= 0:
        return cap
    return max(floor, min(cap, target / rv))


def calibrate_target(rv_series: list[float]) -> float | None:
    """A normalising target = the median of the realized-vol series, so the average scale is
    ~1 and vol-scaling redistributes exposure across regimes rather than adding net leverage.
    This uses the whole series and so is a *calibration constant*, not a trading input — the
    per-date timing in `vol_scale` still uses only trailing data."""
    vals = [v for v in rv_series if v and v > 0]
    return median(vals) if vals else None


def exposure_multiplier(market_returns: list[float], *, target: float | None = None,
                        lookback: int = 63, cap: float = 2.5) -> float:
    """Convenience for the live book: given the market's recent daily returns, return the
    exposure multiplier to apply to risk budget / position size right now. Without a `target`,
    a neutral 1.0 is returned (a target must be set from history to have meaning)."""
    rv = realized_vol(market_returns, lookback)
    if target is None or rv is None:
        return 1.0
    return vol_scale(rv, target, cap)
