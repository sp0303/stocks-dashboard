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


def run(every=5, start=None, end=None, cost_pct=0.30, min_adv=0.0, min_n=60, progress=True):
    uni = bt.load_universe()
    if not uni:
        raise SystemExit("no daily data — is the Mongo store populated?")

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

    # per label: list of trade records {r, win, hold, ret, sector, half}
    trades = {lbl: [] for lbl in S.ALL_LABELS if lbl != S.NO_SETUP}
    label_counts = defaultdict(int)

    for di, as_of in enumerate(rebal):
        for sym, v in uni.items():
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
            })

        if progress and di % 40 == 0:
            print(f"  {as_of} ({di + 1}/{len(rebal)})")

    return {"trades": trades, "label_counts": dict(label_counts), "rebal": rebal,
            "mid_date": mid_date, "cost_pct": cost_pct, "min_adv": min_adv, "min_n": min_n}


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
    print(f"sub-period split at {res['mid_date']}   point-in-time membership: NO (optimistic)\n")

    print("label distribution (share of all scored stock-dates):")
    for lbl in S.ALL_LABELS:
        c = counts.get(lbl, 0)
        print(f"  {lbl:<26} {c:>7,}  {c / total * 100:>5.1f}%" if total else f"  {lbl}")
    print()

    print(f"{'setup':<26}{'n':>7}{'win%':>7}{'expR':>8}{'medR':>8}{'t':>7}"
          f"{'hold':>6}{'ret%':>8}")
    print("-" * 78)
    exp_by = {}
    for lbl in (*S.TRADABLE, S.EXTENDED):
        rs = [t["r"] for t in trades[lbl]]
        n, m, med, t = _stats(rs)
        exp_by[lbl] = m if n else None
        win = sum(x["win"] for x in trades[lbl]) / n * 100 if n else 0
        hold = statistics.mean(x["hold"] for x in trades[lbl]) if n else 0
        ret = statistics.mean(x["ret"] for x in trades[lbl]) if n else 0
        print(f"{lbl:<26}{n:>7,}{win:>6.0f}%{m:>+8.2f}{med:>+8.2f}{t:>+7.1f}"
              f"{hold:>6.1f}{ret:>+8.2f}")
    print("-" * 78)

    # sub-period stability + top sectors, per tradable setup
    for lbl in S.TRADABLE:
        if not trades[lbl]:
            continue
        h0 = [t["r"] for t in trades[lbl] if t["half"] == 0]
        h1 = [t["r"] for t in trades[lbl] if t["half"] == 1]
        by_sec = defaultdict(list)
        for t in trades[lbl]:
            by_sec[t["sector"]].append(t["r"])
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
        ok = n >= res["min_n"] and m is not None and m > 0
        any_pass = any_pass or ok
        verdict = "PASS" if ok else ("thin sample" if n < res["min_n"] else "NO EDGE")
        print(f"GATE {lbl:<26} n={n:<6} expR={m:+.2f} -> {verdict}"
              if m is not None else f"GATE {lbl:<26} n={n:<6} (no trades)")
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
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    res = run(every=args.every, start=args.start, end=args.end, cost_pct=args.cost,
              min_adv=args.min_adv, min_n=args.min_n, progress=not args.quiet)
    report(res)


if __name__ == "__main__":
    main()
