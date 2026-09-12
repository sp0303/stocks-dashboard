"""The strategy core — the one place a trading rule is written down.

`screen()` runs at 09:31 over the whole universe and produces the shortlist.
`decide()` runs on each completed 5-minute bar and produces an entry or a reason there
wasn't one. `manage()` runs on an open position and produces an exit or nothing.

All three are pure: no I/O, no clock, no globals. The live engine and the (later)
replay driver call exactly these, which is what makes a backtest number and a Monday
morning signal comparable at all.

Every gate appends to a trace — including the ones that pass — so a rejected candidate
can answer "why not this one" months later, which is the question you actually ask.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.orb.bars import Bar
from app.services.orb.config import DEFAULT, OrbConfig
from app.services.orb.features import Bar5, OpeningRange, Vwap, resample
from app.services.orb.session import (ENTRY_CUTOFF, ENTRY_FIRST, MARKET_OPEN, OR_END,
                                      SQUARE_OFF)

LONG, SHORT = 1, -1


@dataclass
class Check:
    rule: str
    ok: bool
    value: float | str | None = None
    limit: float | str | None = None
    note: str = ""


@dataclass
class Trace:
    checks: list[Check] = field(default_factory=list)

    def add(self, rule, ok, value=None, limit=None, note="") -> bool:
        self.checks.append(Check(rule, bool(ok), value, limit, note))
        return bool(ok)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed_rule(self) -> str | None:
        for c in self.checks:
            if not c.ok:
                return c.rule
        return None

    def as_list(self) -> list[dict]:
        return [c.__dict__ for c in self.checks]


@dataclass
class SessionContext:
    """Everything the rules may look at. Assembled by the caller; the strategy never
    fetches anything itself."""
    symbol: str
    date: str
    minute: int
    tick: int                                  # paise
    bars: list[Bar]                            # 1-minute bars, 09:15 to `minute`
    vwap: Vwap
    orange: OpeningRange | None
    prev_close: int | None = None
    pdh: int | None = None
    pdl: int | None = None
    atr14: float | None = None                 # paise, through yesterday
    median_or_vol: float | None = None
    median_cum_vol_now: float | None = None
    median_turnover_cr: float | None = None
    series: str = "EQ"
    surveillance: bool = False
    price_band_pct: float | None = 20.0
    event_blackout: bool = False
    circuit_distance_pct: float | None = None
    feed_vwap: int | None = None               # average_traded_price from the websocket
    sector_index_ret: float | None = None      # % since 09:15; None = unmapped
    market_ret: float | None = None
    vix: float | None = None
    dead: bool = False                         # D4 trap veto already fired today
    traded_today: int = 0
    open_positions: int = 0
    day_r: float = 0.0
    consecutive_losses: int = 0
    cfg: OrbConfig = DEFAULT

    def bars5(self) -> list[Bar5]:
        return resample(self.bars, self.cfg.signal_timeframe_min)


@dataclass
class Decision:
    action: str                    # "none" | "enter"
    trace: Trace
    side: int = 0
    stop: int = 0                  # absolute, independent of the fill price
    trigger: int = 0               # the breakout bar's close, for reference
    or_width: int = 0
    reason: str = ""

    @property
    def entered(self) -> bool:
        return self.action == "enter"


# ── 09:31 screen: gates A, B, C1, C2 ──────────────────────────────
def screen(ctx: SessionContext) -> Trace:
    c, t = ctx.cfg, Trace()
    o = ctx.orange

    t.add("A1", ctx.series in c.series_allowed, ctx.series, "/".join(c.series_allowed),
          "BE is Trade-to-Trade: no intraday square-off")
    t.add("A6a", not (c.exclude_surveillance and ctx.surveillance), ctx.surveillance, False)
    t.add("A6b", ctx.price_band_pct is None or ctx.price_band_pct >= c.min_price_band_pct,
          ctx.price_band_pct, c.min_price_band_pct)
    t.add("A4", not ctx.event_blackout, ctx.event_blackout, False, "results / ex-date window")
    t.add("A5", ctx.vix is None or ctx.vix <= c.max_india_vix, ctx.vix, c.max_india_vix)
    t.add("A2", ctx.median_turnover_cr is not None
          and ctx.median_turnover_cr >= c.min_median_turnover_cr,
          ctx.median_turnover_cr, c.min_median_turnover_cr, "20-day median traded value, Rs cr")
    t.add("A7", ctx.circuit_distance_pct is None
          or ctx.circuit_distance_pct >= c.min_circuit_distance_pct,
          ctx.circuit_distance_pct, c.min_circuit_distance_pct)

    if o is None:
        t.add("B1", False, None, None, "no opening range")
        return t
    t.add("B1", o.complete, o.bars, OR_END - 555, "complete 09:15-09:30")
    t.add("B2", ctx.atr14 is not None and o.width <= c.or_width_max_atr_mult * ctx.atr14,
          o.width, round(c.or_width_max_atr_mult * ctx.atr14, 1) if ctx.atr14 else None,
          "range already used up the day's average move")
    t.add("B3", o.width_pct >= c.or_width_min_pct, round(o.width_pct, 3), c.or_width_min_pct)

    gap = None
    if ctx.prev_close:
        first = next((b for b in ctx.bars if not b.syn), None)
        if first:
            gap = (first.o - ctx.prev_close) / ctx.prev_close * 100.0
    t.add("B4", gap is not None and c.gap_min_pct <= abs(gap) <= c.gap_max_pct,
          round(gap, 2) if gap is not None else None,
          f"{c.gap_min_pct}-{c.gap_max_pct}", "measured off the 09:15 open")

    rvol = (o.volume / ctx.median_or_vol) if ctx.median_or_vol else None
    t.add("C1", rvol is not None and rvol >= c.rvol_or_min,
          round(rvol, 2) if rvol else None, c.rvol_or_min, "opening-range relative volume")
    t.add("C2", (o.turnover / 1e7) >= c.or_turnover_min_cr,
          round(o.turnover / 1e7, 2), c.or_turnover_min_cr, "opening-range traded value, Rs cr")
    t.add("C5", not (rvol is not None and rvol > c.climax_rvol
                     and ctx.atr14 and o.width > c.or_width_max_atr_mult * ctx.atr14),
          round(rvol, 2) if rvol else None, c.climax_rvol, "climax volume on a wide range")
    return t


# ── per-bar decision: gates C3-C6, D, E ───────────────────────────
def decide(ctx: SessionContext) -> Decision:
    c, t = ctx.cfg, Trace()
    o = ctx.orange
    if o is None:
        return Decision("none", t, reason="no opening range")

    if not t.add("E0", ENTRY_FIRST <= ctx.minute <= ENTRY_CUTOFF, ctx.minute,
                 ENTRY_CUTOFF, "entry window"):
        return Decision("none", t, reason="outside the entry window")
    if not t.add("D4", not ctx.dead, ctx.dead, False, "trap veto fired earlier today"):
        return Decision("none", t, reason="symbol vetoed")
    if not t.add("F1", ctx.traded_today < c.max_trades_per_day, ctx.traded_today,
                 c.max_trades_per_day):
        return Decision("none", t, reason="daily trade cap")
    if not t.add("F2", ctx.open_positions < c.max_concurrent, ctx.open_positions,
                 c.max_concurrent):
        return Decision("none", t, reason="concurrent position cap")
    if not t.add("F3", ctx.day_r > c.daily_stop_r, round(ctx.day_r, 2), c.daily_stop_r,
                 "daily loss limit"):
        return Decision("none", t, reason="daily stop hit")
    if not t.add("F4", ctx.consecutive_losses < c.max_consecutive_losses,
                 ctx.consecutive_losses, c.max_consecutive_losses):
        return Decision("none", t, reason="consecutive losses")

    bars5 = [b for b in ctx.bars5() if b.end <= ctx.minute]
    if not bars5:
        return Decision("none", t, reason="no completed 5-minute bar")
    bar = bars5[-1]

    side = LONG if bar.c > o.high else SHORT if bar.c < o.low else 0
    if not t.add("E1", side != 0, bar.c, f"{o.low}/{o.high}", "5-minute close beyond the range"):
        return Decision("none", t, reason="no breakout")

    vwap = ctx.vwap.at_or_before(ctx.minute)
    if not t.add("D1", vwap is not None, vwap, None, "VWAP available"):
        return Decision("none", t, reason="no VWAP")

    # D4 — the trap: broken out but on the wrong side of VWAP kills the symbol for the
    # session, both directions, not just this bar.
    trap = (side == LONG and bar.c <= vwap) or (side == SHORT and bar.c >= vwap)
    if not t.add("D2", not trap, bar.c, vwap, "price the right side of VWAP"):
        return Decision("none", t, reason="trap: broke out against VWAP", side=side)

    slope = ctx.vwap.slope_pct(ctx.minute, c.vwap_slope_lookback_min)
    t.add("D3", slope is not None and (slope >= c.vwap_slope_min_pct if side == LONG
                                       else slope <= -c.vwap_slope_min_pct),
          round(slope, 4) if slope is not None else None,
          c.vwap_slope_min_pct, f"VWAP slope over {c.vwap_slope_lookback_min}m")

    if ctx.feed_vwap:
        drift_bps = abs(vwap - ctx.feed_vwap) / ctx.feed_vwap * 10000.0
        t.add("D7", drift_bps <= c.vwap_drift_tolerance_bps, round(drift_bps, 1),
              c.vwap_drift_tolerance_bps, "our VWAP vs the feed's average traded price")

    if c.require_sector_alignment:
        t.add("D5", ctx.sector_index_ret is None or (ctx.sector_index_ret > 0) == (side == LONG),
              ctx.sector_index_ret, 0,
              "no sector index mapped" if ctx.sector_index_ret is None else "sector agrees")
    if c.require_market_alignment:
        t.add("D6", ctx.market_ret is None or (ctx.market_ret > 0) == (side == LONG),
              ctx.market_ret, 0, "Nifty agrees")

    # The baseline must exclude the breakout bar itself — comparing a bar to an average
    # that contains it makes the test unpassable whenever it is the only sample.
    prior5 = [b for b in bars5 if OR_END < b.end < bar.end]
    if prior5:
        threshold = c.breakout_vol_mult * (sum(b.v for b in prior5) / len(prior5))
        basis = "vs 5-minute bars since 09:30"
    else:
        # First bar after the range: nothing to average, so compare against the pace the
        # opening range itself set.
        or_pace = o.volume / ((OR_END - MARKET_OPEN) / c.signal_timeframe_min)
        threshold = c.breakout_vol_vs_or_mult * or_pace
        basis = "vs the opening range's own pace"
    t.add("C3", threshold > 0 and bar.v >= threshold, bar.v, round(threshold), basis)

    cum = sum(b.v for b in ctx.bars if b.minute < ctx.minute)
    cum_rvol = (cum / ctx.median_cum_vol_now) if ctx.median_cum_vol_now else None
    t.add("C4", cum_rvol is not None and cum_rvol >= c.cum_rvol_min,
          round(cum_rvol, 2) if cum_rvol else None, c.cum_rvol_min,
          "cumulative volume vs the same clock time on prior sessions")

    t.add("C6", bar.close_strength(side) >= c.close_strength,
          round(bar.close_strength(side), 2), c.close_strength, "closed near the extreme")

    stop = _stop_for(side, bar, vwap, o.mid, ctx.tick)
    risk = (bar.c - stop) if side == LONG else (stop - bar.c)
    t.add("E2", risk > 0, risk, 0, "stop on the correct side of the trigger")
    t.add("E3", ctx.atr14 is None or risk <= c.max_risk_atr_mult * ctx.atr14, risk,
          round(c.max_risk_atr_mult * ctx.atr14, 1) if ctx.atr14 else None,
          "stop too far to be a day trade")

    # E4 — a floor under the stop distance. Too-tight stops sit inside the noise and are
    # the worst cohort in the backtest; below this %% of price the setup is chop.
    t.add("E4", not c.min_risk_pct or risk >= c.min_risk_pct / 100.0 * bar.c,
          round(risk / bar.c * 100, 3), c.min_risk_pct, "stop distance vs price")

    # B6 — a volatility floor. ORB needs a name that can travel; low-ATR names chop and
    # fail the breakout. ATR14 is through yesterday, so this leaks nothing.
    atr_pct = (ctx.atr14 / bar.c * 100) if ctx.atr14 else None
    t.add("B6", not c.min_atr_pct or (atr_pct is not None and atr_pct >= c.min_atr_pct),
          round(atr_pct, 2) if atr_pct is not None else None, c.min_atr_pct,
          "ATR14 vs price")

    # B5 — room to run before yesterday's high/low. A trade breaking into fresh ground
    # (already beyond PDH/PDL) is the good case and passes; only a nearby prior-day cap
    # standing between the trigger and its T1 fails. Skipped when the level is unknown.
    t1_dist = c.t1_r_multiple * risk
    room = None
    if side == LONG and ctx.pdh is not None:
        room = ctx.pdh - bar.c
    elif side == SHORT and ctx.pdl is not None:
        room = bar.c - ctx.pdl
    t.add("B5", room is None or room <= 0 or room >= c.headroom_mult * t1_dist,
          round(room) if room is not None else None,
          round(c.headroom_mult * t1_dist),
          "clearance to PDH/PDL is at least headroom_mult x the T1 distance")

    if not t.passed:
        return Decision("none", t, side=side, reason=f"failed {t.failed_rule}")
    return Decision("enter", t, side=side, stop=stop, trigger=bar.c, or_width=o.width)


def _stop_for(side: int, bar: Bar5, vwap: int, or_mid: int, tick: int) -> int:
    """The tightest of the three legs — which for a long means the highest.

    The draft this replaces used only max(vwap, or_mid) and dropped the breakout bar
    entirely, which makes R wrong on every trade and therefore the targets and the
    position size wrong too."""
    if side == LONG:
        return max(bar.l - tick, vwap - 2 * tick, or_mid)
    return min(bar.h + tick, vwap + 2 * tick, or_mid)


# ── sizing and targets, once a fill price is known ────────────────
@dataclass
class Plan:
    side: int
    entry: int
    stop: int
    risk: int
    t1: int
    t2: int
    qty: int
    notional: float

    def r_multiple(self, price: int) -> float:
        if not self.risk:
            return 0.0
        return ((price - self.entry) if self.side == LONG else (self.entry - price)) / self.risk


def plan_trade(cfg: OrbConfig, side: int, entry: int, stop: int, or_width: int,
               median_daily_vol: int | None = None) -> Plan | None:
    risk = (entry - stop) if side == LONG else (stop - entry)
    if risk <= 0:
        return None
    t1 = entry + int(round(cfg.t1_r_multiple * risk)) * side
    t2 = entry + or_width * side
    risk_rupees = cfg.capital * cfg.risk_per_trade_pct / 100.0
    qty = int(risk_rupees / (risk / 100.0))                       # risk is in paise
    cap_by_notional = int(cfg.capital * cfg.max_notional_pct / 100.0 / (entry / 100.0))
    qty = min(qty, cap_by_notional)
    if median_daily_vol:
        qty = min(qty, int(median_daily_vol * cfg.max_qty_pct_of_median_vol / 100.0))
    if qty <= 0:
        return None
    return Plan(side=side, entry=entry, stop=stop, risk=risk, t1=t1, t2=t2, qty=qty,
                notional=qty * entry / 100.0)


# ── managing an open position ─────────────────────────────────────
@dataclass
class Position:
    symbol: str
    plan: Plan
    entry_minute: int
    breakout_volume: int
    qty_open: int
    stop: int
    t1_done: bool = False
    weak_bars: int = 0


def manage(pos: Position, ctx: SessionContext, last_price: int) -> tuple[str, int] | None:
    """Return (reason, price) for an exit, or None to hold. Checked in the order a real
    session imposes: stop first, because within one bar we cannot know it wasn't."""
    c = ctx.cfg
    side = pos.plan.side
    hit_stop = last_price <= pos.stop if side == LONG else last_price >= pos.stop
    if hit_stop:
        return ("STOP" if not pos.t1_done else "TRAIL"), pos.stop

    if ctx.minute >= SQUARE_OFF:
        return "SQUARE_OFF", last_price

    if not pos.t1_done:
        hit_t1 = last_price >= pos.plan.t1 if side == LONG else last_price <= pos.plan.t1
        if hit_t1:
            return "T1", pos.plan.t1
    else:
        hit_t2 = last_price >= pos.plan.t2 if side == LONG else last_price <= pos.plan.t2
        if hit_t2:
            return "T2", pos.plan.t2

    # C7 — no follow-through. Three consecutive 5-minute bars under half the breakout
    # bar's volume without reaching 1R is a slow bleed; take the scratch.
    bars5 = [b for b in ctx.bars5() if b.end > pos.entry_minute and b.end <= ctx.minute]
    if bars5 and pos.breakout_volume:
        weak = 0
        for b in reversed(bars5):
            if b.v < c.nofollow_vol_mult * pos.breakout_volume:
                weak += 1
            else:
                break
        reached_1r = pos.plan.r_multiple(last_price) >= 1.0
        if weak >= c.nofollow_bars and not reached_1r:
            return "NO_FOLLOW_THROUGH", last_price
    return None


def trail_stop(pos: Position, ctx: SessionContext) -> int:
    """After T1 the stop rides the last N completed 5-minute bars, never loosening."""
    c = ctx.cfg
    bars5 = [b for b in ctx.bars5() if b.end <= ctx.minute][-c.trail_lookback_bars:]
    if not bars5:
        return pos.stop
    if pos.plan.side == LONG:
        return max(pos.stop, min(b.l for b in bars5))
    return min(pos.stop, max(b.h for b in bars5))
