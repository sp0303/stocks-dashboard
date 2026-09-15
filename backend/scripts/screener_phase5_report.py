#!/usr/bin/env python
"""Phase 5 — realized-performance report (and optional snapshot backfill).

Live, the daily scan calls `screener_forward.save_snapshot(db, snapshot_from_compute(...))`
and, days later, `record_outcomes`. To get a realized read *today* without waiting, this
script backfills point-in-time snapshots for the last N rebalance dates that have already
matured (>= max horizon of forward bars), records their real outcomes from the store, and
prints the realized rank-IC and per-setup expectancy — the live mirror of the Phase 1/2 gates.

  python scripts/screener_phase5_report.py --backfill 40            # in-memory, prints report
  python scripts/screener_phase5_report.py --backfill 40 --save     # also persist snapshots

--save is the only thing that writes to Mongo (collection `screener_snapshots`, upsert by date).
Without it, nothing in the database is touched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import screener_backtest as bt                                    # noqa: E402
from app.services import screener_factors as F                    # noqa: E402
from app.services import screener_forward as FW                   # noqa: E402
from app.services import screener_plan, screener_setups as S      # noqa: E402


def _pit_snapshot(uni, comp, as_of):
    raw_by, rows_by = {}, {}
    for sym, v in uni.items():
        i = v["idx"].get(as_of)
        if i is None or i < bt.MIN_HISTORY:
            continue
        rows = v["rows"][max(0, i - bt.WINDOW + 1): i + 1]
        raw_by[sym] = F.raw_factors(rows)
        rows_by[sym] = rows
    scores = comp.score_universe(raw_by)
    stocks = []
    for sym, rows in rows_by.items():
        label = S.classify(rows)
        pl = screener_plan.plan_levels(rows, label) or {}
        stocks.append({
            "ticker": sym, "setup": label, "score": round(scores.get(sym, 0.0), 4),
            "value_score": None, "quality_score": None,
            "entry": pl.get("entry") or rows[-1]["c"] / 100,
            "stop": pl.get("stop"), "t2": pl.get("t2"),
            "risk_per_share": pl.get("risk_per_share"),
        })
    return {"_id": as_of, "as_of": as_of, "created_at": "backfill", "stocks": stocks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=40, help="rebalance dates to backfill")
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--cost", type=float, default=0.30)
    ap.add_argument("--save", action="store_true", help="persist snapshots to Mongo")
    args = ap.parse_args()

    uni = bt.load_universe()
    if not uni:
        raise SystemExit("no daily data — is the Mongo store populated?")
    comp = F.Composite()
    all_dates = sorted({d for v in uni.values() for d in v["dates"]})
    # only dates with a full forward window already available (so outcomes mature)
    usable = all_dates[bt.MIN_HISTORY: len(all_dates) - max(FW.HORIZONS) - 1]
    picks = usable[::args.every][-args.backfill:]
    print(f"backfilling {len(picks)} snapshots  {picks[0]} → {picks[-1]}  (cost {args.cost}%)")

    def forward_lookup(sym, as_of):
        v = uni.get(sym)
        i = v["idx"].get(as_of) if v else None
        return v["rows"][i + 1:] if (v and i is not None) else []

    snaps = []
    db = None
    if args.save:
        from app.config import settings
        from pymongo import MongoClient
        db = MongoClient(settings.mongodb_url)[settings.mongodb_db]
    for as_of in picks:
        snap = _pit_snapshot(uni, comp, as_of)
        FW.record_outcomes(snap, forward_lookup, cost_pct=args.cost)
        snaps.append(snap)
        if db is not None:
            FW.save_snapshot(db, snap)

    for h in (5, 10, 20):
        rep = FW.realized_report(snaps, horizon=h)
        print(f"\n=== REALIZED @+{h}d  (snapshots scored: {rep['snapshots_scored']}, "
              f"pairs: {rep['pairs']}) ===")
        print(f"pooled realized rank-IC: {rep['pooled_realized_ic']}")
        if h == 10:
            for setup, st in sorted(rep["setup_expectancy_r"].items()):
                print(f"  {setup:<26} n={st['n']:<6} realized expR={st['exp_r']:+.3f}")
            print("  rolling IC (last few):",
                  ", ".join(f"{d}:{i:+.3f}" for d, i in rep["rolling_ic"][-6:]))
    print("\n(Backfill mirrors the backtest since it replays history; live snapshots will "
          "diverge as the future unfolds — that divergence is the decay signal to watch.)")
    if not args.save:
        print("Nothing written to Mongo (pass --save to persist).")


if __name__ == "__main__":
    main()
