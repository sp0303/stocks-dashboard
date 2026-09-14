#!/usr/bin/env python
"""Phase 1 — does the NEW composite ranking beat equal-weight, net of costs?

Phase 0's `screener_backtest.py` proved the shipped `score_for()` has no edge. This
harness judges the replacement: the normalised, IC-screened composite in
`app.services.screener_factors`. It reuses Phase 0's universe loader and Spearman so the
two measure the same cross-section the same way.

Four execution-realism layers are built in, because a ranking that only works frictionless
and in every regime is not a strategy:

  * TRANSACTION COSTS + TURNOVER — the top decile's forward return is charged the
    round-trip cost on the fraction of it that turns over each rebalance. Churn can no
    longer hide alpha.
  * MACRO REGIME — breadth (% of the universe above its 200-DMA) gates the long book.
    On risk-off dates the long decile earns cash, not the market's fall. Reported both
    ways so you can see how much of the edge is just being long in a bull run.
  * LIQUIDITY FLOOR (ADV) — names below a minimum median daily traded value are dropped
    BEFORE scoring, so an illiquid paper winner never enters a decile.
  * SURVIVORSHIP — optional point-in-time membership (--membership) restricts each date to
    the names actually in the index then. Without it, the same optimistic bias Phase 0
    carried is printed as a caveat, not hidden.

    python scripts/screener_phase1_backtest.py --every 5 --cost 0.30 --min-adv 5000000
    python scripts/screener_phase1_backtest.py --method percentile --regime-breadth 40
    python scripts/screener_phase1_backtest.py --membership pit_members.json --out /root/p1
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))          # to import the Phase-0 harness

import screener_backtest as bt                                     # noqa: E402  reuse loader/spearman
from app.services import screener_factors as F                     # noqa: E402

HORIZONS = bt.HORIZONS
NEW_FACTORS = ["from_52w", "mom_3m", "mom_6m", "atr_pct", "atr_contraction",
               "trend_persistence", "fip"]


def _dma(closes: list[float], n: int) -> float | None:
    return sum(closes[-n:]) / n if len(closes) >= n else None


def _load_membership(path: str | None) -> dict | None:
    """{date: [symbols]} — the index constituents as of each date. Optional."""
    if not path:
        return None
    return json.loads(Path(path).read_text())


def run(every=5, start=None, end=None, method="zscore", cost_pct=0.30,
        min_adv=0.0, regime_breadth=0.0, membership_path=None, progress=True):
    uni = bt.load_universe()
    if not uni:
        raise SystemExit("no daily data — is the Mongo store populated?")
    members = _load_membership(membership_path)
    comp = F.Composite(method=method)

    all_dates = sorted({d for v in uni.values() for d in v["dates"]})
    if start:
        all_dates = [d for d in all_dates if d >= start]
    if end:
        all_dates = [d for d in all_dates if d <= end]
    rebal = all_dates[bt.MIN_HISTORY::every]
    rebal = ([d for d in rebal if d <= all_dates[-max(HORIZONS) - 1]]
             if len(all_dates) > max(HORIZONS) else [])

    dec_gross = {h: defaultdict(list) for h in HORIZONS}
    uni_acc = {h: [] for h in HORIZONS}
    ic_acc = {h: [] for h in HORIZONS}
    fic_acc = {f: {h: [] for h in HORIZONS} for f in NEW_FACTORS}
    edge_net = {h: [] for h in HORIZONS}          # D10 minus universe, net of costs
    edge_net_regime = {h: [] for h in HORIZONS}   # same, but long only when risk-on
    turnovers = []
    regime_flags = []
    prev_top: set[str] = set()

    for di, as_of in enumerate(rebal):
        allowed = set(members.get(as_of, [])) if members else None
        raw_by, fwd_by, closes_by = {}, {}, {}
        for sym, v in uni.items():
            if allowed is not None and sym not in allowed:
                continue
            i = v["idx"].get(as_of)
            if i is None or i < bt.MIN_HISTORY:
                continue
            rows = v["rows"][max(0, i - bt.WINDOW + 1): i + 1]
            rf = F.raw_factors(rows)
            if min_adv and (rf.get("adv") or 0) < min_adv:
                continue                                   # liquidity floor, before scoring
            fwd = {}
            for h in HORIZONS:
                j = i + h
                if j < len(v["closes"]) and v["closes"][i]:
                    fwd[h] = (v["closes"][j] - v["closes"][i]) / v["closes"][i] * 100
            if len(fwd) != len(HORIZONS):
                continue
            raw_by[sym] = rf
            fwd_by[sym] = fwd
            closes_by[sym] = [r["c"] / 100 for r in rows]

        if len(raw_by) < 50:
            continue

        # macro regime: breadth = share of the scored universe above its own 200-DMA
        above = sum(1 for c in closes_by.values()
                    if _dma(c, 200) and c[-1] > _dma(c, 200))
        breadth = above / len(closes_by) * 100
        risk_on = breadth >= regime_breadth
        regime_flags.append(risk_on)

        scores = comp.score_universe(raw_by)
        ranked = sorted(scores, key=lambda s: scores[s])          # ascending; D10 = top
        n = len(ranked)
        top = set(ranked[n * 9 // 10:])
        turnover = (len(top - prev_top) / len(top)) if (prev_top and top) else 1.0
        turnovers.append(turnover)
        rt_cost = cost_pct * turnover                              # cost charged this rebalance
        prev_top = top

        # per-factor IC (new factors), and composite IC
        for f in NEW_FACTORS:
            for h in HORIZONS:
                pairs = [(raw_by[s][f], fwd_by[s][h]) for s in ranked
                         if raw_by[s].get(f) is not None]
                if len(pairs) >= 50:
                    fic = bt._spearman([p[0] for p in pairs], [p[1] for p in pairs])
                    if fic is not None:
                        fic_acc[f][h].append(fic)

        for h in HORIZONS:
            rets = [fwd_by[s][h] for s in ranked]
            um = statistics.mean(rets)
            uni_acc[h].append(um)
            ic = bt._spearman([scores[s] for s in ranked], rets)
            if ic is not None:
                ic_acc[h].append(ic)
            for d in range(10):
                lo, hi = n * d // 10, n * (d + 1) // 10
                if hi > lo:
                    dec_gross[h][d + 1].append(statistics.mean(rets[lo:hi]))
            top_ret = statistics.mean(rets[n * 9 // 10:])
            net = top_ret - rt_cost                               # top decile net of costs
            edge_net[h].append(net - um)
            edge_net_regime[h].append((net - um) if risk_on else (0.0 - um))

        if progress and (di % 20 == 0 or di == len(rebal) - 1):
            print(f"  {as_of} ({di+1}/{len(rebal)}) n={n} breadth={breadth:.0f}% "
                  f"turnover={turnover:.0%}", file=sys.stderr)

    return {"dec": dec_gross, "uni": uni_acc, "ic": ic_acc, "fic": fic_acc,
            "edge_net": edge_net, "edge_net_regime": edge_net_regime,
            "turnovers": turnovers, "regime": regime_flags, "dates": len(ic_acc[HORIZONS[0]]),
            "method": method, "cost_pct": cost_pct, "min_adv": min_adv,
            "regime_breadth": regime_breadth, "survivorship": membership_path is not None}


def _t(vals):
    if len(vals) < 3:
        return 0.0
    mu, sd = statistics.mean(vals), statistics.stdev(vals)
    return mu / (sd / len(vals) ** 0.5) if sd else 0.0


def report(res):
    dec, uni, ic = res["dec"], res["uni"], res["ic"]
    print("\n==========  PHASE 1 COMPOSITE VALIDATION  ==========")
    print(f"rebalance dates: {res['dates']}   method: {res['method']}   "
          f"cost/round-trip: {res['cost_pct']:.2f}%   ADV floor: ₹{res['min_adv']:,.0f}")
    print(f"regime breadth gate: {res['regime_breadth']:.0f}%   "
          f"point-in-time membership: {'YES' if res['survivorship'] else 'NO (optimistic)'}")
    if res["turnovers"]:
        print(f"mean top-decile turnover per rebalance: {statistics.mean(res['turnovers']):.0%}")
    if res["regime"]:
        print(f"risk-on dates: {100*sum(res['regime'])/len(res['regime']):.0f}%\n")

    hdr = "decile | " + " | ".join(f"{('+%dd' % h):>8}" for h in HORIZONS)
    print(hdr); print("-" * len(hdr))
    for d in range(1, 11):
        cells = [f"{statistics.mean(dec[h][d]):+8.3f}" if dec[h].get(d) else "       —"
                 for h in HORIZONS]
        print(f"   D{d:<3} | " + " | ".join(cells))
    print("-" * len(hdr))
    print("  univ  | " + " | ".join(
        f"{statistics.mean(uni[h]):+8.3f}" if uni[h] else "       —" for h in HORIZONS)
        + "   <- equal-weight universe (gross)")

    print("\nComposite IC and the top decile's edge NET of costs:")
    for h in HORIZONS:
        ic_mean = statistics.mean(ic[h]) if ic[h] else 0.0
        ic_pos = 100 * sum(1 for x in ic[h] if x > 0) / len(ic[h]) if ic[h] else 0
        en, enr = res["edge_net"][h], res["edge_net_regime"][h]
        print(f"  +{h:>2}d  IC {ic_mean:+.4f} (pos {ic_pos:.0f}%)   "
              f"net edge {statistics.mean(en):+.3f}pp t={_t(en):+.2f}   "
              f"regime-filtered {statistics.mean(enr):+.3f}pp t={_t(enr):+.2f}")

    print("\nPer-factor rank IC (new factors):")
    hdr2 = f"{'factor':<18}" + "".join(f"{('+%dd' % h):>10}" for h in HORIZONS)
    print(hdr2); print("-" * len(hdr2))
    for f in NEW_FACTORS:
        cells = [f"{statistics.mean(res['fic'][f][h]):+10.4f}" if res['fic'][f][h] else "         —"
                 for h in HORIZONS]
        print(f"{f:<18}" + "".join(cells))

    # The Phase-1 gate, stated as a verdict rather than left to the eye.
    print("\n" + "=" * 52)
    h = 10 if 10 in HORIZONS else HORIZONS[0]
    ic_mean = statistics.mean(ic[h]) if ic[h] else 0.0
    net_t = _t(res["edge_net"][h])
    net_edge = statistics.mean(res["edge_net"][h]) if res["edge_net"][h] else 0.0
    passed = ic_mean > 0 and net_edge > 0 and net_t >= 2
    print(f"GATE (@+{h}d): composite IC {ic_mean:+.4f} > 0 ? {ic_mean>0} | "
          f"net edge {net_edge:+.3f}pp > 0 ? {net_edge>0} | t {net_t:+.2f} >= 2 ? {net_t>=2}")
    print(f"  -> {'PASS — proceed to Phase 2' if passed else 'NOT YET — do not build Phase 2'}")
    print("=" * 52)
    print("Note: overlapping windows inflate t; treat >=2 as necessary, not sufficient.")
    if not res["survivorship"]:
        print("Survivorship: universe is TODAY's members — pass --membership for a clean read.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--method", choices=["zscore", "winsor", "percentile"], default="zscore")
    ap.add_argument("--cost", type=float, default=0.30, help="round-trip cost %% (swing delivery)")
    ap.add_argument("--min-adv", type=float, default=0.0, help="min median daily traded value ₹")
    ap.add_argument("--regime-breadth", type=float, default=0.0,
                    help="risk-on requires this %% of the universe above its 200-DMA")
    ap.add_argument("--membership", help="point-in-time membership JSON {date:[symbols]}")
    ap.add_argument("--out")
    args = ap.parse_args()

    res = run(every=args.every, start=args.start, end=args.end, method=args.method,
              cost_pct=args.cost, min_adv=args.min_adv, regime_breadth=args.regime_breadth,
              membership_path=args.membership)
    report(res)

    if args.out:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        summary = {
            "dates": res["dates"], "method": res["method"], "cost_pct": res["cost_pct"],
            "min_adv": res["min_adv"], "regime_breadth": res["regime_breadth"],
            "deciles": {h: {d: round(statistics.mean(v), 4) for d, v in res["dec"][h].items()}
                        for h in HORIZONS},
            "ic": {h: round(statistics.mean(res["ic"][h]), 4) for h in HORIZONS if res["ic"][h]},
            "edge_net": {h: round(statistics.mean(res["edge_net"][h]), 4)
                         for h in HORIZONS if res["edge_net"][h]},
            "fic": {f: {h: round(statistics.mean(res["fic"][f][h]), 4)
                        for h in HORIZONS if res["fic"][f][h]} for f in NEW_FACTORS},
        }
        (out / "phase1_summary.json").write_text(json.dumps(summary, indent=2))
        print(f"\nwrote {out/'phase1_summary.json'}")


if __name__ == "__main__":
    main()
