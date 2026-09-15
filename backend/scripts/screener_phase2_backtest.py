#!/usr/bin/env python
"""Phase 2 — does each labelled setup carry its own edge, validated separately?

Phase 1 judged one blended composite. Phase 2 splits the screen into named setups
(`app.services.screener_setups`) and holds each to its own bar. A setup that cannot clear
it never ships — that is the whole discipline of this phase.

For every rebalance date, each scored stock is classified, then its trade is *path
simulated* forward on daily highs/lows using the setup's own geometry (ATR stop, ATR
target, max hold): whichever of stop / target the price touches first decides the outcome,
so the number is an honest first-touch expectancy, not a horizon average that ignores the
stop. Results are expressed in **R** (multiples of the initial ATR risk), net of a
round-trip cost, and broken down by sub-period and sector.

  python scripts/screener_phase2_backtest.py --every 5 --cost 0.30 --min-adv 5000000
  python scripts/screener_phase2_backtest.py --stop 2.0 --min-n 100

GATE (per tradable setup): n >= --min-n AND mean expectancy in R > 0. EXTENDED is not a
book — it passes when it is confirmed an *inferior* long (expectancy below every tradable
setup), so the label earns its "avoid" rather than hiding a setup.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import screener_backtest as bt                                    # noqa: E402  reuse loader
from app.services import screener_factors as F                    # noqa: E402
from app.services import screener_regime as R                     # noqa: E402
from app.services import screener_setups as S                     # noqa: E402


def first_touch(rows, i, entry, stop_price, target_price, horizon):
    """Walk forward from i, return (outcome, hold_days, exit_price). Same-day ambiguity
    (both stop and target inside one bar) resolves to the stop — the conservative read."""
    last = min(i + horizon, len(rows) - 1)
    for d in range(i + 1, last + 1):
        hi, lo = rows[d]["h"] / 100, rows[d]["l"] / 100
        hit_stop = lo <= stop_price
        hit_tgt = hi >= target_price
        if hit_stop:
            return ("stop", d - i, stop_price)
        if hit_tgt:
            return ("target", d - i, target_price)
    return ("time", last - i, rows[last]["c"] / 100)             # neither: exit on close


def _breadth(uni, as_of):
    """Share of the universe trading above its own 200-DMA on `as_of` — the same risk-on
    gauge Phase 1 uses. Cheap: reads the cached close series, no row slicing."""
    above = tot = 0
    for v in uni.values():
        i = v["idx"].get(as_of)
        if i is None or i < 200:
            continue
        c = v["closes"]
        dma200 = sum(c[i - 199: i + 1]) / 200
        tot += 1
        if c[i] > dma200:
            above += 1
    return (above / tot * 100) if tot else 0.0


def _composite_top(uni, as_of, min_adv, keep_pct, comp):
    """Symbols in the top `keep_pct`% of the Phase-1 composite rank on `as_of`. Lets Phase 2
    ask: do the setups firm up when we only take them on names the *validated* ranking
    already likes? Returns None if the cross-section is too thin to rank."""
    raw_by = {}
    for sym, v in uni.items():
        i = v["idx"].get(as_of)
        if i is None or i < bt.MIN_HISTORY:
            continue
        rows = v["rows"][max(0, i - bt.WINDOW + 1): i + 1]
        if min_adv and (F.adv_rupees(rows) or 0) < min_adv:
            continue
        raw_by[sym] = F.raw_factors(rows)
    if len(raw_by) < 20:
        return set()
    scores = comp.score_universe(raw_by)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    keep = max(1, int(len(ranked) * keep_pct / 100))
    return {s for s, _ in ranked[:keep]}


def _market_returns(uni):
    """Equal-weight universe daily return per date: mean over symbols of close-to-close %.
    The series whose trailing volatility drives the Barroso–Santa-Clara exposure scale."""
    acc: dict[str, list[float]] = defaultdict(list)
    for v in uni.items() if False else uni.values():
        c, dates = v["closes"], v["dates"]
        for i in range(1, len(c)):
            if c[i - 1]:
                acc[dates[i]].append((c[i] - c[i - 1]) / c[i - 1])
    return {d: (sum(rs) / len(rs)) for d, rs in acc.items() if rs}


def _crash_scales(uni, rebal, signal, lookback, cap):
    """Per-rebalance-date exposure scale from a crash signal, using only past data at each
    date. `signal`: 'sma' (trailing realized vol, the laggy baseline), 'ewma' (faster-reacting
    vol), or 'drawdown' (market index below its trailing peak — price-based, more leading).
    Vol signals calibrate their target to the series median so average exposure ≈ 1; drawdown
    needs no target. Returns (scales_by_date, info_string)."""
    mret = _market_returns(uni)
    mdates = sorted(mret)
    series = [mret[d] for d in mdates]
    pos = {d: i for i, d in enumerate(mdates)}

    if signal == "drawdown":
        idx, cum = [], 1.0                              # cumulative equal-weight market index
        for r in series:
            cum *= (1 + r)
            idx.append(cum)
        scales = {}
        for d in rebal:
            i = pos.get(d)
            scales[d] = 1.0 if i is None else R.drawdown_scale(R.drawdown_from_peak(idx[: i + 1]))
        return scales, "drawdown knee -10%"

    vol_fn = R.ewma_vol if signal == "ewma" else R.realized_vol
    rv_by = {}
    for d in rebal:
        i = pos.get(d)
        if i is None:
            continue
        rv = vol_fn(series[: i + 1], lookback)
        if rv:
            rv_by[d] = rv
    target = R.calibrate_target(list(rv_by.values()))
    if not target:
        return {d: 1.0 for d in rebal}, None
    return {d: R.vol_scale(rv_by.get(d), target, cap) for d in rebal}, f"{signal} target {target:.4f}"


def run(every=5, start=None, end=None, cost_pct=0.30, min_adv=0.0, min_n=60,
        regime_breadth=0.0, composite_top_pct=0.0, crash_signal="none", vol_lookback=63,
        vol_cap=2.5, progress=True):
    uni = bt.load_universe()
    if not uni:
        raise SystemExit("no daily data — is the Mongo store populated?")
    comp = F.Composite()

    all_dates = sorted({d for v in uni.values() for d in v["dates"]})
    if start:
        all_dates = [d for d in all_dates if d >= start]
    if end:
        all_dates = [d for d in all_dates if d <= end]
    max_h = max(g["horizon"] for g in S.SETUP_GEOMETRY.values())
    rebal = all_dates[bt.MIN_HISTORY::every]
    rebal = [d for d in rebal if d <= all_dates[-max_h - 1]] if len(all_dates) > max_h else []
    if not rebal:
        raise SystemExit("not enough history for the longest setup horizon")

    mid_date = rebal[len(rebal) // 2]                            # sub-period split point
    vol_scale = crash_signal not in (None, "none")
    scales, vol_target = ((_crash_scales(uni, rebal, crash_signal, vol_lookback, vol_cap))
                          if vol_scale else ({d: 1.0 for d in rebal}, None))

    # per label: list of trade records {r, win, hold, ret, sector, half}
    trades = {lbl: [] for lbl in S.ALL_LABELS if lbl != S.NO_SETUP}
    label_counts = defaultdict(int)

    risk_off_dates = 0
    for di, as_of in enumerate(rebal):
        # macro regime: sit out long setups when market breadth is risk-off (Phase 1's gate)
        if regime_breadth and _breadth(uni, as_of) < regime_breadth:
            risk_off_dates += 1
            if progress and di % 40 == 0:
                print(f"  {as_of} ({di + 1}/{len(rebal)}) risk-off — skipped")
            continue
        top_syms = (_composite_top(uni, as_of, min_adv, composite_top_pct, comp)
                    if composite_top_pct else None)
        for sym, v in uni.items():
            if top_syms is not None and sym not in top_syms:
                continue
            i = v["idx"].get(as_of)
            if i is None or i < bt.MIN_HISTORY:
                continue
            rows = v["rows"][max(0, i - bt.WINDOW + 1): i + 1]
            if min_adv:
                rf_adv = F.adv_rupees(rows)
                if (rf_adv or 0) < min_adv:
                    continue
            label = S.classify(rows)
            label_counts[label] += 1
            if label == S.NO_SETUP:
                continue

            geo = S.SETUP_GEOMETRY[label]
            atr = F._atr(rows)
            entry = v["closes"][i]
            if not atr or not entry:
                continue
            stop_dist = geo["stop_atr"] * atr
            if stop_dist <= 0:
                continue
            stop_price = entry - stop_dist
            target_price = entry + geo["target_atr"] * atr
            # forward bars live on the full series, not the trailing window
            if i + 1 >= len(v["rows"]):
                continue
            outcome, hold, exit_price = first_touch(
                v["rows"], i, entry, stop_price, target_price, geo["horizon"])

            cost_r = (cost_pct / 100 * entry) / stop_dist
            r_mult = (exit_price - entry) / stop_dist - cost_r
            ret = (exit_price - entry) / entry * 100 - cost_pct
            trades[label].append({
                "r": r_mult, "win": r_mult > 0, "hold": hold, "ret": ret,
                "sector": v.get("sector", "Other"),
                "half": 0 if as_of < mid_date else 1,
                "scale": scales.get(as_of, 1.0),      # Barroso–Santa-Clara exposure scale
            })

        if progress and di % 40 == 0:
            print(f"  {as_of} ({di + 1}/{len(rebal)})")

    return {"trades": trades, "label_counts": dict(label_counts), "rebal": rebal,
            "mid_date": mid_date, "cost_pct": cost_pct, "min_adv": min_adv, "min_n": min_n,
            "regime_breadth": regime_breadth, "risk_off_dates": risk_off_dates,
            "composite_top_pct": composite_top_pct, "vol_scale": vol_scale,
            "crash_signal": crash_signal, "vol_lookback": vol_lookback, "vol_cap": vol_cap,
            "vol_info": vol_target}


def _stats(rs: list[float]):
    n = len(rs)
    if n == 0:
        return 0, 0.0, 0.0, 0.0
    m = statistics.mean(rs)
    sd = statistics.stdev(rs) if n > 1 else 0.0
    t = (m / (sd / n ** 0.5)) if sd else 0.0
    return n, m, statistics.median(rs), t


def report(res):
    trades, counts = res["trades"], res["label_counts"]
    total = sum(counts.values())
    print("\n==========  PHASE 2 SETUP VALIDATION  ==========")
    print(f"rebalance dates: {len(res['rebal'])}   cost/round-trip: {res['cost_pct']}%   "
          f"ADV floor: ₹{res['min_adv']:,.0f}   gate min-n: {res['min_n']}")
    rg = res.get("regime_breadth", 0)
    ct = res.get("composite_top_pct", 0)
    print(f"regime breadth gate: {rg:g}%   risk-off dates skipped: {res.get('risk_off_dates', 0)}"
          f"   composite top-gate: {('top ' + format(ct, 'g') + '%') if ct else 'off'}")
    vs = res.get("vol_scale")
    if vs:
        print(f"crash signal: {res['crash_signal'].upper()}  ({res.get('vol_info')})  "
              f"lookback {res['vol_lookback']}d  cap {res['vol_cap']:g}x  "
              f"→ expR/Sharpe below are exposure-scaled")
    print(f"sub-period split at {res['mid_date']}   point-in-time membership: NO (optimistic)\n")

    print("label distribution (share of all scored stock-dates):")
    for lbl in S.ALL_LABELS:
        c = counts.get(lbl, 0)
        print(f"  {lbl:<26} {c:>7,}  {c / total * 100:>5.1f}%" if total else f"  {lbl}")
    print()

    def eff(t):
        return t["r"] * t.get("scale", 1.0) if vs else t["r"]

    def sharpe(rs):
        return (statistics.mean(rs) / statistics.stdev(rs)) if len(rs) > 1 and statistics.stdev(rs) else 0.0

    print(f"{'setup':<26}{'n':>7}{'win%':>7}{'expR':>8}{'medR':>8}{'Shrp':>7}{'t':>7}"
          f"{'hold':>6}")
    print("-" * 78)
    exp_by = {}
    for lbl in (*S.TRADABLE, S.EXTENDED):
        rs = [eff(t) for t in trades[lbl]]
        n, m, med, t = _stats(rs)
        exp_by[lbl] = m if n else None
        win = sum(x["win"] for x in trades[lbl]) / n * 100 if n else 0
        hold = statistics.mean(x["hold"] for x in trades[lbl]) if n else 0
        print(f"{lbl:<26}{n:>7,}{win:>6.0f}%{m:>+8.2f}{med:>+8.2f}{sharpe(rs):>+7.3f}{t:>+7.1f}"
              f"{hold:>6.1f}")
    print("-" * 78)

    # sub-period stability + top sectors, per tradable setup
    for lbl in S.TRADABLE:
        if not trades[lbl]:
            continue
        h0 = [eff(t) for t in trades[lbl] if t["half"] == 0]
        h1 = [eff(t) for t in trades[lbl] if t["half"] == 1]
        by_sec = defaultdict(list)
        for t in trades[lbl]:
            by_sec[t["sector"]].append(eff(t))
        top = sorted(by_sec.items(), key=lambda kv: -len(kv[1]))[:4]
        print(f"\n{lbl}:")
        print(f"    sub-period expR   1st half {_stats(h0)[1]:+.2f} (n={len(h0)})   "
              f"2nd half {_stats(h1)[1]:+.2f} (n={len(h1)})")
        secs = "   ".join(f"{s.split()[0][:10]} {statistics.mean(r):+.2f}(n={len(r)})"
                          for s, r in top)
        print(f"    top sectors expR  {secs}")

    # gate
    print("\n" + "=" * 78)
    best_tradable = max((exp_by[l] for l in S.TRADABLE if exp_by[l] is not None), default=None)
    any_pass = False
    for lbl in S.TRADABLE:
        n = len(trades[lbl])
        m = exp_by[lbl]
        h0 = _stats([eff(t) for t in trades[lbl] if t["half"] == 0])[1]
        h1 = _stats([eff(t) for t in trades[lbl] if t["half"] == 1])[1]
        robust = h0 > 0 and h1 > 0
        ok = n >= res["min_n"] and m is not None and m > 0 and robust
        any_pass = any_pass or ok
        if m is None:
            print(f"GATE {lbl:<26} n={n:<6} (no trades)")
            continue
        if n < res["min_n"]:
            verdict = "thin sample"
        elif m <= 0:
            verdict = "NO EDGE"
        elif not robust:
            verdict = f"FRAGILE (halves {h0:+.2f}/{h1:+.2f})"
        else:
            verdict = "PASS (robust both halves)"
        print(f"GATE {lbl:<26} n={n:<6} expR={m:+.2f} -> {verdict}")
    ext = exp_by.get(S.EXTENDED)
    if ext is not None and best_tradable is not None:
        conf = "confirmed inferior" if ext < best_tradable else "NOT inferior — investigate"
        print(f"GATE {S.EXTENDED:<26} expR={ext:+.2f} vs best tradable {best_tradable:+.2f} "
              f"-> {conf}")
    print("=" * 78)
    print("  -> PHASE 2 " + ("PASS — at least one setup carries its own edge; ship the "
          "passers, drop the rest." if any_pass else "NOT YET — no setup cleared its bar."))
    print("Note: trades overlap across nearby rebalances → t inflated; read t>=2 as "
          "necessary, not sufficient. Survivorship: today's members (optimistic).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--cost", type=float, default=0.30, help="round-trip cost %%")
    ap.add_argument("--min-adv", type=float, default=0.0, help="liquidity floor, ₹")
    ap.add_argument("--min-n", type=int, default=60, help="min trades for a setup gate")
    ap.add_argument("--regime-breadth", type=float, default=0.0,
                    help="skip long setups when %% of universe above 200-DMA is under this")
    ap.add_argument("--composite-top", type=float, default=0.0,
                    help="only take setups on names in the top N%% of the Phase-1 composite")
    ap.add_argument("--crash", choices=["none", "sma", "ewma", "drawdown"], default="none",
                    help="crash-protection signal: sma/ewma vol scaling or market-drawdown gate")
    ap.add_argument("--vol-scale", action="store_true", help="alias for --crash sma")
    ap.add_argument("--vol-lookback", type=int, default=63, help="trailing days for realized vol")
    ap.add_argument("--vol-cap", type=float, default=2.5, help="max exposure multiplier")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    crash = "sma" if (args.vol_scale and args.crash == "none") else args.crash
    res = run(every=args.every, start=args.start, end=args.end, cost_pct=args.cost,
              min_adv=args.min_adv, min_n=args.min_n, regime_breadth=args.regime_breadth,
              composite_top_pct=args.composite_top, crash_signal=crash,
              vol_lookback=args.vol_lookback, vol_cap=args.vol_cap, progress=not args.quiet)
    report(res)


if __name__ == "__main__":
    main()
