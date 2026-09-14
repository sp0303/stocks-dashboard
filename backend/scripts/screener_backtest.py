#!/usr/bin/env python
"""Does the swing screener's score actually predict forward returns?

The score has shipped without ever being tested. This replays it point-in-time over the
daily store and measures what happened NEXT — the same method that showed the ORB
strategy had no edge until the data picked its filters.

    python scripts/screener_backtest.py                    # weekly rebalance, 2y
    python scripts/screener_backtest.py --every 1          # every session
    python scripts/screener_backtest.py --out /root/scr_bt # write per-date CSV

Method
  * For each rebalance date, recompute the score using ONLY rows dated <= that day
    (screener_daily._metrics(as_of=...)), so nothing leaks from the future.
  * Rank that day's cross-section into deciles by score.
  * Measure each stock's forward return at +3/+5/+10/+20 SESSIONS (its own date index,
    so holidays can't shift a horizon).
  * Report mean forward return per decile, the top-minus-bottom spread, the spread over
    the equal-weight universe, and the rank information coefficient (Spearman) per date.

Reading it
  * A score with edge: forward return rises monotonically across deciles, D10 beats the
    universe mean, and mean IC is positive and stable.
  * No edge: deciles are flat/noisy and IC hovers around zero. Then every feature built
    on this ranking is decoration, and the ranking is what needs fixing first.

Caveats stated up front
  * SURVIVORSHIP: the universe is TODAY's Nifty 500. Names that fell out are absent, so
    results are biased optimistic. This measures the score's ranking skill within a
    surviving universe, not a tradeable return.
  * Price-only: the score uses w1/m1/relative-strength/RSI, all derived from closes, so
    the current-snapshot fundamentals never enter and can't leak.
  * No costs/slippage: these are raw forward returns, not a strategy P&L.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings                                      # noqa: E402
from app.services.screener_daily import _load_kpis, _metrics, score_for  # noqa: E402

DAILY_COLL = "orb_candles_1d"
HORIZONS = [3, 5, 10, 20]
FACTORS = ["w1", "m1", "rel", "rsi", "from_52w", "atr_pct"]
WINDOW = 320          # trailing rows fed to _metrics — bounds work, keeps RSI/levels exact enough
MIN_HISTORY = 60      # a symbol needs this many sessions before it can be scored


def _mongo():
    from pymongo import MongoClient
    return MongoClient(settings.mongodb_url)[settings.mongodb_db]


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation — robust to the score's arbitrary scale."""
    n = len(xs)
    if n < 8:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:                                  # average ties
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else None


def _load_daily_from_file(path):
    """Offline loader: read an exported orb_candles_1d dump instead of Mongo, so the
    backtest can run anywhere the DB port is unreachable (e.g. a sandboxed CI/cloud box).

    Accepts what `mongoexport` produces (JSONL: one {_id, rows} object per line), a JSON
    array of those objects, or a plain {symbol: rows} dict. `rows` are the stored daily
    docs: {date, o, h, l, c (paise), v}."""
    import json as _json
    from pathlib import Path as _Path
    text = _Path(path).read_text()
    docs = {}
    stripped = text.lstrip()
    if stripped.startswith("{") and "\n{" not in stripped.strip():
        obj = _json.loads(text)
        if isinstance(obj, dict) and "rows" not in obj:
            docs = obj                                    # {sym: rows}
        else:
            docs = {obj["_id"]: obj.get("rows", [])}
    elif stripped.startswith("["):
        for d in _json.loads(text):
            docs[d["_id"]] = d.get("rows", [])
    else:
        for line in text.splitlines():                    # JSONL from mongoexport
            line = line.strip()
            if line:
                d = _json.loads(line)
                docs[d["_id"]] = d.get("rows", [])
    return docs


def load_universe():
    """{sym: {'dates':[...], 'closes':[...], 'idx':{date:i}, 'sector':str}} for the
    screener's own universe."""
    import os
    kpis = _load_kpis()
    want = [tk for tk, v in kpis.items() if not v.get("error") and tk != "DUMMYHEG"]
    src = os.environ.get("ORB_DAILY_JSON")
    if src:
        raw = _load_daily_from_file(src)
        docs = [{"_id": tk, "rows": raw.get(tk, [])} for tk in want if tk in raw]
    else:
        db = _mongo()
        docs = db[DAILY_COLL].find({"_id": {"$in": want}}, {"rows": 1})
    out = {}
    for doc in docs:
        rows = [r for r in (doc.get("rows") or []) if r.get("c") is not None]
        if len(rows) < MIN_HISTORY:
            continue
        sym = doc["_id"]
        dates = [r["date"] for r in rows]
        out[sym] = {
            "rows": rows,
            "dates": dates,
            "closes": [r["c"] / 100 for r in rows],
            "idx": {d: i for i, d in enumerate(dates)},
            "sector": kpis[sym].get("industry", "Other"),
        }
    return out


