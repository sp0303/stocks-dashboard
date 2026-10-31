#!/usr/bin/env python
"""Replace rolled-up daily bars with NSE's official end-of-day OHLCV (the bhavcopy).

`orb_daily_rollup.py` builds each daily bar from the live 1-minute feed, so its close is
the last traded minute — not NSE's official closing price, which is the volume-weighted
average of the final 30 minutes. On a volatile close the two differ by several percent
(CARBORUNIV 26-Oct-2026: last minute 1080.00, official close 1129.20). The feed also
undercounts volume and misses symbols on days the websocket dropped them.

Every portfolio chart, day-change and screener factor reads `orb_candles_1d`, so this
script overwrites each rolled-up day with the official `sec_bhavdata_full` row — one
public file per day, no broker calls. Run it after NSE publishes (~18:00 IST).

Usage:
    python scripts/orb_official_close.py                    # recent 1m days not yet corrected
    python scripts/orb_official_close.py --since 2026-09-01 # backfill every 1m day from a date
    python scripts/orb_official_close.py 2026-10-26 ...     # specific dates (re-applies)

Safe to re-run: save_daily merges by date. A day NSE has not published yet is skipped
and retried on the next run.
"""
from __future__ import annotations

import csv
import io
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orb import store              # noqa: E402
from app.services.orb.session import IST         # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orb.official_close")

BHAV_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{}.csv"
MARKER = "orb_official_close"     # _id = date already corrected
LOOKBACK_DAYS = 10                # automatic catch-up window; older days need --since
PUBLISH_HOUR = 18                 # don't ask for today's file before NSE publishes it
# Cash-market series that are deliverable equity, best first: one row per symbol.
SERIES_RANK = {"EQ": 0, "BE": 1, "BZ": 2, "SM": 3, "ST": 4}


def _paise(x: str) -> int | None:
    try:
        return round(float(x) * 100)
    except (TypeError, ValueError):
        return None


def parse_bhavcopy(text: str, day: str) -> dict[str, dict]:
    """sec_bhavdata_full CSV → {symbol: {date, o, h, l, c, v}} in paise, one series per
    symbol (EQ preferred). Rows without a usable price are dropped, never zero-filled."""
    reader = csv.reader(io.StringIO(text))
    header = [h.strip().upper() for h in next(reader, [])]
    ix = {h: i for i, h in enumerate(header)}
    out: dict[str, tuple[int, dict]] = {}
    for raw in reader:
        r = [c.strip() for c in raw]
        if len(r) < len(header):
            continue
        rank = SERIES_RANK.get(r[ix["SERIES"]])
        if rank is None:
            continue
        o, h, lo, c = (_paise(r[ix[k]]) for k in ("OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE"))
        if not (o and h and lo and c):
            continue
        try:
            v = int(float(r[ix["TTL_TRD_QNTY"]]))
        except ValueError:
            v = 0
        sym = r[ix["SYMBOL"]]
        if sym not in out or rank < out[sym][0]:
            out[sym] = (rank, {"date": day, "o": o, "h": h, "l": lo, "c": c, "v": v, "src": "nse"})
    return {s: bar for s, (_, bar) in out.items()}


def fetch_bhavcopy(client: httpx.Client, day: str) -> str | None:
    url = BHAV_URL.format(datetime.strptime(day, "%Y-%m-%d").strftime("%d%m%Y"))
    try:
        r = client.get(url)
    except httpx.HTTPError as exc:
        log.warning("bhavcopy %s: %s", day, exc)
        return None
    if r.status_code != 200 or not r.text.lstrip().upper().startswith("SYMBOL"):
        log.info("bhavcopy %s not available yet (HTTP %s)", day, r.status_code)
        return None
    return r.text


def _published(day: str) -> bool:
    now = datetime.now(IST)
    return day < now.strftime("%Y-%m-%d") or (day == now.strftime("%Y-%m-%d") and now.hour >= PUBLISH_HOUR)


def dates_to_fix(args: list[str]) -> list[str]:
    db = store.get_db()
    days = sorted(db[store.CANDLES_1M].distinct("date"))
    if args[:1] == ["--since"]:
        return [d for d in days if d >= args[1] and _published(d)]
    if args:
        return args
    done = set(db[MARKER].distinct("_id"))
    since = (datetime.now(IST) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    return [d for d in days if d >= since and d not in done and _published(d)]


def apply(bars_by_day: dict[str, dict[str, dict]], known: set[str]) -> int:
    """Write official bars for symbols already in the daily store; one write per symbol."""
    per_sym: dict[str, list[dict]] = {}
    for bars in bars_by_day.values():
        for sym, bar in bars.items():
            if sym in known:
                per_sym.setdefault(sym, []).append(bar)
    for sym, rows in per_sym.items():
        store.save_daily(sym, rows)
    return len(per_sym)


def main() -> None:
    days = dates_to_fix(sys.argv[1:])
    if not days:
        log.info("nothing to correct")
        return
    client = httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*",
                                               "Referer": "https://www.nseindia.com/"})
    bars_by_day = {}
    for day in days:
        text = fetch_bhavcopy(client, day)
        if text:
            bars_by_day[day] = parse_bhavcopy(text, day)
        time.sleep(1)  # one public file per day; stay polite to nsearchives
    if not bars_by_day:
        return
    n = apply(bars_by_day, set(store.daily_symbols()))
    db = store.get_db()
    for day, bars in bars_by_day.items():
        db[MARKER].replace_one({"_id": day}, {"_id": day, "symbols": len(bars),
                                               "at": datetime.now(IST).isoformat()}, upsert=True)
    log.info("official close applied for %s: %d symbols updated", ", ".join(bars_by_day), n)


if __name__ == "__main__":
    main()
