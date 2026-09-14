"""Phase 1 — the factor library for the swing screener's ranking.

The shipped `score_for()` blends 1-week momentum and 1-week relative strength (75% of the
weight between them). Backtesting showed both are anti-predictive: at a 1-week horizon
returns mean-revert (Jegadeesh 1990, Lehmann 1990), so a rank built on them has negative
IC. This module replaces that ranking.

Design rules that come straight from the evidence:

  * **Longer, skip-adjusted momentum, not 1-week.** Momentum works at 3-12 months and
    only after skipping the most recent stretch, to step over short-term reversal
    (Jegadeesh & Titman 1993).
  * **Nearness to the 52-week high** is a stronger, non-reversing predictor than past
    return (George & Hwang 2004).
  * **Volatility earns its place** — as *room to travel* (atr_pct) and as *contraction
    before expansion* (VCP; Minervini). Both tested positive here and in the ORB analysis.
  * **Everything is normalised cross-sectionally before it is combined.** A percent return
    and an RSI point must never sit on the same additive scale again — so each factor
    becomes a z-score (or percentile) across the day's universe, then a weighted sum.

Every function is pure: it takes daily rows (or a list of values) and returns numbers.
No I/O, no clock, no Mongo — the live screen and the backtest call the identical code, so
they cannot drift. Prices in the store are integer paise; helpers here convert to rupees.

Rows are the daily-store shape: {"date": "YYYY-MM-DD", "o","h","l","c": paise, "v": shares}.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev

# Factors whose HIGHER raw value should rank a stock HIGHER. `from_52w_high` is stored as
# a negative "percent below the high" (0 = at the high, -30 = 30% below), so higher (closer
# to zero) is already better — it needs no inversion. atr_contraction is inverted: a
# *smaller* current-vs-past ATR ratio (tighter coil) should rank higher.
DIRECTION = {
    "from_52w": +1,
    "mom_3m": +1,
    "mom_6m": +1,
    "atr_pct": +1,
    "trend_persistence": +1,
    "atr_contraction": -1,   # lower ratio = tighter = better
}

# Starting composite weights. Deliberately concentrated on what tested positive; every
# weight is provisional until the IC gate on the harness confirms sign and stability.
DEFAULT_WEIGHTS = {
    "from_52w": 0.30,
    "mom_6m": 0.20,
    "mom_3m": 0.15,
    "trend_persistence": 0.15,
    "atr_pct": 0.10,
    "atr_contraction": 0.10,
}


# ── per-stock raw factors (point-in-time; feed rows already sliced to <= as_of) ──
def _closes(rows: list[dict]) -> list[float]:
    return [r["c"] / 100 for r in rows if r.get("c") is not None]


def mom_skip(rows: list[dict], lookback: int, skip: int = 5) -> float | None:
    """Cumulative % return over `lookback` sessions ending `skip` sessions ago.

    The skip window steps over the most recent week, where returns reverse rather than
    persist — the single fix that separates real momentum from the 1-week noise the old
    score chased. `lookback`/`skip` are in trading sessions, not calendar days, so
    holidays cannot stretch the window."""
    c = _closes(rows)
    if len(c) < lookback + skip + 1:
        return None
    end = c[-1 - skip]
    start = c[-1 - skip - lookback]
    return (end - start) / start * 100 if start else None


def dist_from_52w(rows: list[dict], window: int = 252) -> float | None:
    """Percent below the trailing 52-week high (0 = at the high, negative below).
    George & Hwang's anchor: nearness to the high predicts continuation and does not
    reverse long-run."""
    c = _closes(rows)
    if len(c) < 2:
        return None
    win = c[-window:]
    hi = max(win)
    return (c[-1] - hi) / hi * 100 if hi else None


def _atr(rows: list[dict], period: int = 14, end: int | None = None) -> float | None:
    """Wilder-style ATR in rupees ending at index `end` (default last row)."""
    n = len(rows)
    end = n - 1 if end is None else end
    if end < period:
        return None
    trs = []
    for i in range(end - period + 1, end + 1):
        h, l, pc = rows[i]["h"] / 100, rows[i]["l"] / 100, rows[i - 1]["c"] / 100
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else None


def atr_pct(rows: list[dict], period: int = 14) -> float | None:
    """ATR as a percent of price — 'room to travel'. Enough daily range to reach a target
    inside a 5-20 day hold. Not a bet that high vol = high return (see the low-vol
    anomaly); a tradability factor that tested positive at longer horizons."""
    a = _atr(rows, period)
    c = _closes(rows)
    return (a / c[-1] * 100) if (a and c and c[-1]) else None


def atr_contraction(rows: list[dict], period: int = 14, ago: int = 60) -> float | None:
    """ATR now ÷ ATR `ago` sessions back. Below 1.0 = the range is coiling (the VCP
    setup). Direction is inverted in DIRECTION so a tighter coil ranks higher."""
    now = _atr(rows, period)
    then = _atr(rows, period, end=len(rows) - 1 - ago)
    return (now / then) if (now and then) else None


def trend_persistence(rows: list[dict], window: int = 50) -> float | None:
    """Fraction of the last `window` sessions that closed above their own DMA50 — a
    steadiness gauge that rewards a durable uptrend over one sharp spike."""
    c = _closes(rows)
    if len(c) < window + 50:
        return None
    above = 0
    for i in range(len(c) - window, len(c)):
        dma50 = sum(c[i - 49:i + 1]) / 50
        if c[i] > dma50:
            above += 1
    return above / window * 100


def adv_rupees(rows: list[dict], days: int = 20) -> float | None:
    """Median daily traded value over `days` sessions, in rupees. The liquidity gate:
    a high rank on an illiquid name is a paper win that slippage erases live."""
    vals = []
    for r in rows[-days:]:
        if r.get("v") and r.get("c") is not None:
            vals.append(r["c"] / 100 * r["v"])
    if not vals:
        return None
    vals.sort()
    return vals[len(vals) // 2]


def raw_factors(rows: list[dict]) -> dict:
    """Every raw (un-normalised) factor for one stock, point-in-time on the rows given."""
    return {
        "from_52w": dist_from_52w(rows),
        "mom_3m": mom_skip(rows, lookback=63, skip=5),
        "mom_6m": mom_skip(rows, lookback=126, skip=5),
        "atr_pct": atr_pct(rows),
        "atr_contraction": atr_contraction(rows),
        "trend_persistence": trend_persistence(rows),
        "adv": adv_rupees(rows),
    }


# ── cross-sectional normalisation ─────────────────────────────────
def zscores(values: list[float | None]) -> list[float | None]:
    """Standardise across the day's universe: (x - mean) / std, computed over the
    non-None values only. None stays None (a missing factor should not become 0, which
    would read as 'exactly average')."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return [None] * len(values)
    mu = mean(present)
    sd = pstdev(present)
    if sd == 0:
        return [0.0 if v is not None else None for v in values]
    return [((v - mu) / sd) if v is not None else None for v in values]


