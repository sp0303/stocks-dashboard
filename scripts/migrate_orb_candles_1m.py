#!/usr/bin/env python3
"""Explode v1 `orb_candles_1m` day-documents into market.candles_1m rows.

v1 shape (backend/app/services/orb/store.py): one doc per symbol-session,
  {_id:"SYM:YYYY-MM-DD", sym, date, exch:"NSE", src, t:[minute-of-day IST], o,h,l,c,v:[...],
   syn:[bool], n, session_end, [last_real, real_bars, repaired_at]}
Prices are INTEGER PAISE in v1 and in v2 (LLD-database: candles_1m o/h/l/c INT paise), so
values are copied unchanged; a non-integer price means the doc is not paise and it is
rejected, never rescaled by guesswork.
`syn[i]` marks a densified bar (flat at the last real close, v=0, no trade happened).
Bars after `last_real` are synthetic by construction too. Synthetic bars are written with
synthetic=true (default) or dropped with --skip-synthetic; never imported as real (R6/R16).
Bars with price <= 0, h < max(o,c), l > min(o,c), v < 0, or outside 09:15-15:30 are rejected.

Default scope: the latest 20 sessions present (--sessions N). --all loads everything
(~40 M rows, several GB): it also needs --force-size if the estimate exceeds --max-gb.
The row/size estimate is printed BEFORE any write. Default is --dry-run; --apply writes via
COPY -> temp staging -> INSERT ... ON CONFLICT (security_id, ts) DO NOTHING (idempotent;
rows already written by the v2 feed win). Prints counts only.

Env: MONGODB_URL, PG_DSN (optional MONGODB_DB, default "stocks").
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN, MARKET_CLOSE = 9 * 60 + 15, 15 * 60 + 30  # 555, 930 (v1 session.py)
BYTES_PER_ROW = (
    140  # heap tuple ~70 B + PK index ~35 B + (security_id, ts DESC) index ~35 B
)
COLUMNS = ("security_id", "ts", "o", "h", "l", "c", "v", "synthetic")
DOC_BATCH = 200  # ~75k rows per COPY


# ── pure helpers (unit-tested) ─────────────────────────────────────────────────


def minute_to_ts(day: str, minute: int) -> datetime:
    d = date.fromisoformat(day[:10])
    return datetime.combine(d, time(0, 0), tzinfo=IST) + timedelta(minutes=int(minute))


def to_paise(v: Any) -> int | None:
    """v1 stores int paise. Accept ints and integral floats; anything else is not paise."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def explode_doc(
    doc: dict, security_id: int, skip_synthetic: bool = False
) -> tuple[list[tuple], Counter]:
    """One v1 day-doc -> rows in COLUMNS order, plus per-reason counters."""
    c: Counter = Counter()
    t = doc.get("t") or []
    arrays = [doc.get(k) or [] for k in ("o", "h", "l", "c", "v")]
    if any(len(a) != len(t) for a in arrays):
        c["doc_ragged_arrays"] += 1
        return [], c
    syn = doc.get("syn") or [False] * len(t)
    if len(syn) != len(t):
        c["doc_ragged_arrays"] += 1
        return [], c
    last_real = doc.get("last_real")
    rows: dict[int, tuple] = {}
    for i, m in enumerate(t):
        c["bars_seen"] += 1
        o, h, l, cl = (to_paise(a[i]) for a in arrays[:4])
        v = arrays[4][i]
        if None in (o, h, l, cl):
            c["reject_non_paise"] += 1
            continue
        if not (MARKET_OPEN <= int(m) < MARKET_CLOSE):
            c["reject_out_of_session"] += 1
            continue
        if min(o, h, l, cl) <= 0 or h < max(o, cl) or l > min(o, cl) or h < l:
            c["reject_bad_ohlc"] += 1
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            c["reject_bad_volume"] += 1
            continue
        synthetic = bool(syn[i]) or (last_real is not None and int(m) > int(last_real))
        if synthetic and skip_synthetic:
            c["skip_synthetic"] += 1
            continue
        if int(m) in rows:
            c["dupe_minute_last_wins"] += 1
        c["synthetic" if synthetic else "real"] += 1
        rows[int(m)] = (
            security_id,
            minute_to_ts(doc["date"], m),
            o,
            h,
            l,
            cl,
            int(v),
            synthetic,
        )
    return [rows[m] for m in sorted(rows)], c


