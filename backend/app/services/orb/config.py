"""Every threshold the strategy uses, in one place, with a version stamp.

A signal records the config version that produced it, so a rule change never silently
reinterprets yesterday's signals. Bump CONFIG_VERSION whenever a default changes.

Rule IDs match the build plan: A* universe/session, B* opening range, C* volume,
D* VWAP and context, E* entry/stop/target, F* risk.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

CONFIG_VERSION = "orb-1.1.0"


@dataclass(frozen=True)
class OrbConfig:
    # ── A · universe and session ──────────────────────────────────
    series_allowed: tuple[str, ...] = ("EQ",)     # A1' BE is Trade-to-Trade: no intraday
    min_median_turnover_cr: float = 50.0          # A2  20-day median traded value
    exclude_surveillance: bool = True             # A6  ASM / GSM
    min_price_band_pct: float = 20.0              # A6  reject 5% and 10% band names
    min_circuit_distance_pct: float = 2.0         # A7  distance to nearer circuit at 09:30
    event_blackout_days: int = 1                  # A4  results / ex-date, +/- days
    max_india_vix: float = 25.0                   # A5

    # ── B · opening range ─────────────────────────────────────────
    or_width_max_atr_mult: float = 0.60           # B2  width <= 0.60 x ATR14 (thru yesterday)
    or_width_min_pct: float = 0.30                # B3  width / mid, percent
    gap_min_pct: float = 0.80                     # B4  measured off the 09:15 open
    gap_max_pct: float = 4.00                     # B4  above this is exhaustion
    headroom_mult: float = 0.60                   # B5  clearance to PDH/PDL vs T1 distance

    # ── C · volume ────────────────────────────────────────────────
    rvol_or_min: float = 2.0                      # C1  vs 10-day median 09:15-09:30 volume
    or_turnover_min_cr: float = 2.0               # C2  opening-range traded value
    breakout_vol_mult: float = 1.5                # C3  vs mean 5-min bar since 09:30
    breakout_vol_vs_or_mult: float = 0.8          # C3  fallback for the first bar after
                                                  #     the range, vs the range's own pace
    cum_rvol_min: float = 1.5                     # C4  time-of-day normalised
    climax_rvol: float = 6.0                      # C5  above this + wide range = skip
    close_strength: float = 0.65                  # C6  close in top/bottom third of bar
    nofollow_bars: int = 3                        # C7  consecutive weak bars
    nofollow_vol_mult: float = 0.5                # C7  vs the breakout bar

    # ── D · VWAP and context ──────────────────────────────────────
    vwap_slope_lookback_min: int = 15             # D3
    vwap_slope_min_pct: float = 0.15              # D3  raised from 0.02 (loss analysis:
                                                  #     flat-VWAP breakouts are chop)
    require_sector_alignment: bool = False        # D5  backtest showed alignment is
    require_market_alignment: bool = False        # D6  anti-predictive here (rel. strength)
    vwap_drift_tolerance_bps: float = 10.0        # D7  ours vs the feed's average_traded_price

    # ── E · entry, stop, target ───────────────────────────────────
    signal_timeframe_min: int = 5                 # breakout judged on 5-minute closes
    stop_vwap_ticks: int = 2                      # E  VWAP -/+ 2 ticks
    t1_r_multiple: float = 1.5
    t1_book_fraction: float = 0.5
    trail_lookback_bars: int = 2                  # 5-minute bars, after T1
    max_risk_atr_mult: float = 1.2                # reject if stop is further than this
    # Quality floors found by the backtest's loss analysis — the strategy bleeds on
    # tight-stop, low-volatility chop and earns on real movers. Validated out-of-sample
    # (thresholds fit on year 1, held on year 2). 0.0 disables a floor.
    min_risk_pct: float = 0.6                     # E4  stop at least this %% of price
    min_atr_pct: float = 3.2                      # B6  ATR14 at least this %% of price

    # ── F · risk ──────────────────────────────────────────────────
    capital: float = 1_000_000.0
    risk_per_trade_pct: float = 0.75
    max_notional_pct: float = 15.0
    max_qty_pct_of_median_vol: float = 1.0
    max_concurrent: int = 3
    max_trades_per_day: int = 4
    daily_stop_r: float = -2.0
    max_consecutive_losses: int = 2
    allow_reentry: bool = True

    # ── costs (used by the paper journal; Segment C reuses the same numbers) ──
    brokerage_pct: float = 0.03
    brokerage_cap: float = 20.0
    stt_sell_pct: float = 0.025
    exchange_txn_pct: float = 0.00307
    stamp_buy_pct: float = 0.003
    sebi_per_crore: float = 10.0
    gst_pct: float = 18.0
    slippage_entry_pct: float = 0.02
    slippage_stop_pct: float = 0.05

    # ── operational ───────────────────────────────────────────────
    universe_size: int = 200                      # working set; the websocket allows 1000
    version: str = CONFIG_VERSION

    def with_overrides(self, **kw) -> "OrbConfig":
        known = {k: v for k, v in kw.items() if k in self.__dataclass_fields__}
        return replace(self, **known)

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = OrbConfig()
