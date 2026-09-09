"""Wall-clock scheduler for the live engine.

`while True: sleep(n)` is not adequate here, and every reason bites in production while
looking fine in testing:

  * **Interval drift.** Sleeping 300s repeatedly turns "09:30" into 09:30:47 and then
    09:31:31, and the opening range gets cut in the wrong place. Jobs fire on absolute
    IST minute boundaries, recomputed each pass, never accumulated.
  * **One exception kills the loop.** Everything works until 11:02 and then goes silent
    with nothing on the page to say so. Each job is wrapped individually; a failure is
    recorded and the loop continues.
  * **Restarts.** A deploy at 10:15 means 09:31's job never ran and nothing recovers it.
    On start, every job whose window has passed today but which has no completed ledger
    entry is run once, in order.
  * **Two workers.** `uvicorn --workers 2` or `--reload` runs everything twice: two
    subscriptions, duplicate bars, doubled signals. A Mongo lock with a TTL means
    exactly one process is the engine.
  * **Silent death.** A heartbeat written every minute lets /orb show seconds since the
    last one instead of yesterday's data looking like today's.

`tick()` holds the whole decision and takes the time as an argument, so the behaviour
above is testable without waiting for a clock.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from app.services.orb import store
from app.services.orb.session import IST, now_ist

log = logging.getLogger("orb.scheduler")

LOCK_ID = "orb-engine"
LOCK_TTL_S = 120
HEARTBEAT_ID = "orb-heartbeat"


@dataclass
class Job:
    name: str
    fn: Callable[[str], object]          # takes the date string
    at: int | None = None                # minute of day; None with every=True
    every: bool = False                  # run on every tick in [from_minute, to_minute)
    from_minute: int = 0
    to_minute: int = 24 * 60
    catch_up: bool = True                # re-run on restart if its time has passed
    market_day_only: bool = True

    def due_at(self, minute: int) -> bool:
        if self.every:
            return self.from_minute <= minute < self.to_minute
        return self.at is not None and minute >= self.at


@dataclass
class JobRun:
    name: str
    minute: int
    ok: bool
    detail: str = ""
    seconds: float = 0.0


class Scheduler:
    def __init__(self, jobs: list[Job], owner: str | None = None):
        self.jobs = jobs
        self.owner = owner or f"{socket.gethostname()}:{os.getpid()}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_runs: list[JobRun] = []
        self.is_leader = False
        self.trading_today: bool | None = None

    # ── leadership ────────────────────────────────────────────────
    def acquire_lock(self) -> bool:
        """One engine per deployment. The TTL means a crashed process releases the role
        without anyone intervening."""
        now = time.time()
        col = store.get_db()[store.JOBS]
        doc = col.find_one_and_update(
            {"_id": LOCK_ID, "$or": [{"expires_at": {"$lt": now}}, {"owner": self.owner}]},
            {"$set": {"owner": self.owner, "expires_at": now + LOCK_TTL_S}},
            upsert=False, return_document=True)
        if doc is None:
            existing = col.find_one({"_id": LOCK_ID})
            if existing is None:
                try:
                    col.insert_one({"_id": LOCK_ID, "owner": self.owner,
                                    "expires_at": now + LOCK_TTL_S})
                    doc = {"owner": self.owner}
                except Exception:
                    doc = None
        self.is_leader = bool(doc and doc.get("owner") == self.owner)
        return self.is_leader

    # ── ledger ────────────────────────────────────────────────────
    @staticmethod
    def _ledger_id(day: str, job: str) -> str:
        return f"{day}:{job}"

    def already_ran(self, day: str, job: str) -> bool:
        doc = store.get(store.JOBS, self._ledger_id(day, job))
        return bool(doc and doc.get("ok"))

    def record(self, day: str, run: JobRun) -> None:
        store.put(store.JOBS, {
            "_id": self._ledger_id(day, run.name), "date": day, "job": run.name,
            "ok": run.ok, "minute": run.minute, "detail": run.detail[:500],
            "seconds": round(run.seconds, 2), "owner": self.owner,
            "at": datetime.now(IST).isoformat(),
        })

    # ── the decision, isolated for testing ────────────────────────
    def tick(self, minute: int, day: str, market_open: bool = True) -> list[JobRun]:
        runs: list[JobRun] = []
        for job in self.jobs:
            if not job.due_at(minute):
                continue
            if job.market_day_only and not market_open:
                continue
            if not job.every and self.already_ran(day, job.name):
                continue
            t0 = time.perf_counter()
            try:
                detail = job.fn(day)
                run = JobRun(job.name, minute, True, str(detail or "")[:500],
                             time.perf_counter() - t0)
            except Exception as exc:
                log.exception("job %s failed", job.name)
                run = JobRun(job.name, minute, False, f"{type(exc).__name__}: {exc}",
                             time.perf_counter() - t0)
            runs.append(run)
            if not job.every:
                self.record(day, run)
        if runs:
            self.last_runs = (runs + self.last_runs)[:50]
        return runs

    def catch_up(self, minute: int, day: str, market_open: bool = True) -> list[JobRun]:
        """On start, run anything whose time has passed today and which never completed.
        Ordered by scheduled time so 09:31's work happens before 09:35's."""
        pending = [j for j in self.jobs
                   if not j.every and j.catch_up and j.at is not None and j.at <= minute
                   and not self.already_ran(day, j.name)]
        if not pending:
            return []
        log.warning("catch-up: %s", ", ".join(j.name for j in pending))
        runs = []
        for job in sorted(pending, key=lambda j: j.at):
            saved, self.jobs = self.jobs, [job]
            runs += self.tick(minute, day, market_open)
            self.jobs = saved
        return runs

    # ── the loop ──────────────────────────────────────────────────
    def start(self, market_open_probe: Callable[[], bool] | None = None) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="orb-scheduler",
                                        daemon=True,
                                        kwargs={"probe": market_open_probe})
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self, probe: Callable[[], bool] | None = None) -> None:
        first = True
        while not self._stop.is_set():
            now = now_ist()
            minute = now.hour * 60 + now.minute
            day = now.date().isoformat()
            try:
                if self.acquire_lock():
                    open_now = probe() if probe else True
                    if first:
                        self.catch_up(minute, day, open_now)
                        first = False
                    self.tick(minute, day, open_now)
                    self._heartbeat(minute, day, open_now)
                else:
                    log.debug("another process holds the engine lock")
            except Exception:
                log.exception("scheduler pass failed — continuing")
            self._sleep_to_next_minute()

    def _heartbeat(self, minute: int, day: str, market_open: bool) -> None:
        store.put(store.HEALTH, {
            "_id": HEARTBEAT_ID, "date": day, "minute": minute, "owner": self.owner,
            "market_open": market_open, "at": time.time(),
            "recent": [r.__dict__ for r in self.last_runs[:10]],
        })

    def _sleep_to_next_minute(self) -> None:
        """Sleep to the next absolute minute boundary plus a small offset, so a job that
        needs the minute that just closed sees a complete one."""
        now = datetime.now(IST)
        nxt = (now + timedelta(minutes=1)).replace(second=2, microsecond=0)
        self._stop.wait(max(1.0, (nxt - now).total_seconds()))


def heartbeat() -> dict | None:
    doc = store.get(store.HEALTH, HEARTBEAT_ID)
    if doc:
        doc["age_s"] = round(time.time() - doc.get("at", 0), 1)
    return doc
