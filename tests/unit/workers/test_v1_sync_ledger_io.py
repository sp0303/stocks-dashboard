"""v1 -> v2 ledger resync I/O: dry run writes nothing, apply is COPY -> staging -> MERGE,
orphan guard, SQL builders, and the R18 per-client drift report."""

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from pi_workers.v1_sync_ledger import SyncAborted, read_v1, render, sync_with
from pi_workers.v1_sync_ledger_sql import SPECS, merge_sql, staging_ddl

from tests.unit.workers.test_v1_sync_ledger import v1_book

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class FakeTx:
    def __init__(self, conn, readonly):
        self.conn, self.readonly = conn, readonly

    async def __aenter__(self):
        self.conn.tx.append("readonly" if self.readonly else "rw")

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    """Empty v2; records every statement."""

    def __init__(self, lock=True):
        self.lock, self.tx, self.executed, self.copied = lock, [], [], []

    def transaction(self, readonly=False):
        return FakeTx(self, readonly)

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        return self.lock

    async def execute(self, sql, *args):
        self.executed.append(sql)
        return "MERGE 1" if sql.startswith("MERGE") else "INSERT 0 1"

    async def copy_records_to_table(self, table, records, columns):
        self.copied.append((table, len(records)))


def run(coro):
    return asyncio.run(coro)


def test_dry_run_writes_nothing_and_uses_read_only_tx():
    conn = FakeConn()
    res = run(sync_with(conn, v1_book(), dry_run=True))
    assert conn.tx == ["readonly"] and conn.executed == [] and conn.copied == []
    assert res.plan["trades"].inserts and res.applied == {}
    assert "DRY-RUN" in render(res)


def test_apply_copies_to_staging_then_merges_in_fk_order():
    conn = FakeConn()
    res = run(sync_with(conn, v1_book(), dry_run=False))
    tables = [t for t, _ in conn.copied]
    assert tables[:4] == ["stg_core_managers", "stg_core_clients", "stg_ledger_uploads", "stg_ledger_trades"]
    merges = [s for s in conn.executed if s.startswith("MERGE")]
    assert len(merges) == 10 and "ledger.trades" in merges[3]
    assert not any(s.lstrip().upper().startswith("DELETE") for s in conn.executed)
    assert any("ops.job_runs" in s for s in conn.executed)
    assert res.applied["trades_merged"] == 1


def test_locked_run_is_skipped():
    res = run(sync_with(FakeConn(lock=False), v1_book(), dry_run=False))
    assert res.skipped_locked and not res.plan.has_writes


def test_empty_v1_aborts_before_any_write():
    conn = FakeConn()
    with pytest.raises(SyncAborted):
        run(sync_with(conn, v1_book(managers=[], clients=[]), dry_run=False))
    assert conn.tx == [] and conn.executed == []


def test_orphan_guard_refuses_mass_tombstone(monkeypatch):
    from pi_workers import v1_sync_ledger as mod

    cid = uuid.UUID(int=20)
    trades = [{"client_id": cid, "fingerprint": f"x{i}", "legacy_id": None, "symbol": "A",
               "deleted": False, "v1_origin": True} for i in range(50)]

    async def snap(self, cutover):
        s = mod.V2Snapshot(
            managers=[{"manager_id": uuid.UUID(int=10), "legacy_id": "m1", "name": "SP", "firm": None,
                       "email": "sp@example.test", "is_active": True}],
            clients=[{"client_id": cid, "legacy_id": "c1", "manager_id": uuid.UUID(int=10), "name": "Client One",
                      "client_code": "AB1234", "broker": None, "status": "ACTIVE", "active_trades": 50}],
            trades=trades)
        return s

    monkeypatch.setattr(mod.PgLedgerRepo, "snapshot", snap)
    conn = FakeConn()
    with pytest.raises(SyncAborted):
        run(sync_with(conn, v1_book(), dry_run=False, flag_orphans=True))
    assert conn.copied == []


def test_merge_sql_insert_only_for_trades_and_guarded_updates():
    t = merge_sql(SPECS["trades"])
    assert "WHEN MATCHED" not in t and "ON t.client_id = s.client_id AND t.fingerprint = s.fingerprint" in t
    c = merge_sql(SPECS["corporate_actions"])
    assert "WHEN MATCHED AND (t.isin IS DISTINCT FROM s.isin" in c
    assert staging_ddl(SPECS["managers"]).endswith("ON COMMIT DROP")


def test_read_v1_reads_every_collection():
    class Coll(list):
        def find(self, q):
            return iter(self)

    db = {n: Coll([{"n": n}]) for n in ("managers", "clients", "trades", "uploads", "corporate_actions",
                                       "dividends", "thesis", "watchlists", "boards")}
    v1 = read_v1(db)
    assert v1.theses == [{"n": "thesis"}] and v1.boards == [{"n": "boards"}]


def test_ledger_drift_per_client_and_symbol():
    from verify_migration import ledger_drift, render_drift

    v1 = {"A": [("f1", "INFY", "buy", 10), ("f2", "INFY", "sell", 4)], "v1:zz": [("f9", "X", "buy", 1)]}
    v2 = {"A": [("f1", "INFY", "buy", 10)], "B": []}
    rows = {r.client: r for r in ledger_drift(v1, v2, {"A": "AB1234"})}
    assert rows["A"].missing_in_v2 == 1 and rows["A"].qty_drift == {"INFY": (6.0, 10.0)}
    assert rows["v1:zz"].drifted and not rows["B"].drifted
    assert "2 of 3 clients drift" in render_drift(list(rows.values()))


def test_ledger_drift_none_when_equal():
    from verify_migration import ledger_drift

    same = {"A": [("f1", "infy", "BUY", 5)]}
    assert not any(r.drifted for r in ledger_drift(same, {"A": [("f1", "INFY", "buy", 5)]}, {}))
