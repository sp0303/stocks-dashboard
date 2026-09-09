"""Strategy core. Every test builds a synthetic session and asserts on the *rule that
fired*, not just the outcome — a signal that passes for the wrong reason is a bug that
only shows up with money on it.
"""
import pytest

from app.services.orb.bars import Bar
from app.services.orb.config import DEFAULT
from app.services.orb.features import opening_range, vwap_series
from app.services.orb.session import ENTRY_CUTOFF, MARKET_OPEN, OR_END
from app.services.orb.strategy import (LONG, SHORT, SessionContext, decide, manage,
                                       plan_trade, screen, Plan, Position)


def session(or_high=10100, or_low=9900, after=None, vol=20000):
    """09:15-09:30 oscillating inside [or_low, or_high], then whatever `after` supplies."""
    bars = []
    for i in range(OR_END - MARKET_OPEN):
        hi, lo = (or_high, or_low) if i in (3, 7) else (or_high - 40, or_low + 40)
        bars.append(Bar(minute=MARKET_OPEN + i, o=10000, h=hi, l=lo, c=10000, v=vol))
    bars.extend(after or [])
    return bars


def ctx_for(bars, minute, **kw):
    o = opening_range(bars)
    base = dict(
        symbol="TEST", date="2026-09-09", minute=minute, tick=5, bars=bars,
        vwap=vwap_series(bars), orange=o, prev_close=9910, pdh=10400, pdl=9700,
        atr14=400.0, median_or_vol=120000.0, median_cum_vol_now=200000.0,
        median_turnover_cr=120.0, cfg=DEFAULT,
    )
    base.update(kw)
    return SessionContext(**base)


def breakout_bars(start, n=5, px=10200, vol=18000, low=10150):
    return [Bar(minute=start + i, o=px - 20, h=px + 10, l=low, c=px, v=vol) for i in range(n)]


# ── screen ────────────────────────────────────────────────────────
def test_be_series_is_rejected_because_it_cannot_be_squared_off_intraday():
    t = screen(ctx_for(session(), OR_END, series="BE"))
    assert not t.passed and t.failed_rule == "A1"


def test_surveillance_and_narrow_price_band_are_rejected():
    assert screen(ctx_for(session(), OR_END, surveillance=True)).failed_rule == "A6a"
    assert screen(ctx_for(session(), OR_END, price_band_pct=5.0)).failed_rule == "A6b"


def test_range_wider_than_the_average_day_is_rejected():
    # width 200 vs 0.60 * ATR 400 = 240 -> passes; ATR 300 -> limit 180 -> fails
    assert screen(ctx_for(session(), OR_END, atr14=400.0)).passed
    assert screen(ctx_for(session(), OR_END, atr14=300.0)).failed_rule == "B2"


def test_low_opening_range_volume_is_rejected():
    t = screen(ctx_for(session(vol=2000), OR_END))
    assert t.failed_rule in ("C1", "C2")


def test_a_clean_candidate_passes_every_gate():
    t = screen(ctx_for(session(), OR_END))
    assert t.passed, t.failed_rule
    assert {c.rule for c in t.checks} >= {"A1", "A2", "B2", "B3", "B4", "C1", "C2"}


# ── decide ────────────────────────────────────────────────────────
def test_no_breakout_means_no_trade():
    bars = session(after=[Bar(minute=570 + i, o=10000, h=10050, l=9950, c=10000, v=18000)
                          for i in range(5)])
    d = decide(ctx_for(bars, 575))
    assert not d.entered and d.reason == "no breakout"


def test_clean_long_breakout_enters_with_the_tightest_of_three_stops():
    bars = session(after=breakout_bars(570, low=10150))
    d = decide(ctx_for(bars, 575))
    assert d.entered and d.side == LONG
    # or_mid is 10000; breakout low - tick is 10145; VWAP - 2 ticks is far below.
    # The rule takes the highest for a long, i.e. the breakout bar.
    assert d.stop == 10145


def test_stop_is_the_tightest_of_all_three_legs():
    """The rule, stated independently of which leg happens to win: for a long the stop
    is the highest of breakout-bar low, VWAP - 2 ticks, and the range midpoint. The
    draft this replaces dropped the breakout-bar leg entirely, which makes R — and so
    the targets and the position size — wrong on every trade."""
    bars = session(after=breakout_bars(570, px=10200, low=9800))
    c = ctx_for(bars, 575)
    d = decide(c)
    assert d.entered
    vwap = c.vwap.at_or_before(575)
    expected = max(9800 - c.tick, vwap - 2 * c.tick, opening_range(bars).mid)
    assert d.stop == expected
    assert d.stop != 9800 - c.tick          # the loosest leg never wins


