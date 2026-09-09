"""Segment A — REST backfill of historical candles into Mongo.

Angel caps a single historical request by interval: 30 days at 1-minute, 2,000 at
daily. This module chunks accordingly, converts to the engine's storage conventions
(integer paise, minute-of-day IST, dense sessions), and records progress so a crash at
symbol 140 of 200 costs nothing.

Rate limiting is not implemented here — services/angel.py already gates every call to
Angel's published 3/s and 180/min historical ceilings. The practical constraint on a
two-year pull is the 5,000/hour cap, which puts 200 symbols at roughly an hour.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from app.services import angel
from app.services.orb import store
from app.services.orb.bars import Bar, densify
from app.services.orb.session import (IST, MARKET_CLOSE, MARKET_OPEN, minute_of_day,
                                      to_paise)
from app.services.orb.universe import Instrument

log = logging.getLogger("orb.history")

CHUNK_DAYS = {"1m": 28, "5m": 90, "1d": 1800}     # under Angel's caps, with headroom


def _fmt(d: date, minute: int) -> str:
    return f"{d.isoformat()} {minute // 60:02d}:{minute % 60:02d}"


def _rows_to_bars(rows: list[list]) -> dict[str, list[Bar]]:
    """Angel rows -> {YYYY-MM-DD: [Bar]}. Prices arrive in rupees here (unlike the
    websocket, which sends paise), so this is the conversion point."""
    out: dict[str, list[Bar]] = {}
    for r in rows or []:
        try:
            ts = datetime.fromisoformat(r[0])
        except (ValueError, TypeError, IndexError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=IST)
        day = ts.astimezone(IST).date().isoformat()
        out.setdefault(day, []).append(Bar(
            minute=minute_of_day(ts), o=to_paise(r[1]), h=to_paise(r[2]),
            l=to_paise(r[3]), c=to_paise(r[4]), v=int(r[5] or 0)))
    return out


# ── daily ─────────────────────────────────────────────────────────
def backfill_daily(inst: Instrument, start: date, end: date) -> int:
    """One request covers years at ONE_DAY. Gives liquidity ranking, ATR history and
    previous-day levels for the whole candidate pool cheaply."""
    rows = angel.get_candles(inst.token, inst.exchange, "1d",
                             _fmt(start, MARKET_OPEN), _fmt(end, MARKET_CLOSE))
    if rows is None:
        return -1                      # call failed; distinct from "no trades"
    out = []
    for r in rows:
        try:
            day = datetime.fromisoformat(r[0]).date().isoformat()
        except (ValueError, TypeError):
            continue
        out.append({"date": day, "o": to_paise(r[1]), "h": to_paise(r[2]),
                    "l": to_paise(r[3]), "c": to_paise(r[4]), "v": int(r[5] or 0)})
    store.save_daily(inst.symbol, out)
    return len(out)


# ── minute ────────────────────────────────────────────────────────
def fetch_minute_window(inst: Instrument, start: date, end: date) -> dict[str, list[Bar]] | None:
    rows = angel.get_candles(inst.token, inst.exchange, "1m",
                             _fmt(start, MARKET_OPEN), _fmt(end, MARKET_CLOSE))
    if rows is None:
        return None
    return _rows_to_bars(rows)


def backfill_minute(inst: Instrument, start: date, end: date,
                    skip_present: bool = True, on_progress=None) -> dict:
    """Walk the window in chunks, writing one dense document per session.

    `skip_present` makes a re-run cheap: a chunk whose days are already stored is not
    re-fetched. That is what turns an interrupted two-hour pull into a resumable one.
    """
    have = store.sessions_present(inst.symbol) if skip_present else set()
    days_written, chunks, failures = 0, 0, 0
    cursor = start
    step = timedelta(days=CHUNK_DAYS["1m"])
    while cursor <= end:
        chunk_end = min(cursor + step - timedelta(days=1), end)
        wanted = {d.isoformat() for d in _weekdays(cursor, chunk_end)}
        if skip_present and wanted and wanted <= have:
            cursor = chunk_end + timedelta(days=1)
            continue
        by_day = fetch_minute_window(inst, cursor, chunk_end)
        chunks += 1
        if by_day is None:
            failures += 1
            log.warning("%s: chunk %s..%s failed", inst.symbol, cursor, chunk_end)
        else:
            for day, bars in by_day.items():
                dense = densify(bars, MARKET_OPEN, MARKET_CLOSE)
                last_real = max((b.minute for b in bars), default=None)
                store.save_session(inst.symbol, day, dense, src="rest",
                                   last_real=last_real, real_bars=len(bars))
                days_written += 1
                have.add(day)
        if on_progress:
            on_progress(inst.symbol, cursor, chunk_end, days_written)
        cursor = chunk_end + timedelta(days=1)

    manifest = {"_id": inst.symbol, "sym": inst.symbol, "token": inst.token,
                "from": start.isoformat(), "to": end.isoformat(),
                "days": len(store.sessions_present(inst.symbol)),
                "chunks": chunks, "failures": failures,
                "updated_at": datetime.now(IST).isoformat()}
    store.put(store.BACKFILL, manifest)
    return manifest


def _weekdays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ── liquidity ranking ─────────────────────────────────────────────
def median_turnover_cr(sym: str, lookback: int = 20) -> float | None:
    """20-day median traded value in rupees crore, from stored daily candles. This is
    what replaces F&O membership as the liquidity filter."""
    from statistics import median

    rows = store.load_daily(sym, limit=lookback)
    vals = [((r["h"] + r["l"] + r["c"]) / 3.0 / 100.0) * r["v"] / 1e7
            for r in rows if r.get("v")]
    return median(vals) if vals else None
