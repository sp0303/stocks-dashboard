"""Reference-data side of the v1 -> v2 sync: trading calendar and benchmarks.

Split out of ``v1_sync_db`` (module size limit, AGENTS §3.14). Same contract:
Mongo read-only, COPY -> temp staging -> INSERT .. ON CONFLICT, counts only.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from pi_workers.v1_sync import (
    BENCHMARK_SOURCE,
    TransformStats,
    build_upsert_sql,
    derive_calendar,
    transform_benchmark_docs,
)

if TYPE_CHECKING:
    from pi_workers.v1_sync_db import SyncReport


async def sync_calendar(conn, mdb, since: date | None, report: SyncReport) -> None:
    pipeline: list[dict] = [
        {"$project": {"_id": 0, "rows.date": 1}},
        {"$unwind": "$rows"},
    ]
    if since is not None:
        pipeline.append(
            {"$match": {"rows.date": {"$gte": (since - timedelta(days=7)).isoformat()}}}
        )
    pipeline.append({"$group": {"_id": "$rows.date", "n": {"$sum": 1}}})
    agg = await asyncio.to_thread(
        lambda: list(mdb.orb_candles_1d.aggregate(pipeline, allowDiskUse=True))
    )
    per_date = {
        date.fromisoformat(str(a["_id"])[:10]): int(a["n"]) for a in agg if a.get("_id")
    }
    cal = derive_calendar(per_date)
    await conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS stg_cal (cal_date date, is_open boolean, note text) ON COMMIT DROP"
    )
    await conn.execute("TRUNCATE stg_cal")
    await conn.copy_records_to_table(
        "stg_cal", records=cal, columns=["cal_date", "is_open", "note"]
    )
    sql = build_upsert_sql(
        "market.trading_calendar",
        "stg_cal",
        ("cal_date", "is_open", "note"),
        ("cal_date",),
        ("is_open", "note"),
        "t.note IS NULL OR t.note LIKE 'derived:%'",
    )
    res = await conn.fetch(sql)
    report.counts.update(
        calendar_dates_seen=len(per_date),
        calendar_open=sum(1 for c in cal if c[1]),
        calendar_closed=sum(1 for c in cal if not c[1]),
        calendar_inserted=sum(1 for r in res if r["inserted"]),
        calendar_updated=sum(1 for r in res if not r["inserted"]),
        calendar_last_open=max((c[0] for c in cal if c[1]), default=None),
    )


async def sync_benchmarks(conn, mdb, report: SyncReport) -> None:
    benches = await conn.fetch(
        "SELECT b.benchmark_id, b.code, v.value_date AS last_date, v.value AS last_value "
        "FROM market.benchmarks b LEFT JOIN LATERAL (SELECT value_date, value FROM market.benchmark_values "
        "WHERE benchmark_id = b.benchmark_id ORDER BY value_date DESC LIMIT 1) v ON true"
    )
    await conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS stg_bv (LIKE market.benchmark_values) ON COMMIT DROP"
    )
    await conn.execute("TRUNCATE stg_bv")
    records, stats, per_code = [], TransformStats(), {}
    for b in benches:
        q: dict[str, Any] = {"symbol": b["code"]}
        if b["last_date"]:
            q["date"] = {"$gt": b["last_date"].isoformat()}
        docs = await asyncio.to_thread(
            lambda q=q: list(
                mdb.benchmark_prices.find(q, {"_id": 0, "date": 1, "close": 1})
            )
        )
        rows, st = transform_benchmark_docs(docs, b["last_date"], b["last_value"])
        stats.merge(st)
        per_code[b["code"]] = len(rows)
        records.extend((b["benchmark_id"], d, v, BENCHMARK_SOURCE) for d, v in rows)
    if records:
        await conn.copy_records_to_table(
            "stg_bv",
            records=records,
            columns=["benchmark_id", "value_date", "value", "source"],
        )
    sql = build_upsert_sql(
        "market.benchmark_values",
        "stg_bv",
        ("benchmark_id", "value_date", "value", "source"),
        ("benchmark_id", "value_date"),
    )
    res = await conn.fetch(sql) if records else []
    report.counts.update(
        benchmark_rows_new_per_code=per_code,
        benchmark_inserted=len(res),
        benchmark_rejects=dict(stats.rejects),
    )
