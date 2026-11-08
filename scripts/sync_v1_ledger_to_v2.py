#!/usr/bin/env python3
"""Idempotent v1 (Mongo) -> v2 (Postgres) ledger resync (managers, clients, uploads, trades,
corporate actions, dividends, theses, watchlists, board; then trade notes/tags).

Mongo is read only. Dry run is the DEFAULT; pass --apply to write. Prints counts and v2 ids only.

Env: MONGODB_URL (+ MONGODB_DB, default 'stocks'); LEDGER_SYNC_DSN, else PG_DSN, else DATABASE_URL
(a role with write on core, ledger, research and ops -- see docs/v2/RUNBOOK-ledger-resync.md).
Recompute (--recompute) runs `python -m pi_workers.portfolio_worker --recompute-all` with the
inherited DATABASE_URL (pi_worker: portfolio.* is written only by the portfolio worker, §3.5).

    python3 scripts/sync_v1_ledger_to_v2.py                  # dry run
    python3 scripts/sync_v1_ledger_to_v2.py --apply --recompute
    python3 scripts/sync_v1_ledger_to_v2.py --apply --flag-orphans

Exit: 0 ok · 1 failed/aborted · 2 locked by another run (skipped).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "apps" / "workers", ROOT / "libs" / "pi_core", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from pi_workers.v1_sync_ledger import (
    MAX_ORPHAN_FRACTION,
    SyncAborted,
    render,
    run_sync,
)

RECOMPUTE_CMD = [sys.executable, "-m", "pi_workers.portfolio_worker", "--recompute-all"]


def _args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write (default is a read-only dry run)")
    ap.add_argument("--dry-run", action="store_true", help="explicit dry run (the default)")
    ap.add_argument("--flag-orphans", action="store_true",
                    help="soft-flag v2 rows gone from v1: trade tombstone, client INACTIVE, manager inactive")
    ap.add_argument("--max-orphan-fraction", type=float, default=MAX_ORPHAN_FRACTION)
    ap.add_argument("--recompute", action="store_true",
                    help="after a write, run the portfolio recompute (else print the command)")
    ap.add_argument("--skip-journal", action="store_true", help="skip the trade notes/tags reconcile")
    ap.add_argument("--mongo-db", default=os.getenv("MONGODB_DB", "stocks"))
    a = ap.parse_args()
    if a.apply and a.dry_run:
        ap.error("--apply and --dry-run are exclusive")
    return a


def _journal(pg: str, mg: str, mongo_db: str, apply: bool) -> int:
    from reconcile_trade_notes_tags import run as reconcile_journal

    return asyncio.run(reconcile_journal(pg, mg, mongo_db, apply))


def _recompute(result, wanted: bool) -> int:
    if result.dry_run or not (result.plan.changed_clients or result.plan.recompute_all):
        print("recompute: not needed (no ledger change)")
        return 0
    cmd = "python -m pi_workers.portfolio_worker --recompute-all"
    if not wanted:
        print(f"recompute needed: run `{cmd}` with the pi_worker DATABASE_URL")
        return 0
    print(f"recompute: {cmd}")
    paths = [str(ROOT / "apps" / "workers"), str(ROOT / "libs" / "pi_core"), str(ROOT / "apps" / "api")]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([*paths, os.environ.get("PYTHONPATH", "")])}
    return subprocess.run(RECOMPUTE_CMD, check=False, timeout=1800, env=env).returncode


def main() -> int:
    a = _args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pg = os.getenv("LEDGER_SYNC_DSN") or os.getenv("PG_DSN") or os.getenv("DATABASE_URL")
    mg = os.getenv("MONGODB_URL")
    if not pg or not mg:
        print("LEDGER_SYNC_DSN/PG_DSN/DATABASE_URL and MONGODB_URL must be set", file=sys.stderr)
        return 1
    try:
        result = asyncio.run(run_sync(
            pg, mg, mongo_db=a.mongo_db, dry_run=not a.apply, flag_orphans=a.flag_orphans,
            max_orphan_fraction=a.max_orphan_fraction))
    except SyncAborted as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 1
    print(render(result))
    if result.skipped_locked:
        return 2
    if not a.skip_journal:
        jrc = _journal(pg, mg, a.mongo_db, a.apply)
        if jrc:
            print("journal: some notes/tags unresolved (listed above); not fatal")
    return 1 if _recompute(result, a.recompute) else 0


if __name__ == "__main__":
    sys.exit(main())