def run(every: int = 5, start: str | None = None, end: str | None = None, progress=True):
    uni = load_universe()
    if not uni:
        raise SystemExit("no daily data — is the Mongo store populated?")

    # master calendar = every date any symbol traded, ascending
    all_dates = sorted({d for v in uni.values() for d in v["dates"]})
    if start:
        all_dates = [d for d in all_dates if d >= start]
    if end:
        all_dates = [d for d in all_dates if d <= end]
    # leave room for the longest forward horizon
    rebal = all_dates[MIN_HISTORY::every]
    rebal = [d for d in rebal if d <= all_dates[-max(HORIZONS) - 1]] if len(all_dates) > max(HORIZONS) else []

    per_date = []          # {date, n, ic:{h:..}, deciles:{h:{d:mean}}, uni_mean:{h:..}}
    dec_acc = {h: defaultdict(list) for h in HORIZONS}
    uni_acc = {h: [] for h in HORIZONS}
    ic_acc = {h: [] for h in HORIZONS}
    fic_acc = {f: {h: [] for h in HORIZONS} for f in FACTORS}
    edge_acc = {h: [] for h in HORIZONS}      # per-date D10 minus universe, for a t-stat

    for di, as_of in enumerate(rebal):
        scored = []        # (score, sym, {h: fwd_ret})
        w1_by_sector = defaultdict(list)
        staged = []

        for sym, v in uni.items():
            i = v["idx"].get(as_of)
            if i is None or i < MIN_HISTORY:
                continue
            m = _metrics(v["rows"][max(0, i - WINDOW + 1): i + 1], as_of)
            if not m.get("price"):
                continue
            fwd = {}
            for h in HORIZONS:
                j = i + h
                if j < len(v["closes"]) and v["closes"][i]:
                    fwd[h] = (v["closes"][j] - v["closes"][i]) / v["closes"][i] * 100
            if len(fwd) != len(HORIZONS):
                continue                                    # need every horizon to compare fairly
            staged.append((sym, v["sector"], m, fwd))
            if m.get("w1") is not None:
                w1_by_sector[v["sector"]].append(m["w1"])

        if len(staged) < 50:
            continue
        sec_avg = {s: sum(x) / len(x) for s, x in w1_by_sector.items() if x}

        factors = {k: [] for k in FACTORS}
        for sym, sec, m, fwd in staged:
            w1, m1, rsi = m.get("w1"), m.get("m1"), m.get("rsi")
            rel = (w1 - sec_avg[sec]) if (w1 is not None and sec in sec_avg) else None
            scored.append((score_for(w1, m1, rel, rsi), sym, fwd))
            # every raw building block, so we can see which (if any) carries signal
            factors["w1"].append(w1)
            factors["m1"].append(m1)
            factors["rel"].append(rel)
            factors["rsi"].append(rsi)
            factors["from_52w"].append(m.get("from_52w_high"))
            factors["atr_pct"].append((m["atr"] / m["price"] * 100)
                                      if (m.get("atr") and m.get("price")) else None)

        # per-factor IC: rank the factor against the same forward returns
        for fname, fvals in factors.items():
            for h in HORIZONS:
                pairs = [(fv, t[2][h]) for fv, t in zip(fvals, scored) if fv is not None]
                if len(pairs) >= 50:
                    fic = _spearman([p[0] for p in pairs], [p[1] for p in pairs])
                    if fic is not None:
                        fic_acc[fname][h].append(fic)

        scored.sort(key=lambda t: t[0])
        n = len(scored)
        row = {"date": as_of, "n": n}
        for h in HORIZONS:
            rets = [t[2][h] for t in scored]
            uni_mean = statistics.mean(rets)
            uni_acc[h].append(uni_mean)
            ic = _spearman([t[0] for t in scored], rets)
            if ic is not None:
                ic_acc[h].append(ic)
                row[f"ic_{h}"] = round(ic, 4)
            row[f"uni_{h}"] = round(uni_mean, 3)
            for d in range(10):                              # decile 1 = lowest score
                lo, hi = n * d // 10, n * (d + 1) // 10
                if hi > lo:
                    mean = statistics.mean(rets[lo:hi])
                    dec_acc[h][d + 1].append(mean)
                    if d in (0, 9):
                        row[f"d{d+1}_{h}"] = round(mean, 3)
                    if d == 9:
                        edge_acc[h].append(mean - uni_mean)  # top decile's edge that date
        per_date.append(row)
        if progress and (di % 20 == 0 or di == len(rebal) - 1):
            print(f"  {as_of}  ({di+1}/{len(rebal)})  n={n}", file=sys.stderr)

    return {"per_date": per_date, "dec": dec_acc, "uni": uni_acc, "ic": ic_acc,
            "fic": fic_acc, "edge": edge_acc, "dates": len(per_date)}


