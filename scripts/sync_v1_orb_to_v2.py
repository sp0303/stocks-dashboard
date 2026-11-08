#!/usr/bin/env python3
"""Sync v1 Mongo orb_* collections into v2 Postgres orb.* (one idempotent pass).

READ-ONLY on v1 Mongo. Never logs into Angel, never calls SmartAPI (AGENTS §10), so it
is safe to run during market hours alongside v1's live ORB feed.

Env:
    MONGODB_URL   v1 Mongo (required)
    MONGODB_DB    v1 database name (default "stocks", as in v1 config)
    PG_DSN        v2 Postgres DSN with write on orb.* (falls back to DATABASE_URL)

Usage:
    python3 scripts/sync_v1_orb_to_v2.py --dry-run     # counts only, writes nothing
    python3 scripts/sync_v1_orb_to_v2.py               # incremental upsert
    python3 scripts/sync_v1_orb_to_v2.py --full        # ignore the date watermark

Output is a single JSON line of counts per table; document contents are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "apps" / "workers"))

from pi_workers.orb_feed import V1MongoSource, run_sync


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true", help="read and compare; write nothing")
    p.add_argument("--full", action="store_true", help="ignore the incremental watermark")
    p.add_argument("--lookback-days", type=int, default=3,
                   help="re-read this many days before the newest synced date")
    args = p.parse_args(argv)

    url = os.environ.get("MONGODB_URL", "").strip()
    if not url:
        print("MONGODB_URL is not set", file=sys.stderr)
        return 2
    dsn = os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL")
    if not dsn and not args.dry_run:
        print("PG_DSN (or DATABASE_URL) is not set", file=sys.stderr)
        return 2

    source = V1MongoSource(url, os.environ.get("MONGODB_DB", "stocks"))
    try:
        result = asyncio.run(run_sync(source, dsn, full=args.full, dry_run=args.dry_run,
                                      lookback_days=args.lookback_days))
    finally:
        source.close()
    print(json.dumps({"source": source.name, "dry_run": args.dry_run, "tables": result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
