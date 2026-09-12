#!/usr/bin/env python
"""Backfill NSE index + INDIA VIX candles into the same Mongo store as equities.

The ORB strategy's context gates D5 (sector alignment), D6 (market alignment) and A5
(VIX ceiling) all need index series the equity backfill never fetched. This pulls the
14 tokens in universe.INDEX_TOKENS as daily + 1-minute candles, stored under their index
name (sym="NIFTY 50", …) so the backtest can read them with the ordinary store API.

    python scripts/orb_index_backfill.py --years 2

Indices carry no volume (v=0); only their close is used, for since-09:15 returns and the
VIX level. Reuses history.backfill_* so chunking, paise conversion and resume all match
the equity path exactly.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.orb import history                            # noqa: E402
from app.services.orb.universe import INDEX_TOKENS, Instrument  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orb.index_backfill")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=2.0)
    ap.add_argument("--only", help="comma-separated index names to limit to")
    args = ap.parse_args()

    end = date.today()
    start = end - timedelta(days=int(365 * args.years) + 40)   # +40d warmup headroom
    names = [n.strip() for n in args.only.split(",")] if args.only else list(INDEX_TOKENS)

    t0 = time.time()
    for i, name in enumerate(names, 1):
        token = INDEX_TOKENS[name]
        inst = Instrument(symbol=name, token=token, series="EQ", tick=1, exchange="NSE")
        nd = history.backfill_daily(inst, start, end)
        man = history.backfill_minute(inst, start, end)
        log.info("[%d/%d] %-18s daily=%s  minute_days=%s  failures=%s",
                 i, len(names), name, nd, man.get("days"), man.get("failures"))
    log.info("index backfill done in %.0fs", time.time() - t0)


if __name__ == "__main__":
    main()
