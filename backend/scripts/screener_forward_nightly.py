#!/usr/bin/env python
"""Phase 5, automated: snapshot the screen, record outcomes, journal top-N vs the market.

  python scripts/screener_forward_nightly.py                 # dry run: print the rolling test, write nothing
  python scripts/screener_forward_nightly.py --relabel       # one-off: file old snapshots under their true data date
  python scripts/screener_forward_nightly.py --snapshot --record   # nightly (cron, after the 16:00 rollup)

--snapshot  computes today's screen and saves it under the date of the close it was built
            from (not the day it ran) — so it no longer depends on someone opening the page.
--record    fills Phase-5 outcomes for every snapshot (from 3 matured sessions on; refreshed
            nightly until 20) and upserts the top-N journal into `screener_forward_journal`.
--relabel   moves mis-dated snapshots to their true date; originals go to
            `screener_snapshots_backup` first. Idempotent.
Reads only Mongo (zero broker calls). Market data only — no client data is touched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import screener_daily                      # noqa: E402
from app.services import screener_forward as FW              # noqa: E402
from app.services import screener_journal as J               # noqa: E402

JOURNAL_COLL = "screener_forward_journal"
BACKUP_COLL = "screener_snapshots_backup"


def _rows_by_ticker(db, tickers) -> dict[str, list[dict]]:
    return {d["_id"]: d.get("rows", [])
            for d in db[screener_daily.DAILY_COLL].find({"_id": {"$in": list(tickers)}}, {"rows": 1})}


def _true_dated(db, snaps, rows_by) -> dict[str, dict]:
    """{data_date: snapshot}; several labels can hold the same close — keep the newest.
    Screens first shown after a later session closed are dropped (not actionable)."""
    ref = max(rows_by.values(), key=len, default=[])
    trading = [r["date"] for r in ref]
    best: dict[str, dict] = {}
    for s in snaps:
        d = J.infer_data_date(s["stocks"], rows_by)
        if not d:
            print(f"  ! {s['_id']}: could not infer data date — skipped")
            continue
        s["_true"] = d
        created = str(s.get("created_at") or s["_id"])[:10]
        if J.is_stale(d, created, trading):
            print(f"  - {s['_id']}: built from the {d} close but first saved {created} — stale, left out")
            s["_stale"] = True
            continue
        if d not in best or str(s.get("created_at")) > str(best[d].get("created_at")):
            best[d] = s
    return best


def relabel(db, snaps, by_date) -> None:
    # Stale screens are kept too (flagged), under their true date, unless a good one owns it.
    for s in snaps:
        if s.get("_stale") and s["_true"] not in by_date:
            by_date = {**by_date, s["_true"]: {**s, "stale": True}}
    keep_ids = {d for d in by_date}
    wrong = [s for s in snaps if s.get("_true") and s["_id"] != s["_true"]]
    for s in wrong:
        db[BACKUP_COLL].replace_one({"_id": s["_id"]},
                                    {k: v for k, v in s.items() if k not in ("_true", "_stale")}, upsert=True)
    for d, s in by_date.items():
        doc = {k: v for k, v in s.items() if k not in ("_true", "_stale")}
        if s["_id"] != d:
            doc["relabeled_from"] = s["_id"]
        doc.update({"_id": d, "as_of": d, "data_as_of": d})
        FW.save_snapshot(db, doc)
    stale = [s["_id"] for s in wrong if s["_id"] not in keep_ids]
    if stale:
        db[FW.SNAP_COLL].delete_many({"_id": {"$in": stale}})
    print(f"relabel: {len(wrong)} mis-dated backed up, {len(stale)} removed, {len(by_date)} kept by true date")


def snapshot_today(db) -> str:
    data = screener_daily.compute()
    as_of = data.get("data_as_of")
    if not as_of:
        raise SystemExit("compute() returned no data_as_of — daily store empty?")
    snap = FW.snapshot_from_compute(data, as_of)
    snap["data_as_of"] = as_of
    FW.save_snapshot(db, snap)
    print(f"snapshot saved for close of {as_of} ({len(snap['stocks'])} stocks)")
    return as_of


def run_journal(db, by_date, rows_by, *, write: bool) -> list[dict]:
    out = []
    for d, s in sorted(by_date.items()):
        if s.get("stale"):
            continue
        after = {tk: [r for r in rows if r["date"] > d] for tk, rows in rows_by.items()}
        rows = J.journal(s["stocks"], after, d)
        out += rows
        if write:
            FW.save_snapshot(db, FW.record_outcomes({**{k: v for k, v in s.items() if k not in ("_true", "_stale")},
                                                     "as_of": d},
                                                    lambda tk, _a: after.get(tk), min_bars=3))
            for r in rows:
                db[JOURNAL_COLL].replace_one({"_id": r["_id"]}, r, upsert=True)
    return out


def report(rows: list[dict]) -> None:
    p = lambda x: "  —   " if x is None else f"{x * 100:+6.2f}%"  # noqa: E731
    print(f"\n{'signal close':12} {'h':>2} {'exit':10} {'top20':>8} {'top50':>8} {'t50 setup':>9} "
          f"{'(n)':>4} {'market':>8} {'mkt win%':>8}")
    for r in sorted(rows, key=lambda r: (r["horizon"], r["signal_date"])):
        g = r["groups"]
        s = g["top50_setup"]
        print(f"{r['signal_date']:12} {r['horizon']:>2} {r['exit_date']:10} {p(g['top20']['avg_real']):>8} "
              f"{p(g['top50']['avg_real']):>8} {p(s and s['avg_real']):>9} {(s or {}).get('n', 0):>4} "
              f"{p(g['universe']['avg_real']):>8} {g['universe']['win_rate'] * 100:>7.0f}%")
    print("\nROLLUP — mean return vs the market (excess) and how often the group beat it")
    for h in J.HORIZONS:
        r = J.rollup(rows, h)
        if not r["windows"]:
            continue
        cells = "  ".join(
            f"{g}: {p(r[g]['mean_excess'])} excess, beat {r[g]['beat_rate'] * 100:.0f}%"
            if r[g]["mean_excess"] is not None else f"{g}: —" for g in ("top20", "top50", "top50_setup"))
        print(f"  h={h:<2} windows={r['windows']:<2} market {p(r['universe_mean'])} | {cells}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--relabel", action="store_true")
    a = ap.parse_args()
    db = screener_daily._mongo()
    if a.snapshot:
        snapshot_today(db)
    snaps = list(db[FW.SNAP_COLL].find())
    rows_by = _rows_by_ticker(db, {st["ticker"] for s in snaps for st in s["stocks"]})
    by_date = _true_dated(db, snaps, rows_by)
    if a.relabel:
        relabel(db, snaps, by_date)
    rows = run_journal(db, by_date, rows_by, write=a.record)
    report(rows)
    if not (a.snapshot or a.record or a.relabel):
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