def test_breaking_out_below_vwap_is_a_trap_and_vetoes_the_symbol():
    # A heavy spike after the range drags VWAP up; the next bar closes above the range
    # high but back under VWAP. That is the trade the D4 veto exists to refuse.
    spike = [Bar(minute=570 + i, o=10500, h=10520, l=10480, c=10500, v=400000)
             for i in range(5)]
    fade = [Bar(minute=575 + i, o=10110, h=10130, l=10100, c=10105, v=18000)
            for i in range(5)]
    bars = session(after=spike + fade)
    d = decide(ctx_for(bars, 580))
    assert not d.entered and "trap" in d.reason


def test_entry_window_closes_at_1130():
    bars = session(after=breakout_bars(ENTRY_CUTOFF, low=10150))
    d = decide(ctx_for(bars, ENTRY_CUTOFF + 5))
    assert not d.entered and d.reason == "outside the entry window"


def test_a_vetoed_symbol_stays_vetoed():
    bars = session(after=breakout_bars(570, low=10150))
    d = decide(ctx_for(bars, 575, dead=True))
    assert not d.entered and d.reason == "symbol vetoed"


def test_risk_limits_block_entries():
    bars = session(after=breakout_bars(570, low=10150))
    assert decide(ctx_for(bars, 575, traded_today=4)).reason == "daily trade cap"
    assert decide(ctx_for(bars, 575, open_positions=3)).reason == "concurrent position cap"
    assert decide(ctx_for(bars, 575, day_r=-2.5)).reason == "daily stop hit"
    assert decide(ctx_for(bars, 575, consecutive_losses=2)).reason == "consecutive losses"


def test_weak_breakout_bar_volume_is_rejected():
    bars = session(after=breakout_bars(570, vol=100, low=10150))
    d = decide(ctx_for(bars, 575))
    assert not d.entered
    failed = {c.rule for c in d.trace.checks if not c.ok}
    assert "C3" in failed                    # the breakout bar carried no participation


def test_short_side_mirrors():
    bars = session(after=[Bar(minute=570 + i, o=9880, h=9890, l=9800, c=9810, v=18000)
                          for i in range(5)])
    d = decide(ctx_for(bars, 575, market_ret=-0.4, sector_index_ret=-0.3))
    assert d.entered and d.side == SHORT and d.stop > d.trigger


# ── sizing ────────────────────────────────────────────────────────
def test_position_size_respects_risk_notional_and_liquidity_caps():
    p = plan_trade(DEFAULT, LONG, entry=10000, stop=9900, or_width=200)
    # risk Rs 1.00/share, 0.75% of Rs 10L = Rs 7,500 -> 7,500 shares, but 15% notional
    # of Rs 10L at Rs 100/share caps it at 1,500.
    assert p.qty == 1500 and p.risk == 100
    assert p.t1 == 10150 and p.t2 == 10200
    thin = plan_trade(DEFAULT, LONG, entry=10000, stop=9900, or_width=200,
                      median_daily_vol=50_000)
    assert thin.qty == 500          # 1% of median volume


def test_an_inverted_stop_produces_no_plan():
    assert plan_trade(DEFAULT, LONG, entry=10000, stop=10100, or_width=200) is None


# ── manage ────────────────────────────────────────────────────────
def _pos(side=LONG):
    plan = plan_trade(DEFAULT, side, entry=10000, stop=9900, or_width=200)
    return Position(symbol="TEST", plan=plan, entry_minute=575, breakout_volume=90000,
                    qty_open=plan.qty, stop=plan.stop)


def test_stop_is_checked_before_target():
    bars = session(after=breakout_bars(570, low=10150))
    c = ctx_for(bars, 600)
    assert manage(_pos(), c, 9899)[0] == "STOP"


def test_t1_then_t2():
    bars = session(after=breakout_bars(570, low=10150))
    c = ctx_for(bars, 600)
    p = _pos()
    assert manage(p, c, 10150)[0] == "T1"
    p.t1_done = True
    assert manage(p, c, 10200)[0] == "T2"


def test_no_follow_through_exit_fires_on_three_weak_bars():
    quiet = [Bar(minute=575 + i, o=10010, h=10020, l=10000, c=10010, v=100)
             for i in range(15)]
    bars = session(after=breakout_bars(570, low=10150) + quiet)
    c = ctx_for(bars, 590)
    out = manage(_pos(), c, 10010)
    assert out and out[0] == "NO_FOLLOW_THROUGH"