def report(res):
    dec, uni, ic = res["dec"], res["uni"], res["ic"]
    print("\n===============  SCREENER SCORE VALIDATION  ===============")
    print(f"rebalance dates: {res['dates']}   (decile 1 = lowest score, 10 = highest)\n")

    hdr = "decile | " + " | ".join(f"{('+%dd' % h):>8}" for h in HORIZONS)
    print(hdr)
    print("-" * len(hdr))
    for d in range(1, 11):
        cells = []
        for h in HORIZONS:
            vals = dec[h].get(d, [])
            cells.append(f"{statistics.mean(vals):+8.3f}" if vals else "       —")
        print(f"   D{d:<3} | " + " | ".join(cells))
    print("-" * len(hdr))
    cells = [f"{statistics.mean(uni[h]):+8.3f}" if uni[h] else "       —" for h in HORIZONS]
    print("  univ  | " + " | ".join(cells) + "   <- equal-weight universe mean")

    print("\nKey numbers (mean % forward return):")
    for h in HORIZONS:
        d10 = statistics.mean(dec[h][10]) if dec[h].get(10) else 0.0
        d1 = statistics.mean(dec[h][1]) if dec[h].get(1) else 0.0
        um = statistics.mean(uni[h]) if uni[h] else 0.0
        ics = ic[h]
        ic_mean = statistics.mean(ics) if ics else 0.0
        ic_pos = 100 * sum(1 for x in ics if x > 0) / len(ics) if ics else 0
        print(f"  +{h:>2}d  D10 {d10:+.3f}  D1 {d1:+.3f}  spread {d10-d1:+.3f}"
              f"   D10-vs-universe {d10-um:+.3f}"
              f"   IC {ic_mean:+.4f} (positive on {ic_pos:.0f}% of dates)")

    # Is D10's edge over the universe real, or noise? t = mean / (sd / sqrt(n)).
    print("\nIs the top decile's edge over the universe distinguishable from noise?")
    for h in HORIZONS:
        e = res["edge"][h]
        if len(e) > 2:
            mu, sd = statistics.mean(e), statistics.stdev(e)
            t = mu / (sd / len(e) ** 0.5) if sd else 0.0
            verdict = "significant" if abs(t) >= 2 else "NOT significant"
            print(f"  +{h:>2}d  mean edge {mu:+.3f}pp   sd {sd:.3f}   t = {t:+.2f}   {verdict}")
    print("  (overlapping windows inflate t — treat these as an upper bound on confidence)")

    print("\nPer-factor rank IC (does each raw building block predict on its own?):")
    hdr2 = f"{'factor':<10}" + "".join(f"{('+%dd' % h):>10}" for h in HORIZONS)
    print(hdr2)
    print("-" * len(hdr2))
    for f in FACTORS:
        cells = []
        for h in HORIZONS:
            v = res["fic"][f][h]
            cells.append(f"{statistics.mean(v):+10.4f}" if v else "         —")
        print(f"{f:<10}" + "".join(cells))

    print("\nVerdict guide: edge => deciles trend upward, D10 beats universe, IC > 0 and")
    print("stable. Flat deciles and IC ~ 0 => the ranking has no predictive power.")
    print("Survivorship: universe is TODAY's Nifty 500 — biased optimistic.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=5, help="rebalance every N sessions")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--out", help="directory for per-date CSV + summary JSON")
    args = ap.parse_args()

    res = run(every=args.every, start=args.start, end=args.end)
    report(res)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        rows = res["per_date"]
        if rows:
            keys = sorted({k for r in rows for k in r})
            with open(out / "per_date.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
        summary = {
            "dates": res["dates"],
            "deciles": {h: {d: round(statistics.mean(v), 4) for d, v in res["dec"][h].items()}
                        for h in HORIZONS},
            "universe": {h: round(statistics.mean(res["uni"][h]), 4) for h in HORIZONS if res["uni"][h]},
            "ic": {h: round(statistics.mean(res["ic"][h]), 4) for h in HORIZONS if res["ic"][h]},
        }
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"\nwrote {out/'per_date.csv'} and {out/'summary.json'}")


if __name__ == "__main__":
    main()
