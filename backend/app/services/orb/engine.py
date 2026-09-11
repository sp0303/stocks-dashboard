"""The live engine: feed + recorder + scheduler + strategy, wired to the trading day.

Stage 1 (record only) and stage 2 (record and decide) are the same process with one
switch. `ORB_STRATEGY_ENABLED` stays false until reconciliation has scored five clean
sessions — the recorder has to earn the right to be traded on.

Started from the FastAPI lifespan when ORB_ENABLED is set. Everything runs on its own
threads: the websocket SDK is thread-based and every Angel call is blocking, so none of
this belongs on the request event loop.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from app.config import settings
from app.services.orb import calendar as orb_calendar
from app.services.orb import recon, signals, store
from app.services.orb.config import DEFAULT, OrbConfig
from app.services.orb.feed import Feed
from app.services.orb.recorder import Recorder
from app.services.orb.scheduler import Job, Scheduler, heartbeat
from app.services.orb.session import (IST, MARKET_CLOSE, MARKET_OPEN, OR_END, SQUARE_OFF,
                                      ENTRY_CUTOFF, ENTRY_FIRST, now_ist, today_ist)
from app.services.orb.universe import (INDEX_TOKENS, MARKET_INDEX, VIX_INDEX,
                                       equity_candidates)

log = logging.getLogger("orb.engine")

PREP_MINUTE = 8 * 60 + 45          # 08:45  baselines, universe, subscribe
PROBE_MINUTE = 9 * 60 + 16         # 09:16  did the market actually open?
SCREEN_MINUTE = OR_END + 1         # 09:31  opening range + gates
RECON_MINUTE = 15 * 60 + 40        # 15:40  reconcile against Angel's own candles


class Engine:
    def __init__(self, cfg: OrbConfig = DEFAULT, strategy_enabled: bool | None = None):
        self.cfg = cfg
        self.strategy_enabled = (settings.orb_strategy_enabled
                                 if strategy_enabled is None else strategy_enabled)
        self.day = today_ist().isoformat()
        self.recorder = Recorder()
        self.feed = Feed(self.recorder.on_tick)
        self.baselines: dict[str, signals.Baseline] = {}
        self.shortlist: list[str] = []
        self.book = signals.PaperBook(self.day, cfg)
        self.members: list[dict] = []
        self.scheduler = Scheduler(self._jobs())
        self.last_error = ""

    # ── jobs ──────────────────────────────────────────────────────
    def _jobs(self) -> list[Job]:
        return [
            Job("prep", self.job_prep, at=PREP_MINUTE, market_day_only=False),
            Job("probe", self.job_probe, at=PROBE_MINUTE, market_day_only=False),
            Job("flush", self.job_flush, every=True,
                from_minute=MARKET_OPEN, to_minute=MARKET_CLOSE + 2),
            Job("screen", self.job_screen, at=SCREEN_MINUTE),
            Job("decide", self.job_decide, every=True,
                from_minute=ENTRY_FIRST, to_minute=ENTRY_CUTOFF + 1),
            Job("manage", self.job_manage, every=True,
                from_minute=ENTRY_FIRST, to_minute=SQUARE_OFF),
            Job("square_off", self.job_square_off, at=SQUARE_OFF),
            Job("finalize", self.job_finalize, at=MARKET_CLOSE + 1),
            Job("reconcile", self.job_reconcile, at=RECON_MINUTE),
        ]

    # ── 08:45 ─────────────────────────────────────────────────────
    def job_prep(self, day: str) -> str:
        self.day = day
        self.recorder = Recorder()
        self.book = signals.PaperBook(day, self.cfg)
        self.shortlist = []

        rows = store.find(store.UNIVERSE, {}, sort=[("date", -1)], limit=1)
        if not rows:
            raise RuntimeError("no universe stored — run scripts/orb_backfill.py universe")
        self.members = rows[0]["members"]
        self.baselines = signals.prepare_day(day, self.members)

        for m in self.members:
            self.recorder.register(m["sym"], m["token"])
        for name, token in INDEX_TOKENS.items():
            self.recorder.register(name, token)          # indices for D5/D6, and the VIX

        tokens = [m["token"] for m in self.members] + list(INDEX_TOKENS.values())
        self.feed.stop()
        self.feed.start(tokens)
        return f"{len(self.members)} symbols + {len(INDEX_TOKENS)} indices subscribed"

    # ── 09:16 ─────────────────────────────────────────────────────
    def job_probe(self, day: str) -> str:
        """If nothing anywhere has traded a minute into the session, the market is not
        open — an unscheduled closure that no published holiday list would have carried.
        Every market job then stands down for the day."""
        open_now = self.recorder.market_is_open()
        store.put(store.CALENDAR, {**(orb_calendar.entry(day) or {"_id": day, "date": day}),
                                   "probe_open": open_now, "probe_at": now_ist().isoformat()})
        if not open_now:
            log.warning("no ticks by %s — standing down for the day", day)
        return f"market_open={open_now}"

    def market_open_probe(self) -> bool:
        n = now_ist()
        if (n.hour * 60 + n.minute) < PROBE_MINUTE:
            return True                       # too early to conclude anything
        return self.recorder.market_is_open()

    # ── every minute ──────────────────────────────────────────────
    def job_flush(self, day: str) -> str:
        return f"{self.recorder.flush()} bars"

    def job_screen(self, day: str) -> str:
        doc = signals.run_screen(day, self.recorder, self.baselines, self.cfg)
        self.shortlist = doc["shortlist"]
        if self.shortlist:
            tokens = [self.baselines[s].token for s in self.shortlist
                      if s in self.baselines]
            self.feed.upgrade_to_snap_quote(tokens)   # circuit limits for gate A7
        return f"{doc['passed']}/{doc['candidates']} passed; shortlist {self.shortlist}"

    def job_decide(self, day: str) -> str:
        if not self.strategy_enabled or not self.shortlist:
            return "strategy disabled" if not self.strategy_enabled else "no shortlist"
        n = now_ist()
        minute = n.hour * 60 + n.minute
        if (minute - MARKET_OPEN) % self.cfg.signal_timeframe_min != 0:
            return ""                          # only on 5-minute boundaries
        fired = signals.run_decide(day, minute, self.recorder, self.baselines,
                                   self.shortlist, self.book, self.cfg)
        return f"{len(fired)} entries" if fired else ""

    def job_manage(self, day: str) -> str:
        if not self.strategy_enabled or not self.book.open:
            return ""
        n = now_ist()
        events = signals.run_manage(day, n.hour * 60 + n.minute, self.recorder,
                                    self.baselines, self.book, self.cfg)
        return ", ".join(f"{e['sym']}:{e['event']}" for e in events)

    def job_square_off(self, day: str) -> str:
        if not self.strategy_enabled:
            return "strategy disabled"
        out = signals.square_off(day, SQUARE_OFF, self.recorder, self.book)
        return f"{len(out)} positions closed"

    # ── after the close ───────────────────────────────────────────
    def job_finalize(self, day: str) -> str:
        written = self.recorder.finalize()
        self.feed.stop()
        orb_calendar.rebuild(date.fromisoformat(day), date.fromisoformat(day))
        stats = self.recorder.stats()
        store.put(store.HEALTH, {"_id": f"{day}:recorder", "date": day,
                                 "kind": "recorder", **stats})
        return f"{written} final bars; {stats['ticks']} ticks"

    def job_reconcile(self, day: str) -> str:
        from app.services.orb.universe import Instrument

        insts = [Instrument(symbol=m["sym"], token=m["token"], series=m.get("series", "EQ"),
                            tick=int(m.get("tick") or 5)) for m in self.members]
        if not insts:
            return "no members"
        doc = recon.reconcile_day(insts, day)
        return f"agreement {doc['agree_pct']}% over {doc['minutes_compared']} minutes"

    # ── lifecycle ─────────────────────────────────────────────────
    def start(self) -> None:
        store.ensure_indexes()
        self.scheduler.start(market_open_probe=self.market_open_probe)
        log.info("ORB engine started (strategy %s)",
                 "ON" if self.strategy_enabled else "OFF — recording only")

    def stop(self) -> None:
        self.scheduler.stop()
        self.feed.stop()

    def status(self) -> dict:
        return {
            "date": self.day,
            "strategy_enabled": self.strategy_enabled,
            "config": self.cfg.version,
            "feed": self.feed.status.as_dict(),
            "recorder": self.recorder.stats(),
            "shortlist": self.shortlist,
            "open_positions": list(self.book.open),
            "day_r": round(self.book.day_r, 2),
            "heartbeat": heartbeat(),
            "is_leader": self.scheduler.is_leader,
            "exit_test": recon.exit_test(),
        }


_engine: Engine | None = None
_start_error: str = ""


def get_engine() -> Engine | None:
    return _engine


def start_error() -> str:
    return _start_error


def start_engine() -> Engine | None:
    """Called from the app lifespan. Never raises into startup: a misconfigured ORB
    engine must not stop the rest of the dashboard from serving."""
    global _engine
    if not settings.orb_enabled:
        log.info("ORB engine disabled (set ORB_ENABLED=true to run it)")
        return None
    try:
        _engine = Engine()
        _engine.start()
        return _engine
    except Exception as exc:
        global _start_error
        log.exception("ORB engine failed to start")
        _engine, _start_error = None, f"{type(exc).__name__}: {exc}"
        return None


def stop_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.stop()
        _engine = None
