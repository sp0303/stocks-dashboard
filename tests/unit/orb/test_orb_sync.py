"""Sync flow and idempotency.

`FakeConn` emulates the three statements the writer issues (staging COPY, hash-guarded
upsert, watermark) so the flow runs without a database. `test_real_postgres_*` repeats
the idempotency check against a real Postgres when PI_TEST_PG_DSN points at a disposable
database that has migration 0002 applied (never production).
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date

import pytest
from pi_workers import orb_feed as f

from tests.unit.orb import fixtures as fx


class FakeSource:
    name = "fake"

    def __init__(self, docs: dict[str, list[dict]]) -> None:
        self.docs = docs
        self.calls: list[tuple[str, object]] = []

    def fetch(self, collection, since):
        self.calls.append((collection, since))
        return [dict(d) for d in self.docs.get(collection, [])]


class FakeConn:
    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict]] = {t.table: {} for t in f.TABLES}
        self._staged: list[dict] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql):
        self._staged = []

    async def copy_records_to_table(self, name, records, columns):
        self._staged = [dict(zip(columns, r)) for r in records]

    async def fetchval(self, sql):
        table = sql.split("orb.")[1].split()[0]
        dates = [r["trade_date"] for r in self.tables[table].values() if r.get("trade_date")]
        return max(dates) if dates else None

    async def fetch(self, sql, *args):
        table = sql.split("orb.")[1].split()[0]
        store = self.tables[table]
        if sql.startswith("SELECT legacy_id"):
            return [{"legacy_id": k, "source_hash": store[k]["source_hash"]}
                    for k in args[0] if k in store]
        out = []
        for row in self._staged:
            old = store.get(row["legacy_id"])
            if old is None or old["source_hash"] != row["source_hash"]:
                out.append({"inserted": old is None})
                store[row["legacy_id"]] = row
        return out


def _sync(conn, source, **kw):
    async def go():
        return {spec.table: await f.sync_table(conn, source, spec, full=kw.get("full", False),
                                               dry_run=kw.get("dry_run", False), lookback_days=3)
                for spec in f.TABLES}
    return asyncio.run(go())


def test_first_run_inserts_second_run_is_noop():
    conn, src = FakeConn(), FakeSource(fx.all_docs())
    first = _sync(conn, src)
    assert first["signals"] == {"fetched": 2, "rejected": 0, "inserted": 2, "updated": 0,
                                "unchanged": 0}
    assert first["health"]["inserted"] == 3 and first["jobs"]["inserted"] == 2
    second = _sync(conn, src)
    for counts in second.values():
        assert counts["inserted"] == 0 and counts["updated"] == 0


def test_changed_document_is_updated_once():
    docs = fx.all_docs()
    conn = FakeConn()
    _sync(conn, FakeSource(docs))
    docs["orb_health"][2]["minute"] = 601  # heartbeat moves on
    out = _sync(conn, FakeSource(docs))
    assert out["health"]["updated"] == 1 and out["health"]["unchanged"] == 2


def test_incremental_watermark_uses_lookback():
    conn, src = FakeConn(), FakeSource(fx.all_docs())
    _sync(conn, src)
    src.calls.clear()
    _sync(conn, src)
    assert ("orb_signals", date(2026, 9, 28)) in src.calls
    src.calls.clear()
    _sync(conn, src, full=True)
    assert all(since is None for _, since in src.calls)


def test_dry_run_writes_nothing_and_counts():
    conn = FakeConn()
    out = _sync(conn, FakeSource(fx.all_docs()), dry_run=True)
    assert out["signals"]["would_insert"] == 2 and out["signals"]["would_update"] == 0
    assert all(not t for t in conn.tables.values())


def test_rejected_documents_are_counted_not_written():
    docs = fx.all_docs()
    docs["orb_signals"].append({"_id": "bad", "kind": "screen"})
    conn = FakeConn()
    out = _sync(conn, FakeSource(docs))
    assert out["signals"]["rejected"] == 1 and len(conn.tables["signals"]) == 2


PG = os.environ.get("PI_TEST_PG_DSN")


@pytest.mark.skipif(not PG, reason="PI_TEST_PG_DSN not set (disposable local Postgres only)")
def test_real_postgres_upsert_is_idempotent():
    async def go():
        first = await f.run_sync(FakeSource(fx.all_docs()), PG, full=True)
        second = await f.run_sync(FakeSource(fx.all_docs()), PG, full=True)
        return first, second

    _first, second = asyncio.run(go())
    assert sum(c["inserted"] + c["updated"] for c in second.values()) == 0
    assert second["signals"]["unchanged"] == 2
