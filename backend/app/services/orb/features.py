"""Derived series: VWAP, ATR, the opening range, relative-volume baselines.

Pure functions over lists of bars. No pandas — a full session is 375 bars and the whole
two-year sweep runs in seconds in plain Python, so the dependency would buy nothing and
cost the live path an import.

Two look-ahead rules are enforced here rather than left to the caller, because both are
easy to violate by accident and impossible to see afterwards in the results:
  * ATR is computed from *completed prior sessions* only — never today's bar.
  * RVOL baselines are medians over prior sessions only.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.services.orb.bars import Bar
from app.services.orb.session import MARKET_OPEN, OR_END


# ── VWAP ──────────────────────────────────────────────────────────
class Vwap:
    """Session-anchored VWAP, fed one bar at a time. Typical price is (h+l+c)/3 on the
    1-minute bar — the closest we get to tick VWAP without storing every trade."""

    def __init__(self) -> None:
        self._pv = 0.0
        self._v = 0
        self.history: list[tuple[int, int]] = []   # (minute, vwap in paise)

    def add(self, bar: Bar) -> int | None:
        if bar.v > 0:
            self._pv += ((bar.h + bar.l + bar.c) / 3.0) * bar.v
            self._v += bar.v
        val = self.value
        if val is not None:
            self.history.append((bar.minute, val))
        return val

    @property
    def value(self) -> int | None:
        return int(round(self._pv / self._v)) if self._v else None

    def at_or_before(self, minute: int) -> int | None:
        best = None
        for m, val in self.history:
            if m <= minute:
                best = val
            else:
                break
        return best

    def slope_pct(self, minute: int, lookback_min: int) -> float | None:
        """Percentage change in VWAP over the lookback window. 'Sloping upward' is not
        a computable rule; this is."""
        now = self.at_or_before(minute)
        then = self.at_or_before(minute - lookback_min)
        if not now or not then:
            return None
        return (now - then) / now * 100.0


def vwap_series(bars: list[Bar]) -> Vwap:
    v = Vwap()
    for b in bars:
        v.add(b)
    return v


# ── opening range ─────────────────────────────────────────────────
@dataclass(frozen=True)
class OpeningRange:
    high: int
    low: int
    mid: int
    width: int
    volume: int
    turnover: float          # rupees
    bars: int
    complete: bool

    @property
    def width_pct(self) -> float:
        return (self.width / self.mid * 100.0) if self.mid else 0.0


def opening_range(bars: list[Bar]) -> OpeningRange | None:
    """[09:15, 09:30). Synthetic (no-trade) minutes contribute their carried price to the
    range but nothing to volume, which is correct: the price was real, the volume wasn't."""
    window = [b for b in bars if MARKET_OPEN <= b.minute < OR_END]
    if not window:
        return None
    real = [b for b in window if not b.syn]
    if not real:
        return None
    hi = max(b.h for b in window)
    lo = min(b.l for b in window)
    vol = sum(b.v for b in window)
    turn = sum(((b.h + b.l + b.c) / 3.0) * b.v for b in window) / 100.0   # paise -> rupees
    mid = (hi + lo) // 2
    return OpeningRange(high=hi, low=lo, mid=mid, width=hi - lo, volume=vol,
                        turnover=turn, bars=len(window),
                        complete=len(window) == (OR_END - MARKET_OPEN))


# ── resampling ────────────────────────────────────────────────────
@dataclass(frozen=True)
class Bar5:
    start: int               # first minute included
    end: int                 # minute at which the bar closed (exclusive of its own data)
    o: int
    h: int
    l: int
    c: int
    v: int
    syn_count: int

    @property
    def range(self) -> int:
        return self.h - self.l

    def close_strength(self, side: int) -> float:
        """1.0 = closed at the extreme in the trade's favour, 0.0 = against it."""
        if self.range <= 0:
            return 1.0
        return ((self.c - self.l) if side > 0 else (self.h - self.c)) / self.range


def resample(bars: list[Bar], minutes: int = 5, anchor: int = MARKET_OPEN) -> list[Bar5]:
    """Group 1-minute bars into fixed buckets anchored at the open, so a 5-minute bar
    closes at 09:20, 09:25, … 09:35 — the first one that can act on a breakout."""
    buckets: dict[int, list[Bar]] = {}
    for b in bars:
        if b.minute < anchor:
            continue
        buckets.setdefault(anchor + ((b.minute - anchor) // minutes) * minutes, []).append(b)
    out = []
    for start in sorted(buckets):
        grp = sorted(buckets[start], key=lambda x: x.minute)
        out.append(Bar5(start=start, end=start + minutes, o=grp[0].o,
                        h=max(x.h for x in grp), l=min(x.l for x in grp), c=grp[-1].c,
                        v=sum(x.v for x in grp),
                        syn_count=sum(1 for x in grp if x.syn)))
    return out


# ── daily-derived context ─────────────────────────────────────────
@dataclass(frozen=True)
class DailyBar:
    date: str
    o: int
    h: int
    l: int
    c: int
    v: int


def atr(daily: list[DailyBar], period: int = 14) -> float | None:
    """Wilder's ATR in paise over *completed prior sessions*. Pass only bars up to
    yesterday: including today leaks the future into gate B2."""
    if len(daily) < period + 1:
        return None
    trs = []
    for prev, cur in zip(daily, daily[1:]):
        trs.append(max(cur.h - cur.l, abs(cur.h - prev.c), abs(cur.l - prev.c)))
    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = (val * (period - 1) + tr) / period
    return val


def median_or_volume(prior_or_volumes: list[int]) -> float | None:
    """Median, not mean: one results-day spike should not set the bar for a fortnight."""
    vals = [v for v in prior_or_volumes if v > 0]
    return median(vals) if vals else None


def cumulative_volume_curve(bars: list[Bar]) -> dict[int, int]:
    """{minute: cumulative volume up to and including that minute} for one session."""
    out, run = {}, 0
    for b in sorted(bars, key=lambda x: x.minute):
        run += b.v
        out[b.minute] = run
    return out


def median_cum_volume_at(curves: list[dict[int, int]], minute: int) -> float | None:
    """Time-of-day normalised baseline: what a typical prior session had traded by now."""
    vals = [c[minute] for c in curves if minute in c and c[minute] > 0]
    return median(vals) if vals else None


def gap_pct(open_price: int, prev_close: int) -> float | None:
    """Measured off the 09:15 open against yesterday's close — known at 09:15:01, which
    is why this system needs no pre-open feed (Angel does not provide one anyway)."""
    if not prev_close:
        return None
    return (open_price - prev_close) / prev_close * 100.0
