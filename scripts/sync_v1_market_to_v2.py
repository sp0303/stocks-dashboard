#!/usr/bin/env python3
"""Idempotent v1 (Mongo) -> v2 (Postgres) market-data sync.

Loads orb_candles_1d (paise) into market.eod_prices (rupees, source='orb_rollup'),
derives market.trading_calendar from the dates that carry daily rows, and appends
new market.benchmark_values from benchmark_prices. Prints counts only.

Env: MONGODB_URL (+ optional MONGODB_DB, default 'stocks'; v1, read-only use) and PG_DSN (falls back to DATABASE_URL).

    python3 scripts/sync_v1_market_to_v2.py --dry-run
    python3 scripts/sync_v1_market_to_v2.py
    python3 scripts/sync_v1_market_to_v2.py --since 2026-09-15 --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "apps" / "workers", ROOT / "libs" / "pi_core"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from pi_workers.v1_sync_db import run_sync


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="run everything, then roll back; counts only",
    )
    ap.add_argument(
        "--since",
        type=date.fromisoformat,
        help="YYYY-MM-DD; default: last orb_rollup date - 10d",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="whole v1 universe (adds missing NSE securities)",
    )
    ap.add_argument(
        "--replace-other-sources",
        action="store_true",
        help="overwrite existing eod_prices rows whose source is not orb_rollup (default: keep them)",
    )
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    pg_dsn = os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
    mongo_url = os.environ.get("MONGODB_URL")
    if not pg_dsn or not mongo_url:
        print(
            "error: set PG_DSN (or DATABASE_URL) and MONGODB_URL in the environment",
            file=sys.stderr,
        )
        return 2
    report = asyncio.run(
        run_sync(
            pg_dsn,
            mongo_url,
            since=args.since,
            all_universe=args.all,
            dry_run=args.dry_run,
            replace_other_sources=args.replace_other_sources,
            mongo_db=os.environ.get("MONGODB_DB"),
        )
    )
    print(json.dumps(report.as_dict(), indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