def select_sessions(dates: Iterable[str], sessions: int | None) -> list[str]:
    """Latest N distinct session dates (None = all), ascending."""
    ds = sorted({d[:10] for d in dates if d}, reverse=True)
    return sorted(ds if sessions is None else ds[:sessions])


def estimate(total_bars: int) -> tuple[int, float]:
    return total_bars, total_bars * BYTES_PER_ROW / 1024**3


def unit_check(doc: dict, daily_close: int | None) -> str:
    """Compare last real 1m close with the v1 daily close (paise) for the same day."""
    cs, syn = doc.get("c") or [], doc.get("syn") or []
    real = [cs[i] for i in range(len(cs)) if not (i < len(syn) and syn[i])]
    if not real or not daily_close:
        return "unchecked"
    r = float(real[-1]) / float(daily_close)
    if 0.8 <= r <= 1.25:
        return "ok"
    if 0.008 <= r <= 0.0125:
        return "looks_rupees"
    return "mismatch"


# ── I/O ────────────────────────────────────────────────────────────────────────


async def run(a: argparse.Namespace, pg_dsn: str, mongo_url: str) -> int:
    import asyncpg
    from pymongo import MongoClient

    db = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000)[a.mongo_db]
    col = db.orb_candles_1m
    dates = select_sessions(col.distinct("date"), None if a.all else a.sessions)
    if not dates:
        print("no sessions found in orb_candles_1m")
        return 1
    q = {"date": {"$in": dates}}
    agg = list(
        col.aggregate(
            [
                {"$match": q},
                {"$group": {"_id": None, "docs": {"$sum": 1}, "bars": {"$sum": "$n"}}},
            ]
        )
    )
    docs_n, bars_n = (agg[0]["docs"], agg[0]["bars"]) if agg else (0, 0)
    rows_est, gb_est = estimate(bars_n)
    print(
        f"== migrate_orb_candles_1m [{'APPLY' if a.apply else 'DRY-RUN (no writes)'}]"
    )
    print(f"  sessions selected  {len(dates)}  ({dates[0]} .. {dates[-1]})")
    print(f"  v1 docs            {docs_n}")
    print(f"  ESTIMATE rows      {rows_est:,}")
    print(f"  ESTIMATE size      {gb_est:.2f} GB (uncompressed heap + 2 indexes)")
    if a.apply and gb_est > a.max_gb and not a.force_size:
        print(
            f"  refused: estimate > --max-gb {a.max_gb}; check `df -h`, then pass --force-size"
        )
        return 2

    conn = await asyncpg.connect(pg_dsn, timeout=15, command_timeout=600)
    try:
        secmap = {
            r["symbol"]: r["security_id"]
            for r in await conn.fetch(
                "SELECT security_id, symbol FROM market.securities WHERE exchange = 'NSE'"
            )
        }
        before = await conn.fetchval(
            "SELECT count(*) FROM market.candles_1m WHERE ts >= $1 AND ts < $2",
            minute_to_ts(dates[0], 0),
            minute_to_ts(dates[-1], 24 * 60),
        )
        daily = _daily_closes(db, dates) if a.unit_check else {}
        if a.apply:
            await conn.execute(
                "CREATE TEMP TABLE stage_candles_1m (LIKE market.candles_1m INCLUDING DEFAULTS) ON COMMIT DELETE ROWS"
            )
        stats: Counter = Counter()
        unmapped: set[str] = set()
        batch: list[tuple] = []
        for doc in col.find(q).batch_size(DOC_BATCH):
            stats["docs_read"] += 1
            if (doc.get("exch") or "NSE") != "NSE":
                stats["doc_skip_non_nse"] += 1
                continue
            sid = secmap.get(doc.get("sym"))
            if sid is None:
                unmapped.add(doc.get("sym"))
                stats["doc_skip_unmapped_symbol"] += 1
                continue
            if a.unit_check:
                stats[
                    f"unit_{unit_check(doc, daily.get((doc.get('sym'), doc.get('date'))))}"
                ] += 1
            rows, c = explode_doc(doc, sid, a.skip_synthetic)
            stats.update(c)
            batch.extend(rows)
            if len(batch) >= DOC_BATCH * 375:
                stats["rows_inserted"] += await _flush(conn, batch, a.apply)
                batch = []
        stats["rows_inserted"] += await _flush(conn, batch, a.apply)
        after = await conn.fetchval(
            "SELECT count(*) FROM market.candles_1m WHERE ts >= $1 AND ts < $2",
            minute_to_ts(dates[0], 0),
            minute_to_ts(dates[-1], 24 * 60),
        )
    finally:
        await conn.close()
    stats["unmapped_symbols_distinct"] = len(unmapped)
    for k in sorted(stats):
        print(f"  {k:<28} {stats[k]:,}")
    print(f"  pg candles_1m in window: before={before:,} after={after:,}")
    if stats.get("unit_looks_rupees") or stats.get("unit_mismatch"):
        print(
            "  WARNING: price-unit check failed for some docs; inspect before trusting these rows"
        )
    return 0


