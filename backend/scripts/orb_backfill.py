#!/usr/bin/env python
"""Segment A — build the ORB data set.

Runs in stages, each resumable and safe to re-run:

    python scripts/orb_backfill.py daily              # ~2,700 calls, ~15 min
    python scripts/orb_backfill.py universe           # no calls; ranks and picks
    python scripts/orb_backfill.py minute --years 2   # ~5,000 calls, ~1 hour
    python scripts/orb_backfill.py calendar           # no calls
    python scripts/orb_backfill.py report             # no calls

Or the whole thing:

    python scripts/orb_backfill.py all --years 2

Needs MONGODB_URL and the four ANGEL_* variables in backend/.env. Angel's historical
ceiling is 5,000 calls/hour, so `minute` over 200 symbols is paced at roughly an hour
and the script prints a running estimate. Interrupt it whenever you like: sessions
already stored are skipped on the next run.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orb import calendar as orb_calendar          # noqa: E402
from app.services.orb import history, store, universe          # noqa: E402
from app.services.orb.config import DEFAULT                    # noqa: E402
from app.services.orb.session import MARKET_CLOSE              # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orb.backfill")


def _hms(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def cmd_daily(args) -> None:
    """Daily candles for the whole EQ pool. One request per symbol covers years."""
    insts = universe.equity_candidates()
    start = date.today() - timedelta(days=365 * args.daily_years)
    end = date.today()
    log.info("daily candles for %d EQ symbols, %s..%s", len(insts), start, end)
    t0, ok, empty, failed = time.time(), 0, 0, 0
    for i, inst in enumerate(insts, 1):
        n = history.backfill_daily(inst, start, end)
        if n < 0:
            failed += 1
        elif n == 0:
            empty += 1
        else:
            ok += 1
        if i % 100 == 0 or i == len(insts):
            rate = i / max(1e-9, time.time() - t0)
            log.info("  %d/%d  ok=%d empty=%d failed=%d  eta %s",
                     i, len(insts), ok, empty, failed, _hms((len(insts) - i) / rate))
    log.info("daily done in %s: ok=%d empty=%d failed=%d", _hms(time.time() - t0),
             ok, empty, failed)


def cmd_universe(args) -> None:
    """Rank the pool by liquidity and store the working set. No API calls."""
    insts = {i.symbol: i for i in universe.equity_candidates()}
    scored = []
    for sym, inst in insts.items():
        t = history.median_turnover_cr(sym)
        if t is not None:
            scored.append((t, sym))
    scored.sort(reverse=True)
    size = args.size or DEFAULT.universe_size
    chosen = scored[:size]
    doc = {
        "_id": date.today().isoformat(), "date": date.today().isoformat(),
        "size": len(chosen), "min_turnover_cr": round(chosen[-1][0], 2) if chosen else None,
        "members": [{"sym": s, "token": insts[s].token, "series": insts[s].series,
                     "tick": insts[s].tick, "turnover_cr": round(t, 2),
                     "sector_index": universe.sector_index_for(s)} for t, s in chosen],
        "pool": len(insts), "ranked": len(scored),
    }
    store.put(store.UNIVERSE, doc)
    mapped = sum(1 for m in doc["members"] if m["sector_index"])
    log.info("universe: %d of %d ranked (pool %d); turnover floor Rs %s cr",
             len(chosen), len(scored), len(insts), doc["min_turnover_cr"])
    log.info("  sector index mapped for %d/%d — gate D5 is skipped for the rest",
             mapped, len(chosen))
    for t, s in chosen[:10]:
        log.info("  %-14s %8.1f cr", s, t)


def _working_set() -> list:
    doc = store.find(store.UNIVERSE, {}, sort=[("date", -1)], limit=1)
    if not doc:
        raise SystemExit("no universe stored — run `universe` first")
    insts = {i.symbol: i for i in universe.equity_candidates()}
    return [insts[m["sym"]] for m in doc[0]["members"] if m["sym"] in insts]


def cmd_minute(args) -> None:
    """The long one. Chunked, resumable, and skips sessions already on disk."""
    insts = _working_set()
    end = date.today()
    start = end - timedelta(days=int(365.25 * args.years))
    est_calls = len(insts) * (args.years * 365 // history.CHUNK_DAYS["1m"] + 1)
    log.info("1-minute backfill: %d symbols, %s..%s (~%d calls, ~%s at the 5,000/hr cap)",
             len(insts), start, end, est_calls, _hms(est_calls / 5000 * 3600))
    t0 = time.time()
    for i, inst in enumerate(insts, 1):
        m = history.backfill_minute(inst, start, end)
        rate = i / max(1e-9, time.time() - t0)
        log.info("[%d/%d] %-14s days=%-4d chunks=%-3d fail=%-2d  eta %s",
                 i, len(insts), inst.symbol, m["days"], m["chunks"], m["failures"],
                 _hms((len(insts) - i) / rate))
    log.info("minute backfill done in %s", _hms(time.time() - t0))


def cmd_calendar(args) -> None:
    end = date.today()
    start = end - timedelta(days=int(365.25 * args.years))
    res = orb_calendar.rebuild(start, end)
    log.info("calendar: %(trading_days)d trading days, %(half_days)d half days", res)


def cmd_report(args) -> None:
    """Segment A's exit test, as a number rather than a feeling."""
    end = date.today()
    start = end - timedelta(days=int(365.25 * args.years))
    days = orb_calendar.trading_days(start, end)
    if not days:
        raise SystemExit("no trading days derived — run `calendar` first")
    universe_size = len(_working_set())
    complete, partial, thin = 0, 0, []
    for day in days:
        docs = store.session_coverage(day)
        good = sum(1 for d in docs
                   if d.get("n", 0) >= 370 and (d.get("real_bars") or 0) > 0)
        ratio = good / universe_size if universe_size else 0
        if ratio >= 0.95:
            complete += 1
        else:
            partial += 1
            thin.append((day, round(ratio, 3)))
    log.info("=" * 62)
    log.info("SEGMENT A REPORT   %s .. %s", start, end)
    log.info("  trading days derived : %d", len(days))
    log.info("  working set          : %d symbols", universe_size)
    log.info("  days >=95%% complete  : %d", complete)
    log.info("  days below bar       : %d", partial)
    for day, r in thin[:15]:
        log.info("      %s  %.0f%%", day, r * 100)
    passed = partial == 0 and len(days) > 0
    log.info("  EXIT TEST            : %s", "PASS" if passed else "NOT YET")
    log.info("=" * 62)
    if not passed:
        log.info("Re-run `minute` to fill the gaps; it only fetches what is missing.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=["daily", "universe", "minute", "calendar",
                                     "report", "all"])
    p.add_argument("--years", type=float, default=2, help="minute-history depth")
    p.add_argument("--daily-years", type=float, default=5, help="daily-history depth")
    p.add_argument("--size", type=int, default=0, help="working-set size (default 200)")
    args = p.parse_args()

    try:
        store.ensure_indexes()
    except store.StoreUnavailable as exc:
        raise SystemExit(f"{exc}\nSet MONGODB_URL in backend/.env and try again.")
    stages = {"daily": cmd_daily, "universe": cmd_universe, "minute": cmd_minute,
              "calendar": cmd_calendar, "report": cmd_report}
    if args.stage == "all":
        for name in ("daily", "universe", "minute", "calendar", "report"):
            log.info("── stage: %s ──────────────────────────────", name)
            stages[name](args)
    else:
        stages[args.stage](args)


if __name__ == "__main__":
    main()
