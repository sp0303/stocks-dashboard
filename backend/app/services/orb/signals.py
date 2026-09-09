"""Stage 2 of Segment B: the strategy driver and the paper journal.

This module assembles a SessionContext from live state plus stored history, calls the
pure strategy, and records what came back — including for every candidate that was
rejected, with the rule that stopped it. "Why not this one?" is the question you
actually ask at 4pm, and it only has an answer if the rejections were written down.

Nothing here places an order. A position is a paper position; a fill is the price the
tick stream showed. The gap between that and a real fill is exactly what Segment C's
first job is to measure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.services.orb import calendar as orb_calendar
from app.services.orb import store
from app.services.orb.bars import Bar
from app.services.orb.config import DEFAULT, OrbConfig
from app.services.orb.features import (atr, cumulative_volume_curve, DailyBar,
                                       median_cum_volume_at, median_or_volume,
                                       opening_range, vwap_series)
from app.services.orb.recorder import Recorder, SymbolState
from app.services.orb.session import (IST, MARKET_OPEN, OR_END, now_ist)
from app.services.orb.strategy import (LONG, Position, SessionContext, decide, manage,
                                       plan_trade, screen, trail_stop)
from app.services.orb.universe import MARKET_INDEX, VIX_INDEX, sector_index_for

log = logging.getLogger("orb.signals")

BASELINE_SESSIONS = 10


@dataclass
class Baseline:
    """Everything about a symbol that is known before the session opens. Computed once,
    at 08:45, from completed prior sessions only — nothing here may look at today."""
    symbol: str
    token: str
    tick: int
    sector_index: str | None = None
    atr14: float | None = None
    median_or_vol: float | None = None
    cum_curves: list[dict] = field(default_factory=list)
    prev_close: int | None = None
    pdh: int | None = None
    pdl: int | None = None
    median_turnover_cr: float | None = None
    median_daily_vol: int | None = None
    surveillance: bool = False
    price_band_pct: float | None = 20.0
    event_blackout: bool = False


def prepare_day(day: str, members: list[dict],
                sessions: int = BASELINE_SESSIONS) -> dict[str, Baseline]:
    """The 08:45 job. One pass over stored history; no Angel calls."""
    prior = orb_calendar.prior_trading_days(day, sessions)
    out: dict[str, Baseline] = {}
    for m in members:
        sym = m["sym"]
        b = Baseline(symbol=sym, token=str(m["token"]), tick=int(m.get("tick") or 5),
                     sector_index=m.get("sector_index") or sector_index_for(sym),
                     median_turnover_cr=m.get("turnover_cr"))
        daily = store.load_daily(sym, limit=60)
        # ATR and previous-day levels come from completed sessions only. Slicing off any
        # row dated today is what stops gate B2 from seeing the future.
        daily = [r for r in daily if r["date"] < day]
        if daily:
            b.prev_close, b.pdh, b.pdl = daily[-1]["c"], daily[-1]["h"], daily[-1]["l"]
            b.median_daily_vol = int(sorted(r["v"] for r in daily[-20:])[len(daily[-20:]) // 2])
            b.atr14 = atr([DailyBar(r["date"], r["o"], r["h"], r["l"], r["c"], r["v"])
                           for r in daily])
        hist = store.load_sessions(sym, prior)
        or_vols, curves = [], []
        for bars in hist.values():
            o = opening_range(bars)
            if o and o.volume:
                or_vols.append(o.volume)
            curves.append(cumulative_volume_curve(bars))
        b.median_or_vol = median_or_volume(or_vols)
        b.cum_curves = curves
        out[sym] = b
    log.info("prepared %d baselines for %s from %d prior sessions",
             len(out), day, len(prior))
    return out


# ── context assembly ──────────────────────────────────────────────
def build_context(day: str, minute: int, st: SymbolState, base: Baseline,
                  market: dict, cfg: OrbConfig = DEFAULT,
                  bars: list[Bar] | None = None, **overrides) -> SessionContext:
    live = bars if bars is not None else _live_bars(st, minute)
    ctx = SessionContext(
        symbol=base.symbol, date=day, minute=minute, tick=base.tick, bars=live,
        vwap=vwap_series(live), orange=opening_range(live),
        prev_close=st.prev_close or base.prev_close, pdh=base.pdh, pdl=base.pdl,
        atr14=base.atr14, median_or_vol=base.median_or_vol,
        median_cum_vol_now=median_cum_volume_at(base.cum_curves, minute - 1),
        median_turnover_cr=base.median_turnover_cr,
        series="EQ", surveillance=base.surveillance,
        price_band_pct=base.price_band_pct, event_blackout=base.event_blackout,
        circuit_distance_pct=st.circuit_distance_pct(), feed_vwap=st.feed_vwap,
        sector_index_ret=market.get(base.sector_index) if base.sector_index else None,
        market_ret=market.get(MARKET_INDEX), vix=market.get("vix"), cfg=cfg,
    )
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _live_bars(st: SymbolState, minute: int) -> list[Bar]:
    """Bars the builder has closed so far. Read from memory rather than the database so
    a slow write never delays a decision — and so job ordering within a scheduler tick
    cannot affect what the strategy sees."""
    return st.builder.session_bars(before_minute=minute)


def index_returns(recorder: Recorder) -> dict:
    """Percent change from the previous close for every index we track. Index candles
    carry no volume, so alignment uses return, not VWAP."""
    out: dict[str, float | None] = {}
    for name, st in recorder.by_symbol.items():
        if not name.startswith("NIFTY") and name != VIX_INDEX:
            continue
        if st.last_price and st.prev_close:
            out[name] = round((st.last_price - st.prev_close) / st.prev_close * 100, 3)
    if VIX_INDEX in recorder.by_symbol:
        vix = recorder.by_symbol[VIX_INDEX]
        out["vix"] = vix.last_price / 100.0 if vix.last_price else None
    return out


# ── the 09:31 screen ──────────────────────────────────────────────
def run_screen(day: str, recorder: Recorder, baselines: dict[str, Baseline],
               cfg: OrbConfig = DEFAULT, limit: int = 8) -> dict:
    """Every candidate is written, passing or not, with its full trace."""
    market = index_returns(recorder)
    rows = []
    for sym, base in baselines.items():
        st = recorder.by_symbol.get(sym)
        if st is None:
            continue
        bars = _live_bars(st, OR_END)
        o = opening_range(bars)
        ctx = build_context(day, OR_END, st, base, market, cfg, bars=bars)
        trace = screen(ctx)
        rows.append({
            "sym": sym, "passed": trace.passed, "failed": trace.failed_rule,
            "or_high": o.high if o else None, "or_low": o.low if o else None,
            "or_width_pct": round(o.width_pct, 3) if o else None,
            "rvol": round(o.volume / base.median_or_vol, 2)
            if (o and base.median_or_vol) else None,
            "turnover_cr": round(o.turnover / 1e7, 2) if o else None,
            "trace": trace.as_list(),
        })
    passing = [r for r in rows if r["passed"]]
    passing.sort(key=lambda r: (r["rvol"] or 0), reverse=True)
    shortlist = [r["sym"] for r in passing[:limit]]
    doc = {"_id": f"{day}:screen", "date": day, "kind": "screen",
           "candidates": len(rows), "passed": len(passing), "shortlist": shortlist,
           "rows": rows, "config": cfg.version, "at": datetime.now(IST).isoformat()}
    store.put(store.SIGNALS, doc)
    log.info("screen %s: %d/%d passed; shortlist %s", day, len(passing), len(rows),
             shortlist)
    return doc


# ── the paper book ────────────────────────────────────────────────
class PaperBook:
    """Open positions and the day's realised result. Deliberately small: this records
    what the rules did, it does not try to be a broker."""

    def __init__(self, day: str, cfg: OrbConfig = DEFAULT):
        self.day = day
        self.cfg = cfg
        self.open: dict[str, Position] = {}
        self.closed: list[dict] = []
        self.day_r = 0.0
        self.consecutive_losses = 0
        self.dead: set[str] = set()
        self.traded: set[str] = set()

    def can_open(self, sym: str) -> bool:
        return (sym not in self.open and sym not in self.dead
                and len(self.open) < self.cfg.max_concurrent
                and len(self.traded) < self.cfg.max_trades_per_day)

    def enter(self, sym: str, plan, minute: int, breakout_volume: int,
              trace: list) -> Position:
        pos = Position(symbol=sym, plan=plan, entry_minute=minute,
                       breakout_volume=breakout_volume, qty_open=plan.qty,
                       stop=plan.stop)
        self.open[sym] = pos
        self.traded.add(sym)
        store.put(store.SIGNALS, {
            "_id": f"{self.day}:{sym}:{minute}", "date": self.day, "sym": sym,
            "kind": "entry", "minute": minute, "side": plan.side, "entry": plan.entry,
            "stop": plan.stop, "t1": plan.t1, "t2": plan.t2, "qty": plan.qty,
            "risk": plan.risk, "config": self.cfg.version, "trace": trace,
            "at": datetime.now(IST).isoformat()})
        log.info("ENTER %s %s @%d stop %d t1 %d t2 %d qty %d", sym,
                 "LONG" if plan.side == LONG else "SHORT", plan.entry, plan.stop,
                 plan.t1, plan.t2, plan.qty)
        return pos

    def exit(self, sym: str, reason: str, price: int, minute: int,
             fraction: float = 1.0) -> dict:
        pos = self.open[sym]
        qty = int(pos.qty_open * fraction) or pos.qty_open
        r = pos.plan.r_multiple(price) * (qty / pos.plan.qty)
        pos.qty_open -= qty
        rec = {"date": self.day, "sym": sym, "reason": reason, "price": price,
               "minute": minute, "qty": qty, "r": round(r, 3),
               "side": pos.plan.side, "entry": pos.plan.entry, "stop": pos.stop,
               "config": self.cfg.version, "at": datetime.now(IST).isoformat()}
        self.day_r += r
        self.closed.append(rec)
        store.get_db()[store.JOURNAL].insert_one(dict(rec))
        if pos.qty_open <= 0:
            self.open.pop(sym, None)
            if r < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
        log.info("EXIT %s %s @%d qty %d -> %.2fR", sym, reason, price, qty, r)
        return rec


# ── per-bar evaluation ────────────────────────────────────────────
def run_decide(day: str, minute: int, recorder: Recorder,
               baselines: dict[str, Baseline], shortlist: list[str],
               book: PaperBook, cfg: OrbConfig = DEFAULT) -> list[dict]:
    market = index_returns(recorder)
    fired = []
    for sym in shortlist:
        st, base = recorder.by_symbol.get(sym), baselines.get(sym)
        if st is None or base is None or not book.can_open(sym):
            continue
        ctx = build_context(day, minute, st, base, market, cfg,
                            dead=sym in book.dead, traded_today=len(book.traded),
                            open_positions=len(book.open), day_r=book.day_r,
                            consecutive_losses=book.consecutive_losses)
        d = decide(ctx)
        if "trap" in d.reason:
            book.dead.add(sym)                     # D4 kills the symbol for the session
        if not d.entered:
            continue
        # Fill at the next tick, not at the bar close we are reacting to: by the time
        # this runs, that close is already history.
        fill = st.last_price or d.trigger
        slip = max(base.tick, int(fill * cfg.slippage_entry_pct / 100))
        fill += slip * d.side
        plan = plan_trade(cfg, d.side, fill, d.stop, d.or_width, base.median_daily_vol)
        if plan is None:
            continue
        bar5 = [b for b in ctx.bars5() if b.end <= minute]
        book.enter(sym, plan, minute, bar5[-1].v if bar5 else 0, d.trace.as_list())
        fired.append({"sym": sym, "side": d.side, "entry": plan.entry})
    return fired


def run_manage(day: str, minute: int, recorder: Recorder,
               baselines: dict[str, Baseline], book: PaperBook,
               cfg: OrbConfig = DEFAULT) -> list[dict]:
    market = index_returns(recorder)
    events = []
    for sym in list(book.open):
        st, base = recorder.by_symbol.get(sym), baselines.get(sym)
        if st is None or base is None or st.last_price is None:
            continue
        pos = book.open[sym]
        ctx = build_context(day, minute, st, base, market, cfg)
        out = manage(pos, ctx, st.last_price)
        if out is None:
            if pos.t1_done:
                pos.stop = trail_stop(pos, ctx)
            continue
        reason, price = out
        if reason == "T1" and not pos.t1_done:
            book.exit(sym, "T1", price, minute, cfg.t1_book_fraction)
            pos.t1_done = True
            pos.stop = pos.plan.entry            # stop to cost, per the rulebook
            events.append({"sym": sym, "event": "T1"})
        else:
            book.exit(sym, reason, price, minute)
            events.append({"sym": sym, "event": reason})
    return events


def square_off(day: str, minute: int, recorder: Recorder, book: PaperBook) -> list[dict]:
    """15:10, unconditional. The one event in the day with no conditions on it."""
    out = []
    for sym in list(book.open):
        st = recorder.by_symbol.get(sym)
        price = st.last_price if st and st.last_price else book.open[sym].plan.entry
        out.append(book.exit(sym, "SQUARE_OFF", price, minute))
    return out


def day_summary(day: str) -> dict:
    trades = store.find(store.JOURNAL, {"date": day})
    total_r = sum(t.get("r", 0) for t in trades)
    wins = [t for t in trades if t.get("r", 0) > 0]
    return {"date": day, "trades": len(trades), "total_r": round(total_r, 2),
            "wins": len(wins),
            "win_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
            "by_reason": _count(t.get("reason") for t in trades)}


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out
