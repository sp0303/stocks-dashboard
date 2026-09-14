"""Phase 2 — setup classification for the swing screener.

Phase 1 proved the normalised composite ranking has a positive, cost-net IC (the top
decile beats equal-weight out of sample). But one blended rank hides *why* a name is
ranked and how it should be traded: a stock coiling below its 52-week high and a stock
capitulating 15% below its DMA200 can score similarly, yet they want opposite holds and
exits. Phase 2 replaces the single rank with a small set of **labelled setups**, each
validated on its own — sample size, expectancy in R, sub-period and sector — so a label
that cannot clear its own bar never ships (that is the Phase 2 gate).

The three drivers come straight from the evidence, and are deliberately different animals:

  * NEAR BREAKOUT (trend continuation) — near the 52-week high, stacked above DMA20/50,
    range coiling (VCP). George & Hwang (2004) + Minervini. A trend trade: wide target,
    longer hold.
  * PULLBACK (dip in an uptrend) — above DMA200, price fallen back to DMA20/50,
    short-term oversold (RSI-2) *inside* an intact uptrend. Buy the dip, not the crash:
    tighter target, medium hold.
  * OVERSOLD REVERSAL (short-horizon mean reversion) — the +3d effect Phase 0/1 measured,
    where the most beaten-down names bounce. Trend-agnostic capitulation. Fast target,
    short hold, its own exit.

Two more labels carry information without being buys:

  * EXTENDED — AVOID CHASING — a strong uptrend stretched too far above DMA20 to enter
    here. Reported so the harness can *confirm* it is an inferior long, not a hidden one.
  * NO SETUP — none of the above; excluded from every setup book.

Every function is pure (rows in, numbers/label out) and shares Phase 1's helpers, so the
live screen and the backtest classify identically and cannot drift. Rows are the daily
store shape: {"date","o","h","l","c" (paise),"v"}.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import screener_factors as F

# ── labels ────────────────────────────────────────────────────────
NEAR_BREAKOUT = "Near breakout"
PULLBACK = "Pullback setup"
OVERSOLD_REVERSAL = "Oversold reversal"
EXTENDED = "Extended — avoid chasing"
NO_SETUP = "No setup"

# The three tradable setups (EXTENDED/NO_SETUP are context, not books).
TRADABLE = (NEAR_BREAKOUT, PULLBACK, OVERSOLD_REVERSAL)
ALL_LABELS = (NEAR_BREAKOUT, PULLBACK, OVERSOLD_REVERSAL, EXTENDED, NO_SETUP)

# Per-setup trade geometry, in ATR units, used by the Phase 2 harness to turn each label
# into an expectancy in R. Different setups, different holds and exits — that is the point
# of splitting them. stop/target are multiples of ATR(14); horizon is trading sessions.
#   R := the initial risk = stop_atr * ATR. target in R = target_atr / stop_atr.
SETUP_GEOMETRY = {
    NEAR_BREAKOUT:     {"stop_atr": 1.5, "target_atr": 3.0,  "horizon": 20},  # 2.0R, trend runs
    PULLBACK:          {"stop_atr": 1.5, "target_atr": 2.25, "horizon": 10},  # 1.5R, medium
    OVERSOLD_REVERSAL: {"stop_atr": 1.5, "target_atr": 1.5,  "horizon": 5},   # 1.0R, fast bounce
    EXTENDED:          {"stop_atr": 1.5, "target_atr": 3.0,  "horizon": 10},  # scored as a chase
}


# ── geometry helpers (point-in-time; rows already sliced to <= as_of) ──
def _dma(closes: list[float], n: int) -> float | None:
    return sum(closes[-n:]) / n if len(closes) >= n else None


def atr_pct_contraction(rows: list[dict], ago: int = 60) -> float | None:
    """ATR-as-%-of-price now ÷ that same % `ago` sessions back. Unlike the absolute-rupee
    atr_contraction (which mechanically rises in any uptrend, since a constant-% range is
    more rupees at a higher price), this is scale-free: <1 means volatility is genuinely
    contracting — the coil that precedes a breakout."""
    now = F.atr_pct(rows)
    if len(rows) <= ago:
        return None
    then = F.atr_pct(rows[: len(rows) - ago])
    return (now / then) if (now and then) else None


def rsi(closes: list[float], period: int = 2) -> float | None:
    """Wilder RSI over `period` sessions. RSI(2) is the standard short-horizon
    overbought/oversold trigger (Connors): <10 is washed out, >90 is stretched."""
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(len(closes) - period, len(closes)):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    avg_gain, avg_loss = gains / period, losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


@dataclass
class Features:
    """The geometry a classification stands on — exposed so tests and the UI can show the
    'why' behind a label, not just the label."""
    close: float
    dma20: float | None
    dma50: float | None
    dma200: float | None
    from_52w: float | None       # % below the 52w high (<=0)
    atr_pct: float | None        # ATR as % of price
    atr_contraction: float | None  # absolute ATR now / ATR ~60d ago (Phase 1 factor)
    coil: float | None           # ATR%-now / ATR%-ago (<1 = genuinely coiling, scale-free)
    rsi2: float | None
    ext_atr: float | None        # (close - dma20) / ATR  — extension above DMA20, in ATRs


def features(rows: list[dict]) -> Features | None:
    """All geometry for one stock, point-in-time on the rows given (need >=~220 rows for
    DMA200 and a 52w window). Returns None if too short to judge."""
    c = F._closes(rows)
    if len(c) < 60:
        return None
    atr = F._atr(rows)
    return Features(
        close=c[-1],
        dma20=_dma(c, 20),
        dma50=_dma(c, 50),
        dma200=_dma(c, 200),
        from_52w=F.dist_from_52w(rows),
        atr_pct=F.atr_pct(rows),
        atr_contraction=F.atr_contraction(rows),
        coil=atr_pct_contraction(rows),
        rsi2=rsi(c, 2),
        ext_atr=((c[-1] - _dma(c, 20)) / atr) if (atr and _dma(c, 20) is not None) else None,
    )


# ── thresholds (provisional until the harness validates each setup) ──
NEAR_HIGH = -8.0        # within 8% of the 52w high counts as "near"
ATR_FLOOR = 1.5         # a tradable name needs >=1.5% ATR of room to travel
COIL_MAX = 1.05         # ATR-now/ATR-then at/under this = range not expanding
EXTENDED_ATR = 4.0      # >4 ATRs above DMA20 = too stretched to enter
PULLBACK_RSI = 15.0     # short-term oversold inside an uptrend
DEEP_OVERSOLD_RSI = 5.0  # capitulation, trend-agnostic


def classify(rows: list[dict]) -> str:
    """Label one stock from its daily rows. Precedence resolves overlaps: a strong trend
    is judged extended-or-breakout first, then dip setups, then trend-agnostic
    capitulation. A name that fits nothing tradable is NO_SETUP."""
    f = features(rows)
    if f is None or f.dma20 is None or f.dma50 is None or f.dma200 is None:
        return NO_SETUP
    if f.atr_pct is None or f.rsi2 is None or f.from_52w is None:
        return NO_SETUP

    uptrend = f.close > f.dma200
    stacked = f.dma20 > f.dma50            # short MA above long MA = up-structure
    tradable_vol = f.atr_pct >= ATR_FLOOR

    # 1) In a strong uptrend and stretched too far above DMA20 → do not chase.
    if uptrend and f.ext_atr is not None and f.ext_atr >= EXTENDED_ATR:
        return EXTENDED

    # 2) Near breakout: near the high, up-structure, range coiling, enough room.
    if (uptrend and stacked and tradable_vol
            and f.from_52w >= NEAR_HIGH
            and f.coil is not None and f.coil <= COIL_MAX):
        return NEAR_BREAKOUT

    # 3) Pullback: uptrend intact, price fallen back to the DMA20/50 zone, short-term
    #    oversold — a dip, not a top (so it must NOT still be pinned to the high).
    if (uptrend and tradable_vol
            and f.from_52w <= NEAR_HIGH
            and f.rsi2 <= PULLBACK_RSI
            and f.dma50 is not None
            and f.close <= f.dma20 * 1.02 and f.close >= f.dma50 * 0.94):
        return PULLBACK

    # 4) Oversold reversal: capitulation regardless of long trend — the measured +3d
    #    bounce in the most beaten-down names. Deep RSI-2, or below-trend and washed out.
    if tradable_vol and (f.rsi2 <= DEEP_OVERSOLD_RSI
                         or (not uptrend and f.rsi2 <= PULLBACK_RSI)):
        return OVERSOLD_REVERSAL

    return NO_SETUP
