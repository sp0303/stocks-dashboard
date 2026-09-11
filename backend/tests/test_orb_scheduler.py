"""Scheduler failure modes. Each of these is a production failure that looks fine in
development, which is why they are pinned here rather than trusted to review.
"""
import mongomock
import pytest

from app.services.orb import store
from app.services.orb.scheduler import Job, Scheduler


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(store, "get_db", lambda: client["orbtest"])
    yield client


def counter_job(name, at, calls, boom=False, **kw):
    def fn(day):
        calls.append((name, day))
        if boom:
            raise RuntimeError("job exploded")
        return f"ran {name}"
    return Job(name=name, fn=fn, at=at, **kw)


def test_a_job_runs_once_per_day_however_often_the_clock_ticks():
    calls = []
    s = Scheduler([counter_job("range", 571, calls)])
    for minute in (570, 571, 572, 600, 700):
        s.tick(minute, "2026-09-09")
    assert calls == [("range", "2026-09-09")]


def test_the_same_job_runs_again_the_next_day():
    calls = []
    s = Scheduler([counter_job("range", 571, calls)])
    s.tick(571, "2026-09-09")
    s.tick(571, "2026-09-10")
    assert len(calls) == 2


def test_one_failing_job_does_not_stop_the_others():
    calls = []
    s = Scheduler([counter_job("bad", 571, calls, boom=True),
                   counter_job("good", 571, calls)])
    runs = s.tick(571, "2026-09-09")
    assert {r.name: r.ok for r in runs} == {"bad": False, "good": True}
    assert ("good", "2026-09-09") in calls


def test_a_failed_job_is_retried_on_the_next_tick():
    calls = []
    s = Scheduler([counter_job("flaky", 571, calls, boom=True)])
    s.tick(571, "2026-09-09")
    s.tick(572, "2026-09-09")
    assert len(calls) == 2, "a job that failed has not been done"


def test_restart_mid_session_catches_up_in_scheduled_order():
    calls = []
    s = Scheduler([counter_job("late", 690, calls),
                   counter_job("range", 571, calls),
                   counter_job("prep", 525, calls)])
    # Process starts at 11:00: prep and range are overdue, `late` is not.
    s.catch_up(660, "2026-09-09")
    assert [c[0] for c in calls] == ["prep", "range"]


def test_catch_up_does_not_rerun_what_already_completed():
    calls = []
    s = Scheduler([counter_job("range", 571, calls)])
    s.tick(571, "2026-09-09")
    s.catch_up(660, "2026-09-09")
    assert len(calls) == 1


def test_jobs_stand_down_when_the_market_never_opened():
    calls = []
    s = Scheduler([counter_job("range", 571, calls),
                   counter_job("always", 571, calls, market_day_only=False)])
    s.tick(571, "2026-09-09", market_open=False)
    assert [c[0] for c in calls] == ["always"]


def test_an_every_minute_job_runs_only_inside_its_window():
    calls = []
    j = Job(name="flush", fn=lambda d: calls.append(d), every=True,
            from_minute=555, to_minute=930)
    s = Scheduler([j])
    for m in (500, 555, 700, 929, 930, 1000):
        s.tick(m, "2026-09-09")
    assert len(calls) == 3          # 555, 700, 929


def test_only_one_process_holds_the_engine_lock():
    a, b = Scheduler([], owner="host:1"), Scheduler([], owner="host:2")
    assert a.acquire_lock() is True
    assert b.acquire_lock() is False, "a second worker must not also run the engine"
    assert a.acquire_lock() is True, "the holder can refresh its own lock"


def test_the_lock_is_released_when_its_ttl_expires():
    import time as _t
    a, b = Scheduler([], owner="host:1"), Scheduler([], owner="host:2")
    a.acquire_lock()
    store.get_db()[store.JOBS].update_one({"_id": "orb-engine"},
                                          {"$set": {"expires_at": _t.time() - 1}})
    assert b.acquire_lock() is True, "a crashed engine must not hold the role forever"


def test_the_ledger_records_why_a_job_failed():
    s = Scheduler([counter_job("bad", 571, [], boom=True)])
    s.tick(571, "2026-09-09")
    entry = store.get(store.JOBS, "2026-09-09:bad")
    assert entry["ok"] is False and "job exploded" in entry["detail"]
