"""Phase 1 factor library. The point of these is to pin the two things easiest to get
wrong: the skip window in momentum, and normalisation that treats missing data as
'average'. Every test is pure — no Mongo, no network.
"""
import math

from app.services import screener_factors as F


def series(closes, highs=None, lows=None, vols=None):
    """Build daily-store rows (paise) from a close series."""
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    vols = vols or [100000] * n
    return [{"date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "o": int(closes[i] * 100), "h": int(highs[i] * 100),
             "l": int(lows[i] * 100), "c": int(closes[i] * 100), "v": vols[i]}
            for i in range(n)]


# ── momentum + skip window ────────────────────────────────────────
def test_mom_skip_measures_the_window_that_ends_before_the_skip():
    # Flat for a long time, then a sharp +10% only in the last 5 sessions.
    closes = [100.0] * 200 + [100.0] * 5
    closes[-5:] = [110.0] * 5
    rows = series(closes)
    # 3M momentum skips the last 5 sessions, so it should NOT see the recent spike.
    assert abs(F.mom_skip(rows, lookback=63, skip=5)) < 0.01


def test_mom_skip_captures_a_move_inside_its_window():
    closes = [100.0] * 140 + [x for x in _ramp(100.0, 120.0, 60)] + [120.0] * 5
    rows = series(closes)
    m3 = F.mom_skip(rows, lookback=63, skip=5)
    assert m3 is not None and m3 > 10          # the ramp is inside the 3M-skip window


def test_mom_skip_needs_enough_history():
    assert F.mom_skip(series([100.0] * 30), lookback=63, skip=5) is None


# ── Frog-in-the-Pan (information discreteness) ─────────────────────
def test_fip_smooth_uptrend_scores_lower_than_choppy():
    # Smooth: every day up → all positive days → ID = sign(+)·(0 − 1) = -1 (max quality).
    smooth = [100.0 + i * 0.5 for i in range(140)]
    # Choppy but net up: +2,-1 repeating → both signs present, ID near 0 (discrete).
    choppy = [100.0]
    for i in range(139):
        choppy.append(choppy[-1] + (2.0 if i % 2 == 0 else -1.0))
    assert F.fip(series(smooth)) == -1.0
    assert F.fip(series(smooth)) < F.fip(series(choppy))     # continuous < discrete


def test_fip_needs_enough_history():
    assert F.fip(series([100.0] * 40)) is None


# ── 52-week high ──────────────────────────────────────────────────
def test_dist_from_52w_high_is_zero_at_the_high_and_negative_below():
    at_high = series([x for x in _ramp(100.0, 200.0, 260)])
    assert abs(F.dist_from_52w(at_high)) < 0.01
    pulled_back = series([x for x in _ramp(100.0, 200.0, 260)] + [160.0])
    d = F.dist_from_52w(pulled_back)
    assert d is not None and -21 < d < -19      # ~20% below the 200 high


# ── ATR factors ───────────────────────────────────────────────────
def test_atr_pct_scales_with_range():
    tight = series([100.0] * 60, highs=[100.5] * 60, lows=[99.5] * 60)
    wide = series([100.0] * 60, highs=[103.0] * 60, lows=[97.0] * 60)
    assert F.atr_pct(wide) > F.atr_pct(tight)


def test_atr_contraction_below_one_when_range_is_coiling():
    # Wide for the first 60 sessions, then tight for the last 20.
    highs = [106.0] * 60 + [100.5] * 20
    lows = [94.0] * 60 + [99.5] * 20
    rows = series([100.0] * 80, highs=highs, lows=lows)
    ratio = F.atr_contraction(rows, ago=60)
    assert ratio is not None and ratio < 1.0     # coiling


def test_atr_contraction_direction_is_inverted_so_tighter_ranks_higher():
    assert F.DIRECTION["atr_contraction"] < 0


# ── liquidity ─────────────────────────────────────────────────────
def test_adv_is_median_traded_value_in_rupees():
    rows = series([100.0] * 20, vols=[10000] * 20)
    assert F.adv_rupees(rows) == 100.0 * 10000   # ₹10,00,000


# ── normalisation ─────────────────────────────────────────────────
def test_zscore_leaves_missing_as_none_not_zero():
    z = F.zscores([1.0, 2.0, 3.0, None])
    assert z[3] is None, "a missing factor must not read as 'exactly average'"
    assert abs(sum(v for v in z if v is not None)) < 1e-9


def test_winsor_clips_a_runaway_value():
    # 50 identical values + one huge outlier: the outlier's raw z (~7) exceeds the clip.
    z = F.winsorized_zscores([0.0] * 50 + [1000.0], clip=3.0)
    assert max(v for v in z if v is not None) == 3.0
    assert F.zscores([0.0] * 50 + [1000.0])[-1] > 3.0   # and it really would have, unclipped


def test_percentile_ranks_average_ties():
    p = F.percentile_ranks([10, 20, 20, 40])
    assert p[1] == p[2]                            # tied values share a percentile


# ── composite ─────────────────────────────────────────────────────
def test_composite_ranks_the_all_round_stronger_stock_higher():
    # A: near highs, positive momentum, coiling. B: far below highs, negative momentum.
    strong = series([x for x in _ramp(100.0, 180.0, 200)] + [178.0] * 10)
    weak = series([x for x in _ramp(180.0, 100.0, 200)] + [100.0] * 10)
    raw = {"A": F.raw_factors(strong), "B": F.raw_factors(weak)}
    scores = F.Composite().score_universe(raw)
    assert scores["A"] > scores["B"]


def test_composite_renormalises_weight_over_present_factors_only():
    # A stock missing every long-history factor still gets a finite score from what it has.
    short = series([100.0 + i for i in range(70)])   # enough for 3M, not 6M/52w-full
    raw = {"X": F.raw_factors(short), "Y": F.raw_factors(short)}
    scores = F.Composite().score_universe(raw)
    assert all(math.isfinite(v) for v in scores.values())


def _ramp(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]
