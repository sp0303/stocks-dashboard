#!/usr/bin/env python
"""Segment C — the replay driver the architecture reserved a place for.

It reads the same Mongo store the live engine writes (`orb_candles_1m`, `orb_candles_1d`)
and drives the *identical* pure strategy core — screen(), decide(), plan_trade(), manage(),
trail_stop() — so a backtest number and a Monday-morning signal are produced by one
implementation. Nothing in this file re-expresses a trading rule; it only assembles the
SessionContext the rules read and books the fills the rules imply.

    python scripts/orb_backtest.py                       # full universe, all stored days
    python scripts/orb_backtest.py --symbols SBIN,BSE    # a subset, for validation
    python scripts/orb_backtest.py --start 2025-01-01 --end 2025-06-30
    python scripts/orb_backtest.py --out /root/orb_bt    # write trades.csv + summary.json

── modelling choices (stated, because they move the numbers) ──────────────────────────
  * Portfolio simulation. All screened symbols compete for the day's shared budget:
    max_concurrent, max_trades_per_day, daily_stop_r, max_consecutive_losses (F1-F4).
    When more signals fire on one 5-minute bar than there is capacity, the stronger
    close (C6 close_strength) is taken first.
  * No look-ahead. ATR and every RVOL baseline use *prior completed sessions only*
    (enforced by features.py); the screen runs at 09:31; entries only on a completed
    5-minute bar inside the entry window.
  * Fills. Entry at the breakout bar's close plus entry slippage. Stops and targets are
    detected on the 1-minute high/low that follows; when a bar's range spans both the
    stop and a target, the stop is assumed first (pessimistic). Stop exits pay the wider
    stop slippage. All costs (brokerage, STT, txn, stamp, SEBI, GST) from OrbConfig.
  * Not modelled — therefore slightly MORE permissive than the live path will be:
      D5/D6  sector / market alignment  — no index minute data in the store (auto-pass)
      A4-A7  surveillance / band / circuit / event blackout / VIX (auto-pass)
      D7     VWAP-vs-feed drift          — websocket-only
    A market-alignment proxy from NIFTYBEES is applied when --market-proxy is set.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import statistics
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orb import store                                          # noqa: E402
from app.services.orb.bars import Bar                                       # noqa: E402
from app.services.orb.config import DEFAULT, OrbConfig                      # noqa: E402
from app.services.orb.features import (DailyBar, atr, cumulative_volume_curve,  # noqa: E402
                                       median_cum_volume_at, median_or_volume,
                                       opening_range, resample, vwap_series)
from app.services.orb.session import (ENTRY_CUTOFF, ENTRY_FIRST, MARKET_CLOSE,   # noqa: E402
                                      MARKET_OPEN, OR_END, SQUARE_OFF, hhmm)
from app.services.orb.universe import INDEX_TOKENS, MARKET_INDEX, VIX_INDEX  # noqa: E402
from app.services.orb.strategy import (LONG, Position, _stop_for, decide,  # noqa: E402
                                       manage, plan_trade, screen, trail_stop)

RVOL_LOOKBACK = 10       # prior sessions for OR-volume / cum-volume medians
TURNOVER_LOOKBACK = 20   # prior sessions for A2 median traded value and sizing


# ── cost model (reuses OrbConfig's numbers; matches the paper journal) ─────────────────
def _round_trip_cost(cfg: OrbConfig, buy_val: float, sell_val: float) -> float:
    """All statutory + broker charges for one buy leg and one sell leg, in rupees."""
    turnover = buy_val + sell_val
    brokerage = min(cfg.brokerage_pct / 100 * buy_val, cfg.brokerage_cap) + \
        min(cfg.brokerage_pct / 100 * sell_val, cfg.brokerage_cap)
    stt = cfg.stt_sell_pct / 100 * sell_val
    exch = cfg.exchange_txn_pct / 100 * turnover
    stamp = cfg.stamp_buy_pct / 100 * buy_val
    sebi = cfg.sebi_per_crore * turnover / 1e7
    gst = cfg.gst_pct / 100 * (brokerage + exch + sebi)
    return brokerage + stt + exch + stamp + sebi + gst


@dataclass
class Trade:
    date: str
    symbol: str
    side: int
    entry_minute: int
    exit_minute: int
    entry: float          # rupees, incl. slippage
    exit: float           # rupees, blended over partial exits
    qty: int
    gross: float          # rupees
    cost: float           # rupees
    net: float            # rupees
    r: float              # net / risk_rupees
    reason: str
    feat: dict | None = None   # entry-time context features, for filter analysis


# ── one symbol's static setup for a given day (levels, ATR, RVOL baselines) ────────────
@dataclass
class DaySetup:
    bars: list[Bar]
    orange: object
    prev_close: int | None
    pdh: int | None
    pdl: int | None
    atr14: float | None
    median_or_vol: float | None
    cum_curves: list
    median_turnover_cr: float | None
    median_daily_vol: int | None
    tick: int
    series: str


def _daily_context(rows: list[dict], day: str):
    """prev_close / PDH / PDL / ATR14 / median turnover / median daily volume from days
    strictly before `day` — no leak of today into any baseline."""
    prior = [r for r in rows if r["date"] < day]
    if not prior:
        return None, None, None, None, None, None
    last = prior[-1]
    dbars = [DailyBar(date=r["date"], o=r["o"], h=r["h"], l=r["l"], c=r["c"], v=r["v"])
             for r in prior]
    a = atr(dbars, 14)
    recent = prior[-TURNOVER_LOOKBACK:]
    turnovers = [r["v"] * r["c"] / 1e9 for r in recent]           # paise*shares -> Rs cr
    vols = [r["v"] for r in recent]
    med_turn = statistics.median(turnovers) if turnovers else None
    med_vol = int(statistics.median(vols)) if vols else None
    return last["c"], last["h"], last["l"], a, med_turn, med_vol


def _ret_series(bars) -> dict[int, float]:
    """{minute: % change of the index close since 09:15} for one session."""
    if not bars:
        return {}
    anchor = next((b.c for b in bars if b.minute == MARKET_OPEN), None) or bars[0].c
    return {b.minute: (b.c / anchor - 1) * 100.0 for b in bars} if anchor else {}


def build_context(sym, day, minute, setup: DaySetup, cfg, *,
                  dead=False, traded_today=0, open_positions=0, day_r=0.0,
                  consecutive_losses=0, mret_series=None, sret_series=None,
                  sym_sector=None, vix_val=None, blackout=None):
    from app.services.orb.strategy import SessionContext
    upto = [b for b in setup.bars if b.minute <= minute]
    vw = vwap_series(upto)
    market_ret = mret_series.get(minute) if mret_series else None
    sector = sym_sector.get(sym) if sym_sector else None
    sector_ret = sret_series.get(sector, {}).get(minute) if (sret_series and sector) else None
    return SessionContext(
        symbol=sym, date=day, minute=minute,
        tick=setup.tick, bars=upto, vwap=vw, orange=setup.orange,
        prev_close=setup.prev_close, pdh=setup.pdh, pdl=setup.pdl,
        atr14=setup.atr14, median_or_vol=setup.median_or_vol,
        median_cum_vol_now=median_cum_volume_at(setup.cum_curves, minute),
        median_turnover_cr=setup.median_turnover_cr,
        series=setup.series, market_ret=market_ret, sector_index_ret=sector_ret,
        vix=vix_val, event_blackout=bool(blackout and day in blackout.get(sym, ())),
        dead=dead, traded_today=traded_today, open_positions=open_positions,
        day_r=day_r, consecutive_losses=consecutive_losses, cfg=cfg,
    )


# ── simulate one open position minute-by-minute, reusing manage()/trail_stop() ─────────
def _run_position(pos: Position, setup: DaySetup, sym, day, cfg, *, entry_fill):
    """Walk the 1-minute bars after entry, calling manage() at the adverse extreme (stop),
    the favourable extreme (target) and the close (no-follow / square-off). Returns a
    fully-resolved Trade."""
    side = pos.plan.side
    booked_qty, booked_val = 0, 0.0   # rupees notional actually exited
    exit_minute = SQUARE_OFF
    reason = "SQUARE_OFF"

    def px(paise, adverse):
        slip = cfg.slippage_stop_pct if adverse else 0.0
        adj = 1 - slip / 100 if side == LONG else 1 + slip / 100
        return paise / 100 * adj

    minutes = [b for b in setup.bars if b.minute > pos.entry_minute]
    for b in minutes:
        m = b.minute
        five_close = (m - MARKET_OPEN) % cfg.signal_timeframe_min == (cfg.signal_timeframe_min - 1)
        ctx = build_context(sym, day, m, setup, cfg, open_positions=1)

        if five_close and pos.t1_done:
            pos.stop = trail_stop(pos, ctx)

        adverse = b.l if side == LONG else b.h
        favour = b.h if side == LONG else b.l

        # 1) stop first, on the adverse extreme
        r = manage(pos, ctx, adverse)
        if r and r[0] in ("STOP", "TRAIL", "SQUARE_OFF"):
            q = pos.qty_open
            booked_qty += q
            booked_val += q * px(r[1], adverse=(r[0] in ("STOP", "TRAIL")))
            pos.qty_open = 0
            exit_minute, reason = m, r[0]
            break
        # 2) target on the favourable extreme
        r = manage(pos, ctx, favour)
        if r and r[0] == "T1" and not pos.t1_done:
            q = int(round(pos.plan.qty * cfg.t1_book_fraction))
            q = min(q, pos.qty_open)
            booked_qty += q
            booked_val += q * (r[1] / 100)
            pos.qty_open -= q
            pos.t1_done = True
            if pos.qty_open <= 0:
                exit_minute, reason = m, "T1"
                break
            continue
        if r and r[0] == "T2":
            q = pos.qty_open
            booked_qty += q
            booked_val += q * (r[1] / 100)
            pos.qty_open = 0
            exit_minute, reason = m, "T2"
            break
        # 3) no-follow / square-off on the close
        r = manage(pos, ctx, b.c)
        if r and r[0] in ("NO_FOLLOW_THROUGH", "SQUARE_OFF"):
            q = pos.qty_open
            booked_qty += q
            booked_val += q * (b.c / 100)
            pos.qty_open = 0
            exit_minute, reason = m, r[0]
            break
    else:
        # never exited (ran out of bars): flat at the last close
        last = minutes[-1] if minutes else None
        if last and pos.qty_open:
            booked_val += pos.qty_open * (last.c / 100)
            booked_qty += pos.qty_open
            exit_minute = last.minute
            pos.qty_open = 0

    entry_val = pos.plan.qty * entry_fill
    exit_price = booked_val / booked_qty if booked_qty else entry_fill
    gross = (booked_val - entry_val) if side == LONG else (entry_val - booked_val)
    if side == LONG:
        cost = _round_trip_cost(cfg, entry_val, booked_val)
    else:
        cost = _round_trip_cost(cfg, booked_val, entry_val)
    net = gross - cost
    risk_rupees = pos.plan.risk / 100 * pos.plan.qty
    r_mult = net / risk_rupees if risk_rupees else 0.0
    return Trade(date=day, symbol=sym, side=side, entry_minute=pos.entry_minute,
                 exit_minute=exit_minute, entry=round(entry_fill, 2),
                 exit=round(exit_price, 2), qty=pos.plan.qty, gross=round(gross, 2),
                 cost=round(cost, 2), net=round(net, 2), r=round(r_mult, 3), reason=reason)


# ── one trading day across the whole screened set ─────────────────────────────────────
def simulate_day(day, setups: dict[str, DaySetup], cfg, confirm_min=0,
                 mret_series=None, sret_series=None, sym_sector=None,
                 vix_val=None, blackout=None) -> list[Trade]:
    idx = dict(mret_series=mret_series, sret_series=sret_series,
               sym_sector=sym_sector, vix_val=vix_val, blackout=blackout)
    screened = {}
    for sym, s in setups.items():
        if s.orange is None:
            continue
        ctx = build_context(sym, day, OR_END + 1, s, cfg, **idx)
        if screen(ctx).passed:
            screened[sym] = s
    if not screened:
        return []

    trades: list[Trade] = []
    dead: set[str] = set()
    open_syms: set[str] = set()
    traded_today = 0
    day_r = 0.0
    consecutive_losses = 0

    # entries are judged only on completed 5-minute bar closes inside the window
    boundaries = [m for m in range(ENTRY_FIRST, ENTRY_CUTOFF + 1)
                  if (m - MARKET_OPEN) % cfg.signal_timeframe_min == 0]
    for m in boundaries:
        if traded_today >= cfg.max_trades_per_day or len(open_syms) >= cfg.max_concurrent:
            continue
        if day_r <= cfg.daily_stop_r or consecutive_losses >= cfg.max_consecutive_losses:
            break
        candidates = []
        for sym, s in screened.items():
            if sym in open_syms or sym in dead:
                continue
            ctx = build_context(sym, day, m, s, cfg, dead=(sym in dead),
                                traded_today=traded_today, open_positions=len(open_syms),
                                day_r=day_r, consecutive_losses=consecutive_losses, **idx)
            d = decide(ctx)
            if d.reason.startswith("trap"):
                dead.add(sym)
                continue
            if not d.entered:
                continue
            bar5 = [b for b in resample(ctx.bars, cfg.signal_timeframe_min) if b.end <= m][-1]
            candidates.append((bar5.close_strength(d.side), sym, s, d, ctx))
        # strongest close first when capacity is scarce
        candidates.sort(reverse=True, key=lambda x: x[0])
        for _, sym, s, d, ctx in candidates:
            if traded_today >= cfg.max_trades_per_day or len(open_syms) >= cfg.max_concurrent:
                break

            # ── entry confirmation: wait `confirm_min` and require the breakout to still
            # hold beyond the opening-range edge; a close back inside the range within the
            # window is a failed breakout we skip instead of trading into a reversal.
            # The STRUCTURAL stop from the 5-minute breakout bar (d.stop) is kept — the
            # 1-minute bar's own low is far too tight and blows R up. A guard skips a
            # pulled-back fill that would sit too close to that stop (tiny risk -> big R).
            entry_minute, trigger, stop = m, d.trigger, d.stop
            if confirm_min > 0:
                cbar = next((b for b in s.bars if b.minute == m + confirm_min), None)
                if cbar is None:
                    continue
                holds = cbar.c > s.orange.high if d.side == LONG else cbar.c < s.orange.low
                if not holds:
                    continue
                r_orig = (d.trigger - stop) if d.side == LONG else (stop - d.trigger)
                r_conf = (cbar.c - stop) if d.side == LONG else (stop - cbar.c)
                if r_orig <= 0 or r_conf <= 0.5 * r_orig:
                    continue
                entry_minute, trigger = m + confirm_min, cbar.c

            slip = 1 + cfg.slippage_entry_pct / 100 if d.side == LONG \
                else 1 - cfg.slippage_entry_pct / 100
            entry_fill = trigger / 100 * slip
            entry_paise = int(round(entry_fill * 100))
            plan = plan_trade(cfg, d.side, entry_paise, stop, d.or_width, s.median_daily_vol)
            if plan is None:
                continue

            bar5 = [b for b in resample(s.bars, cfg.signal_timeframe_min) if b.end <= m][-1]
            pos = Position(symbol=sym, plan=plan, entry_minute=entry_minute,
                           breakout_volume=bar5.v, qty_open=plan.qty, stop=plan.stop)
            tr = _run_position(pos, s, sym, day, cfg, entry_fill=entry_fill)
            gap = None
            if s.prev_close:
                fb = next((b for b in s.bars if not b.syn), None)
                gap = (fb.o - s.prev_close) / s.prev_close * 100.0 if fb else None
            cum = sum(b.v for b in ctx.bars if b.minute < m)
            tr.feat = {
                "entry_min": m,
                "side": "LONG" if d.side == LONG else "SHORT",
                "gap_pct": round(gap, 2) if gap is not None else None,
                "or_width_pct": round(s.orange.width_pct, 3),
                "rvol_or": round(s.orange.volume / s.median_or_vol, 2) if s.median_or_vol else None,
                "or_turn_cr": round(s.orange.turnover / 1e7, 2),
                "atr_pct": round(s.atr14 / entry_paise * 100, 2) if s.atr14 else None,
                "risk_pct": round(plan.risk / entry_paise * 100, 3),
                "close_str": round(bar5.close_strength(d.side), 2),
                "vwap_slope": (round(ctx.vwap.slope_pct(m, cfg.vwap_slope_lookback_min), 3)
                               if ctx.vwap.slope_pct(m, cfg.vwap_slope_lookback_min) is not None else None),
                "cum_rvol": (round(cum / median_cum_volume_at(s.cum_curves, m), 2)
                             if median_cum_volume_at(s.cum_curves, m) else None),
                "mkt_ret": round(ctx.market_ret, 2) if ctx.market_ret is not None else None,
                "sec_ret": round(ctx.sector_index_ret, 2) if ctx.sector_index_ret is not None else None,
                "vix": round(ctx.vix, 1) if ctx.vix is not None else None,
                "dow": _dt.date.fromisoformat(day).strftime("%a"),
            }
            trades.append(tr)
            traded_today += 1
            open_syms.add(sym)          # one trade per symbol per day (screened once)
            day_r += tr.r
            consecutive_losses = consecutive_losses + 1 if tr.r < 0 else 0
    return trades


# ── driver ────────────────────────────────────────────────────────────────────────────
def run(symbols=None, start=None, end=None, cfg=DEFAULT, market_proxy=False,
        confirm_min=0, progress=True):
    db = store.get_db()
    universe = {m["sym"]: m for m in (db["orb_universe"].find_one() or {}).get("members", [])}
    if symbols:
        want = set(symbols)
    else:
        want = set(universe) or set(store.daily_symbols())

    all_days = sorted({d["date"] for d in db[store.CANDLES_1M].find({}, {"date": 1, "_id": 0})})
    if start:
        all_days = [d for d in all_days if d >= start]
    if end:
        all_days = [d for d in all_days if d <= end]

    daily_rows = {s: store.load_daily(s) for s in want}
    rolling: dict[str, deque] = defaultdict(lambda: deque(maxlen=RVOL_LOOKBACK))
    sym_sector = {m["sym"]: m.get("sector_index")
                  for m in (db["orb_universe"].find_one() or {}).get("members", [])}
    index_names = set(INDEX_TOKENS)

    # A4 ex-date blackout: ex_date +/- event_blackout_days, per symbol, from the app's
    # corporate_actions store. Covers dividends/splits/bonuses; earnings-result dates are
    # not stored and would need an external calendar.
    from datetime import date as _date, timedelta as _td
    blackout: dict[str, set] = defaultdict(set)
    for ca in db["corporate_actions"].find({}, {"symbol": 1, "ex_date": 1, "_id": 0}):
        ex = ca.get("ex_date")
        if not (ca.get("symbol") and ex):
            continue
        try:
            d0 = _date.fromisoformat(ex)
        except ValueError:
            continue
        for k in range(-cfg.event_blackout_days, cfg.event_blackout_days + 1):
            blackout[ca["symbol"]].add((d0 + _td(days=k)).isoformat())

    trades: list[Trade] = []
    for i, day in enumerate(all_days):
        docs = list(db[store.CANDLES_1M].find({"date": day}))
        by_sym = {doc["sym"]: store.doc_to_bars(doc) for doc in docs if doc["sym"] in want}

        # index + VIX series for this day (same query; indices share the collection)
        idx_bars = {doc["sym"]: store.doc_to_bars(doc)
                    for doc in docs if doc["sym"] in index_names}
        mret_series = _ret_series(idx_bars.get(MARKET_INDEX, []))
        sret_series = {name: _ret_series(bars) for name, bars in idx_bars.items()}
        vixb = idx_bars.get(VIX_INDEX, [])
        vix_val = next((b.c / 100.0 for b in vixb if b.minute == MARKET_OPEN),
                       (vixb[0].c / 100.0 if vixb else None))

        setups = {}
        for sym, bars in by_sym.items():
            if sym in index_names:
                continue
            rows = daily_rows.get(sym) or []
            pc, pdh, pdl, a, mturn, mvol = _daily_context(rows, day)
            win = rolling[sym]
            setups[sym] = DaySetup(
                bars=bars, orange=opening_range(bars), prev_close=pc, pdh=pdh, pdl=pdl,
                atr14=a, median_or_vol=median_or_volume([w["or_vol"] for w in win]),
                cum_curves=[w["curve"] for w in win], median_turnover_cr=mturn,
                median_daily_vol=mvol,
                tick=universe.get(sym, {}).get("tick", 5),
                series=universe.get(sym, {}).get("series", "EQ"),
            )

        trades.extend(simulate_day(day, setups, cfg, confirm_min=confirm_min,
                                   mret_series=mret_series, sret_series=sret_series,
                                   sym_sector=sym_sector, vix_val=vix_val, blackout=blackout))

        # push today into each symbol's rolling RVOL window (prior-sessions-only for tomorrow)
        for sym, bars in by_sym.items():
            if sym in index_names:
                continue
            o = opening_range(bars)
            rolling[sym].append({
                "or_vol": o.volume if o else 0,
                "curve": cumulative_volume_curve(bars),
                "turnover": o.turnover if o else 0.0,
            })
        if progress and (i % 25 == 0 or i == len(all_days) - 1):
            print(f"  {day}  ({i+1}/{len(all_days)})  trades so far: {len(trades)}",
                  file=sys.stderr)
    return trades, all_days


# ── reporting ─────────────────────────────────────────────────────────────────────────
def summarise(trades: list[Trade], days, cfg=DEFAULT):
    if not trades:
        return {"trades": 0, "note": "no trades"}
    nets = [t.net for t in trades]
    rs = [t.r for t in trades]
    wins = [t for t in trades if t.net > 0]
    losses = [t for t in trades if t.net <= 0]
    gross_win = sum(t.net for t in wins)
    gross_loss = -sum(t.net for t in losses)
    total = sum(nets)

    # equity curve day by day for max drawdown
    by_day = defaultdict(float)
    for t in trades:
        by_day[t.date] += t.net
    eq, peak, maxdd = cfg.capital, cfg.capital, 0.0
    for d in sorted(by_day):
        eq += by_day[d]
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)

    reasons = defaultdict(int)
    for t in trades:
        reasons[t.reason] += 1

    return {
        "trades": len(trades),
        "trading_days": len(days),
        "days_with_trades": len(by_day),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1),
        "avg_R": round(statistics.mean(rs), 3),
        "expectancy_R": round(statistics.mean(rs), 3),
        "median_R": round(statistics.median(rs), 3),
        "avg_win_R": round(statistics.mean([t.r for t in wins]), 3) if wins else 0,
        "avg_loss_R": round(statistics.mean([t.r for t in losses]), 3) if losses else 0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "net_pnl_rs": round(total, 0),
        "return_on_capital_pct": round(100 * total / cfg.capital, 1),
        "max_drawdown_rs": round(maxdd, 0),
        "max_drawdown_pct": round(100 * maxdd / cfg.capital, 1),
        "avg_trades_per_active_day": round(len(trades) / len(by_day), 2),
        "long": sum(1 for t in trades if t.side == LONG),
        "short": sum(1 for t in trades if t.side != LONG),
        "exit_reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])),
        "best_trade_R": round(max(rs), 2),
        "worst_trade_R": round(min(rs), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="comma-separated subset (default: full universe)")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--market-proxy", action="store_true",
                    help="use NIFTYBEES as a market-alignment proxy for D6")
    ap.add_argument("--confirm-min", type=int, default=0,
                    help="wait N minutes after the breakout and require it still holds")
    ap.add_argument("--no-align", action="store_true",
                    help="disable D5/D6 sector+market alignment gates")
    ap.add_argument("--quality", action="store_true",
                    help="apply the loss-analysis quality floors (risk/ATR/slope, no align)")
    ap.add_argument("--out", help="directory to write trades.csv + summary.json")
    args = ap.parse_args()

    cfg = DEFAULT
    if args.quality:
        cfg = DEFAULT.with_overrides(min_risk_pct=0.6, min_atr_pct=3.2,
                                     vwap_slope_min_pct=0.15,
                                     require_sector_alignment=False,
                                     require_market_alignment=False)
    elif args.no_align:
        cfg = DEFAULT.with_overrides(require_sector_alignment=False,
                                     require_market_alignment=False)

    syms = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    trades, days = run(symbols=syms, start=args.start, end=args.end, cfg=cfg,
                       market_proxy=args.market_proxy, confirm_min=args.confirm_min)
    summary = summarise(trades, days)

    print("\n================  ORB BACKTEST  ================")
    span = f"{days[0]} .. {days[-1]}" if days else "(no days)"
    print(f"universe: {'subset ' + ','.join(syms) if syms else 'full (200)'}   span: {span}")
    print(f"settings: confirm_min={args.confirm_min}  B5=on(core)  "
          f"market_proxy={args.market_proxy}")
    for k, v in summary.items():
        print(f"  {k:26} {v}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "trades.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "symbol", "side", "entry_min", "exit_min", "entry",
                        "exit", "qty", "gross", "cost", "net", "R", "reason"])
            for t in trades:
                w.writerow([t.date, t.symbol, "LONG" if t.side == LONG else "SHORT",
                            hhmm(t.entry_minute), hhmm(t.exit_minute), t.entry, t.exit,
                            t.qty, t.gross, t.cost, t.net, t.r, t.reason])
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        # per-trade features for filter analysis
        feat_keys = list(next((t.feat for t in trades if t.feat), {}).keys())
        with open(out / "features.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "symbol", "R", "net", "reason", "win"] + feat_keys)
            for t in trades:
                fe = t.feat or {}
                w.writerow([t.date, t.symbol, t.r, t.net, t.reason, int(t.net > 0)]
                           + [fe.get(k) for k in feat_keys])
        print(f"\nwrote {out/'trades.csv'}, {out/'summary.json'}, {out/'features.csv'}")


if __name__ == "__main__":
    main()
