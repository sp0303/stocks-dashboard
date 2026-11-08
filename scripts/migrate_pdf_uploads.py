#!/usr/bin/env python3
"""Inspect v1 `pdf_uploads` and report why it cannot be migrated into ledger.uploads (dry-run only).

Finding (from v1 code history, commits b9697d7 / fea6d12 on branch news-pipeline):
`pdf_uploads` is NOT a tradebook collection. It is the *news pipeline*: a newspaper PDF
uploaded via POST /api/news/pdf?scope=manager|client, OCR'd into `news_items` and
`news_links`. Document shape:
  {id, scope: manager|client, owner_id, file_name, file_hash (sha256 hex), edition_date,
   page_count, status: PENDING|PROCESSING|DONE|FAILED, pages_with_news, items_created,
   uploaded_at, [error]}
The PDF bytes were never persisted (passed straight to a background task), so there is no
raw file to carry over losslessly (R13 cannot be satisfied for these rows in any target).

Why ledger.uploads is the wrong target: it is the trade ledger's upload log. It requires
client_id NOT NULL (manager-scoped PDFs have none), broker_format IN (ZERODHA|UPSTOX|OTHER),
rows_total/imported/duplicate/rejected NOT NULL, and status in a different vocabulary.
Loading news PDFs there would make them look like tradebooks to every ledger consumer.
LLD-database section 5 maps pdf_uploads to `research.*`, but no research table for it (or
for news_items / news_links) exists in migrations/0001. That is a schema decision for the owner.

This script therefore only reports counts (no file names, no owner ids). --apply is refused.

Env: MONGODB_URL, PG_DSN (optional MONGODB_DB, default "stocks").
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from collections.abc import Iterable

LEDGER_REQUIRED = ("client_id", "broker_format", "rows_total")
CANDIDATE_TABLES = (
    "research.pdf_uploads",
    "research.news_items",
    "research.news_links",
)


def summarise(docs: Iterable[dict]) -> Counter:
    """Counts only. `has_bytes` flags any binary payload, i.e. a raw file we could preserve."""
    c: Counter = Counter()
    for d in docs:
        c["docs"] += 1
        c[f"scope_{d.get('scope') or 'missing'}"] += 1
        c[f"status_{d.get('status') or 'missing'}"] += 1
        if d.get("file_hash"):
            c["with_file_hash"] += 1
        if any(isinstance(v, (bytes, bytearray, memoryview)) for v in d.values()):
            c["has_bytes"] += 1
        if d.get("scope") != "client":
            c["no_client_owner"] += (
                1  # cannot satisfy ledger.uploads.client_id NOT NULL
            )
    return c


async def run(pg_dsn: str | None, mongo_url: str, mongo_db: str) -> int:
    from pymongo import MongoClient

    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)[mongo_db]
    c = summarise(db.pdf_uploads.find({}))
    news_items = db.news_items.estimated_document_count()
    news_links = db.news_links.estimated_document_count()
    present: dict[str, bool] = {}
    if pg_dsn:
        import asyncpg

        conn = await asyncpg.connect(pg_dsn, timeout=15, command_timeout=30)
        try:
            for t in CANDIDATE_TABLES:
                present[t] = await conn.fetchval(
                    "SELECT to_regclass($1) IS NOT NULL", t
                )
        finally:
            await conn.close()

    print("== migrate_pdf_uploads [DRY-RUN, report only]")
    for k in sorted(c):
        print(f"  v1 pdf_uploads {k:<22} {c[k]}")
    print(f"  v1 news_items                         {news_items}")
    print(f"  v1 news_links                         {news_links}")
    for t, ok in present.items():
        print(f"  pg {t:<34} {'exists' if ok else 'MISSING'}")
    print(
        "  verdict: not migratable to ledger.uploads (news PDFs, not tradebooks; no raw bytes in v1)."
    )
    print(
        "  owner decision needed: add research.pdf_uploads/news_items/news_links, or archive and drop."
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument(
        "--apply", action="store_true", help="refused: no valid v2 target table"
    )
    p.add_argument("--mongo-db", default=os.getenv("MONGODB_DB", "stocks"))
    a = p.parse_args()
    if a.apply:
        sys.exit(
            "refused: pdf_uploads has no v2 target table; see the module docstring"
        )
    mg = os.getenv("MONGODB_URL")
    if not mg:
        sys.exit("MONGODB_URL must be set")
    sys.exit(asyncio.run(run(os.getenv("PG_DSN"), mg, a.mongo_db)))


if __name__ == "__main__":
    main()
