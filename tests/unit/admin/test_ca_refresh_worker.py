"""ca_refresh_worker: idempotent stream handling, DLQ after 5 tries, paced batched refresh."""

import json

import pytest
from pi_workers import ca_refresh_worker as w


class FakeRedis:
    def __init__(self):
        self.kv, self.acked, self.dlq = {}, [], []

    async def exists(self, k):
        return k in self.kv

    async def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, k, s):
        return True

    async def set(self, k, v, ex=None):
        self.kv[k] = v

    async def xack(self, stream, group, msg_id):
        self.acked.append(msg_id)

    async def xadd(self, stream, fields):
        assert stream == w.DLQ
        self.dlq.append(fields)


def _fields(eid="e1", scope="held"):
    return {
        "event_id": eid,
        "event_type": "ca.refresh.requested",
        "data": json.dumps({"scope": scope}),
    }


@pytest.mark.asyncio
async def test_process_once_then_duplicate():
    r, calls = FakeRedis(), []

    async def handler(conn, data):
        calls.append(data)

    assert await w.process_message(r, None, "1-0", _fields(), handler) == "done"
    assert await w.process_message(r, None, "2-0", _fields(), handler) == "duplicate"
    assert len(calls) == 1 and calls[0]["event_id"] == "e1"
    assert r.acked == ["1-0", "2-0"]


@pytest.mark.asyncio
async def test_retry_then_dead_letter_after_five():
    r = FakeRedis()

    async def boom(conn, data):
        raise RuntimeError("nse down")

    outcomes = [
        await w.process_message(r, None, "1-0", _fields(), boom) for _ in range(5)
    ]
    assert outcomes == ["retry"] * 4 + ["dlq"]
    assert r.acked == ["1-0"] and r.dlq[0]["error"] == "nse down"


class FakeConn:
    def __init__(self, held=("AAA", "BBB")):
        self.held, self.copied, self.sql = list(held), [], []

    def transaction(self):
        conn = self

        class _T:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _T()

    async def execute(self, sql, *args):
        self.sql.append(sql)
        if "INSERT INTO ledger.corporate_actions" in sql:
            return f"INSERT 0 {len(self.copied[-1])}"
        return "UPDATE 1"

    async def copy_records_to_table(self, table, records, columns):
        assert table == "stg_ca" and columns[0] == "key"
        self.copied.append(records)

    async def fetch(self, sql, *args):
        return [{"symbol": s} for s in self.held]

    async def fetchval(self, sql, *args):
        return 42


def _row(sym):
    return w.normalize({"symbol": sym, "exDate": "05-Jun-2026", "subject": "Bonus 1:1"})


@pytest.mark.asyncio
async def test_handle_event_held_scope_records_job(monkeypatch):
    monkeypatch.setattr(w, "PAUSE_S", 0)
    conn = FakeConn()

    async def fetch(sym):
        return [_row(sym)]

    async def list_all():
        raise AssertionError("not used for held scope")

    res = await w.handle_event(
        conn, {"scope": "held", "event_id": "e"}, fetch, list_all
    )
    assert res == {"scope": "held", "symbols": 2, "fetched": 2, "stored": 2}
    assert any("status='OK'" in s for s in conn.sql)


@pytest.mark.asyncio
async def test_handle_event_all_falls_back_to_held_and_rejects_bad_scope():
    conn = FakeConn(held=["ZZZ"])

    async def fetch(sym):
        return []

    async def list_all():
        return []

    res = await w.handle_event(conn, {"scope": "all"}, fetch, list_all)
    assert res["symbols"] == 1 and res["stored"] == 0
    with pytest.raises(ValueError):
        await w.handle_event(conn, {"scope": "nope"}, fetch, list_all)


@pytest.mark.asyncio
async def test_refresh_persists_in_batches():
    conn = FakeConn()

    async def fetch(sym):
        return [_row(sym)]

    syms = [f"S{i}" for i in range(w.BATCH + 3)]
    res = await w.refresh(conn, syms, fetch, pause=0)
    assert res["stored"] == len(syms) and len(conn.copied) == 2
