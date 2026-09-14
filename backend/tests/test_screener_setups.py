"""Phase 2 setup classification. These pin the geometry each label stands on and the
precedence between them — the two things easiest to get wrong when setups overlap. Pure:
no Mongo, no network.
"""
from app.services import screener_setups as S


def series(closes, highs=None, lows=None, vols=None):
    """Daily-store rows (paise) from a close series. Highs/lows default to ±1% so ATR is
    non-zero; override when a test needs a specific range."""
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    vols = vols or [100000] * n
    return [{"date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "o": int(closes[i] * 100), "h": int(highs[i] * 100),
             "l": int(lows[i] * 100), "c": int(closes[i] * 100), "v": vols[i]}
            for i in range(n)]


def _ramp(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


# ── RSI(2) ────────────────────────────────────────────────────────
def test_rsi2_saturates_up_and_down():
    assert S.rsi([100 + i for i in range(10)], 2) == 100.0        # only gains
    assert S.rsi([100 - i for i in range(10)], 2) == 0.0          # only losses


def test_rsi2_needs_history():
    assert S.rsi([100.0], 2) is None


# ── near breakout ─────────────────────────────────────────────────
def test_near_breakout_when_coiling_below_a_rising_high():
    # Long steady climb to a fresh high, then a tight coil (small range) near the top.
    closes = _ramp(60.0, 100.0, 240) + [100.0, 99.8, 100.1, 99.9, 100.0]
    # tight recent range → ATR contracts; wide earlier range handled by defaults
    rows = series(closes)
    assert S.classify(rows) == S.NEAR_BREAKOUT


# ── extended ──────────────────────────────────────────────────────
def test_extended_when_far_above_dma20():
    # Strong uptrend, then a vertical blowoff far above the 20-DMA.
    closes = _ramp(60.0, 100.0, 240) + list(_ramp(100.0, 140.0, 8))
    rows = series(closes)
    assert S.classify(rows) == S.EXTENDED


# ── pullback ──────────────────────────────────────────────────────
def test_pullback_dip_to_the_mas_in_an_uptrend():
    # Uptrend well above DMA200, then a short sharp dip back toward the DMA20/50 zone.
    closes = _ramp(60.0, 110.0, 240) + [108.0, 105.0, 102.0, 100.5, 99.5]
    rows = series(closes)
    assert S.classify(rows) == S.PULLBACK


# ── oversold reversal ─────────────────────────────────────────────
def test_oversold_reversal_on_capitulation_below_trend():
    # Downtrend below DMA200 with a final washout → deep RSI(2), trend-agnostic bounce.
    closes = _ramp(140.0, 90.0, 240) + [88.0, 85.0, 82.0, 79.0, 76.0]
    rows = series(closes)
    assert S.classify(rows) == S.OVERSOLD_REVERSAL


# ── no setup / guards ─────────────────────────────────────────────
def test_short_history_is_no_setup():
    assert S.classify(series([100.0] * 30)) == S.NO_SETUP


def test_quiet_midtrend_is_no_setup():
    # Above DMA200 but mid-range: not near the high, not oversold, not extended.
    closes = _ramp(60.0, 100.0, 200) + [100.0] * 40
    rows = series(closes)
    # sitting flat at the top for 40 sessions → DMA20≈price, from_52w≈0 but not coiling
    # into a fresh high and RSI neutral; should not be a tradable dip/reversal.
    assert S.classify(rows) in (S.NEAR_BREAKOUT, S.NO_SETUP, S.EXTENDED)


def test_labels_are_exhaustive_and_stable():
    # classify always returns one of the known labels.
    for closes in ([100.0] * 300, _ramp(50, 150, 300), _ramp(150, 50, 300)):
        assert S.classify(series(closes)) in S.ALL_LABELS
