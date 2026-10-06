#!/usr/bin/env python
"""Indicator lab — do classic indicators help pick winners AMONG the composite's leaders?

Point-in-time every 5 sessions over the daily store (Oct 2022 → ~2 weeks ago):
  * universe = the screener's Nifty-500 list with ≥ ₹2 cr average daily value
  * leaders  = composite top 100 that day
  * for each indicator: rank-IC vs the forward return (entry next open, exit close h-1
    sessions later, h = 5 and 10), and the lift of its best 20 among the leaders over
    the leaders' average.
Gate (printed per indicator): mean IC within leaders has the same sign and |t| ≥ 2 overall
AND the same sign in BOTH halves (split 2024-10-01). Only gated indicators may be merged.

  python scripts/indicator_lab.py [--every 5] > lab.json     (read-only; Mongo + daily store)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import screener_backtest as bt                                     # noqa: E402
from app.services import screener_factors as F                     # noqa: E402
from app.services import screener_forward as FW                    # noqa: E402
from app.services import screener_indicators as I                  # noqa: E402

SPLIT = "2024-10-01"
HORIZONS = (5, 10)


def load_delivery(db, symbols):
    out = defaultdict(dict)
    for r in db["market_delivery_daily"].find({"symbol": {"$in": list(symbols)}},
                                              {"symbol": 1, "date": 1, "deliv_per": 1}):
        try:
            out[r["symbol"]][r["date"]] = float(r["deliv_per"])
        except (TypeError, ValueError):
            pass
    return out


def deliv_features(dl: dict, dates_upto: list[str]):
    v = [dl[d] for d in dates_upto[-60:] if d in dl]
    if len(v) < 40:
        return None, None
    lvl = sum(v[-20:]) / len(v[-20:])
    surge = (sum(v[-5:]) / 5) / (sum(v) / len(v)) if sum(v) else None
    return lvl, surge


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=5)
    a = ap.parse_args()
    db = bt._mongo()
    uni = bt.load_universe()
    ref = max(uni.values(), key=lambda v: len(v["dates"]))["dates"]
    dl = load_delivery(db, uni.keys())
    names = list(I.INDICATORS) + ["deliv_level", "deliv_surge"]

    ic = {h: {n: [] for n in names} for h in HORIZONS}          # (date, ic_leaders, ic_all, lift)
    for i in range(270, len(ref) - max(HORIZONS) - 1, a.every):
        D = ref[i]
        raw, rows_by = {}, {}
        for s, v in uni.items():
            j = v["idx"].get(D)
            if j is None or j < 260:
                continue
            rows = v["rows"][max(0, j - bt.WINDOW + 1): j + 1]
            f = F.raw_factors(rows)
            if (f.get("adv") or 0) < 2e7:
                continue
            raw[s], rows_by[s] = f, rows
        if len(raw) < 150:
            continue
        comp = F.Composite().score_universe(raw)
        leaders = set(sorted(comp, key=lambda s: comp[s], reverse=True)[:100])
        feats = {}
        for s, rows in rows_by.items():
            x = {n: fn(rows) for n, fn in I.INDICATORS.items()}
            x["deliv_level"], x["deliv_surge"] = deliv_features(dl.get(s, {}), ref[: i + 1])
            feats[s] = x
        for h in HORIZONS:
            fwd = {}
            for s in rows_by:
                v = uni[s]
                j = v["idx"][D]
                if j + h < len(v["rows"]) and v["rows"][j + 1]["o"]:
                    fwd[s] = v["rows"][j + h]["c"] / v["rows"][j + 1]["o"] - 1
            for n in names:
                pairs_all = [(feats[s][n], fwd[s]) for s in fwd if feats[s].get(n) is not None]
                pairs_ld = [(feats[s][n], fwd[s]) for s in fwd if s in leaders and feats[s].get(n) is not None]
                if len(pairs_ld) < 30:
                    continue
                ic_l = FW._spearman([p[0] for p in pairs_ld], [p[1] for p in pairs_ld])
                ic_a = FW._spearman([p[0] for p in pairs_all], [p[1] for p in pairs_all])
                srt = sorted(pairs_ld, key=lambda p: p[0], reverse=True)
                lift = sum(p[1] for p in srt[:20]) / 20 - sum(p[1] for p in pairs_ld) / len(pairs_ld)
                ic[h][n].append((D, ic_l, ic_a, lift))

    def agg(rows):
        if not rows:
            return None
        def mt(vals):
            vals = [v for v in vals if v is not None]
            if len(vals) < 5:
                return None, None
            m = sum(vals) / len(vals)
            sd = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5
            return m, (m / (sd / len(vals) ** 0.5) if sd else None)
        out = {}
        for tag, sel in (("all", rows), ("h1", [r for r in rows if r[0] < SPLIT]), ("h2", [r for r in rows if r[0] >= SPLIT])):
            mi, ti = mt([r[1] for r in sel])
            ma, _ = mt([r[2] for r in sel])
            ml, tl = mt([r[3] for r in sel])
            out[tag] = {"n": len(sel), "ic_leaders": mi, "t": ti, "ic_universe": ma, "lift_top20": ml, "t_lift": tl}
        a_, h1, h2 = out["all"], out["h1"], out["h2"]
        same = (a_["ic_leaders"] is not None and h1["ic_leaders"] is not None and h2["ic_leaders"] is not None
                and (a_["ic_leaders"] > 0) == (h1["ic_leaders"] > 0) == (h2["ic_leaders"] > 0))
        out["pass"] = bool(same and a_["t"] is not None and abs(a_["t"]) >= 2)
        out["direction"] = None if a_["ic_leaders"] is None else ("higher is better" if a_["ic_leaders"] > 0 else "lower is better")
        return out

    print(json.dumps({"split": SPLIT, "every": a.every, "from": ref[270], "to": ref[-max(HORIZONS) - 2],
                      "results": {h: {n: agg(v) for n, v in d.items()} for h, d in ic.items()}}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
