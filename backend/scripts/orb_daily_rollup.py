#!/usr/bin/env python
"""Roll the ORB live 1-minute feed up into daily candles — no broker calls.

The screener reads `orb_candles_1d`, but the only writer of that store was the Angel
historical backfill (`orb_backfill.py daily`, ~2,700 REST calls). Meanwhile the live ORB
websocket already records a full-universe minute series in `orb_candles_1m` every trading
day. This script aggregates those minute bars into one daily OHLCV row per symbol and
upserts it via `store.save_daily`, so the screener stays current with zero Angel usage and
zero interference with the live feed's Angel session.

Usage:
    python scripts/orb_daily_rollup.py                 # roll up every complete day in
                                                       # 1m that is newer than what 1d has
    python scripts/orb_daily_rollup.py 2026-09-17      # roll up one specific date

Safe to re-run: save_daily merges by date, so a repeat is a no-op.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orb import store                                  # noqa: E402
from app.services.orb.session import IST, MARKET_CLOSE, minute_of_day  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orb.rollup")


def _daily_bar(doc: dict) -> dict | None:
    """Collapse one symbol's minute doc into {date,o,h,l,c,v}, using only real bars so
    densified (synthetic) fills never set a false open/close/high/low."""
    o, h, l, c, v = doc.get("o"), doc.get("h"), doc.get("l"), doc.get("c"), doc.get("v")
    if not o or not h or not l or not c:
        return None
    syn = doc.get("syn") or [False] * len(o)
    idx = [i for i in range(len(o)) if i < len(syn) and not syn[i]]
    if not idx:
        return None
    return {
        "date": doc["date"],
        "o": o[idx[0]],
        "h": max(h[i] for i in idx),
        "l": min(l[i] for i in idx),
        "c": c[idx[-1]],
        "v": sum((v[i] or 0) for i in idx) if v else 0,
    }


def _session_complete(day: str) -> bool:
    """True once the day's trading session is over — so a mid-session run never writes a
    partial daily bar. Past dates are always complete; today only after the close."""
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    if day < today:
        return True
    if day == today:
        return minute_of_day(now) >= MARKET_CLOSE
    return False


def _dates_to_roll(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    latest_1d = max(store.latest_daily_dates().values(), default="")
    dates_1m = get_1m_dates()
    return [d for d in dates_1m if d > latest_1d and _session_complete(d)]


def get_1m_dates() -> list[str]:
    return sorted(store.get_db()[store.CANDLES_1M].distinct("date"))


def roll_up(day: str) -> int:
    """Aggregate every known-universe symbol's minute doc for `day` into 1d. Restricted to
    symbols already in the daily store, so test/junk instruments never leak into the screen."""
    known = set(store.daily_symbols())
    col_1m = store.get_db()[store.CANDLES_1M]
    n = 0
    for doc in col_1m.find({"date": day}, {"sym": 1, "date": 1, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "syn": 1}):
        sym = doc.get("sym")
        if sym not in known:
            continue
        bar = _daily_bar(doc)
        if bar:
            store.save_daily(sym, [bar])
            n += 1
    log.info("rolled up %s: %d symbols", day, n)
    return n


def main() -> None:
    explicit = sys.argv[1] if len(sys.argv) > 1 else None
    days = _dates_to_roll(explicit)
    if not days:
        log.info("nothing to roll up — 1d is already current")
        return
    total = 0
    for day in days:
        total += roll_up(day)
    log.info("done: %d symbol-days written across %s", total, ", ".join(days))


if __name__ == "__main__":
    main()