def winsorized_zscores(values: list[float | None], clip: float = 3.0) -> list[float | None]:
    """Z-scores with tails clipped to ±clip, so one runaway name can't dominate the
    composite. Clipping after standardising keeps the threshold in units of sigma."""
    z = zscores(values)
    return [max(-clip, min(clip, v)) if v is not None else None for v in z]


def percentile_ranks(values: list[float | None]) -> list[float | None]:
    """0-100 cross-sectional percentile — an alternative to z-scores that ignores the
    shape of the distribution entirely. The harness can compare both."""
    present = sorted(v for v in values if v is not None)
    n = len(present)
    if n < 2:
        return [None] * len(values)
    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        lo = _bisect_left(present, v)
        hi = _bisect_right(present, v)
        out.append((lo + hi) / 2 / n * 100)
    return out


def _bisect_left(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _bisect_right(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


# ── composite ─────────────────────────────────────────────────────
@dataclass
class Composite:
    """A normalised, weighted ranking built from a universe's raw factors.

    Directionality is applied here (via DIRECTION) so every factor's normalised value
    means 'higher = more bullish' before weighting. A stock missing a factor contributes
    nothing from it, and its weight is renormalised across the factors it does have — so a
    name with a short history is not silently pushed to the middle of every factor."""
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    method: str = "zscore"          # "zscore" | "winsor" | "percentile"

    def _normalise(self, values: list[float | None]) -> list[float | None]:
        if self.method == "percentile":
            return percentile_ranks(values)
        if self.method == "winsor":
            return winsorized_zscores(values)
        return zscores(values)

    def score_universe(self, raw_by_symbol: dict[str, dict]) -> dict[str, float]:
        """raw_by_symbol: {symbol: raw_factors(...)}. Returns {symbol: composite score}."""
        symbols = list(raw_by_symbol)
        factors = [f for f in self.weights if f in DIRECTION]
        norm: dict[str, list[float | None]] = {}
        for f in factors:
            col = [raw_by_symbol[s].get(f) for s in symbols]
            if DIRECTION[f] < 0:
                col = [(-v if v is not None else None) for v in col]
            norm[f] = self._normalise(col)

        out: dict[str, float] = {}
        for i, s in enumerate(symbols):
            num = 0.0
            wsum = 0.0
            for f in factors:
                z = norm[f][i]
                if z is not None:
                    num += self.weights[f] * z
                    wsum += self.weights[f]
            out[s] = (num / wsum) if wsum else 0.0
        return out