async def _flush(conn, rows: list[tuple], apply: bool) -> int:
    if not rows:
        return 0
    if not apply:
        return len(rows)  # would-insert upper bound (conflicts unknown in dry-run)
    async with conn.transaction():
        await conn.copy_records_to_table(
            "stage_candles_1m", records=rows, columns=COLUMNS
        )
        res = await conn.execute(
            f"INSERT INTO market.candles_1m ({', '.join(COLUMNS)}) "
            f"SELECT {', '.join(COLUMNS)} FROM stage_candles_1m "
            "ON CONFLICT (security_id, ts) DO NOTHING"
        )
    return int(res.split()[-1])


def _daily_closes(db, dates: list[str]) -> dict[tuple[str, str], int]:
    """Server-side filter: only the selected dates leave Mongo (1d docs hold ~1,250 rows each)."""
    out: dict[tuple[str, str], int] = {}
    pipe = [
        {
            "$project": {
                "rows": {
                    "$filter": {
                        "input": "$rows",
                        "cond": {"$in": ["$$this.date", dates]},
                    }
                }
            }
        }
    ]
    for d in db.orb_candles_1d.aggregate(pipe):
        for r in d.get("rows") or []:
            out[(d["_id"], r["date"])] = r.get("c")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--apply", action="store_true", help="write (default is dry-run)")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument(
        "--sessions", type=int, default=20, help="latest N sessions (default 20)"
    )
    p.add_argument(
        "--all", action="store_true", help="every session (~40M rows); explicit opt-in"
    )
    p.add_argument(
        "--skip-synthetic",
        action="store_true",
        help="drop densified bars instead of flagging",
    )
    p.add_argument(
        "--max-gb", type=float, default=1.5, help="refuse --apply above this estimate"
    )
    p.add_argument(
        "--force-size", action="store_true", help="allow --apply above --max-gb"
    )
    p.add_argument("--no-unit-check", dest="unit_check", action="store_false")
    p.add_argument("--mongo-db", default=os.getenv("MONGODB_DB", "stocks"))
    a = p.parse_args()
    if a.sessions <= 0:
        sys.exit("--sessions must be > 0")
    pg, mg = os.getenv("PG_DSN"), os.getenv("MONGODB_URL")
    if not pg or not mg:
        sys.exit("PG_DSN and MONGODB_URL must be set")
    sys.exit(asyncio.run(run(a, pg, mg)))


if __name__ == "__main__":
    main()
