"""The trading calendar, derived from the data.

NSE publishes a holiday master, but it sits behind Akamai and refuses datacenter
traffic — it returns 403 from most server environments, intermittently from the rest.
A live engine cannot have a hard dependency on that.

So a trading day is defined as *a day the data says trading happened*: a weekday on
which a decisive share of the universe produced real (non-synthetic) bars. The backfill
therefore builds two years of calendar as a by-product, exactly, with no external call.
The published list, when it can be fetched, is used only to cross-check — a
disagreement is recorded for a human to look at, never acted on.

Half-days fall out of the same computation: the session end is the last minute at which
a decisive share of the universe was still trading, so the square-off shifts with it.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.services.orb import store
from app.services.orb.session import MARKET_CLOSE, MARKET_OPEN, SQUARE_OFF

log = logging.getLogger("orb.calendar")

# A day counts as trading when this fraction of the symbols we hold data for produced
# real bars. Set well above zero so one stale or mis-keyed symbol cannot invent a
# session, and well below one so a handful of suspended names cannot erase a real one.
QUORUM = 0.5

# How close to the normal close a session must run to count as a full day.
FULL_DAY_TOLERANCE_MIN = 5


def derive_day(day: str) -> dict:
    """Build (but do not store) the calendar entry for one date."""
    d = date.fromisoformat(day)
    docs = store.session_coverage(day)
    symbols = len(docs)
    with_data = 0
    last_reals: list[int] = []
    for doc in docs:
        syn = doc.get("syn") or []
        real = sum(1 for s in syn if not s) if syn else doc.get("n", 0)
        if real > 0:
            with_data += 1
        lr = doc.get("last_real")
        if lr:
            last_reals.append(lr)

    weekend = d.weekday() >= 5
    ratio = (with_data / symbols) if symbols else 0.0
    # The data decides, including on a weekend: NSE holds Muhurat sessions on days the
    # weekday check would reject outright (8 Nov 2026 is a Sunday). `weekend` stays on
    # the record as context, never as a veto.
    trading = symbols > 0 and ratio >= QUORUM

    session_end = MARKET_CLOSE
    if trading and last_reals:
        last_reals.sort()
        # The median symbol's last trade: robust to one illiquid name that stopped early
        # and to one late print.
        median_last = last_reals[len(last_reals) // 2]
        if median_last < MARKET_CLOSE - FULL_DAY_TOLERANCE_MIN:
            session_end = median_last + 1

    return {
        "_id": day, "date": day, "trading": trading, "weekend": weekend,
        "symbols": symbols, "with_data": with_data, "ratio": round(ratio, 3),
        "session_end": session_end,
        "half_day": trading and session_end < MARKET_CLOSE,
        "square_off": min(SQUARE_OFF, session_end - 20),
        "source": "derived",
    }


def rebuild(start: date, end: date) -> dict:
    """Derive and store every date in the window. Idempotent."""
    trading, half = 0, 0
    d = start
    while d <= end:
        entry = derive_day(d.isoformat())
        store.put(store.CALENDAR, entry)
        trading += 1 if entry["trading"] else 0
        half += 1 if entry["half_day"] else 0
        d += timedelta(days=1)
    log.info("calendar %s..%s: %d trading days, %d half days", start, end, trading, half)
    return {"from": start.isoformat(), "to": end.isoformat(),
            "trading_days": trading, "half_days": half}


def trading_days(start: date, end: date) -> list[str]:
    rows = store.find(store.CALENDAR,
                      {"trading": True, "date": {"$gte": start.isoformat(),
                                                 "$lte": end.isoformat()}},
                      sort=[("date", 1)])
    return [r["date"] for r in rows]


def prior_trading_days(day: str, n: int) -> list[str]:
    """The n trading days immediately before `day`, oldest first. This is the lookback
    every baseline in features.py is built on."""
    rows = store.find(store.CALENDAR, {"trading": True, "date": {"$lt": day}},
                      sort=[("date", -1)], limit=n)
    return [r["date"] for r in reversed(rows)]


def entry(day: str) -> dict | None:
    return store.get(store.CALENDAR, day)


# NSE equity full-day trading holidays. The derived calendar above is hindsight only —
# today's entry does not exist until after the close — so the LIVE engine needs a
# forward-looking check. NSE's holiday API refuses datacenter traffic (see the module
# docstring), so this is a maintained constant: refresh it once a year from the NSE
# circular. It is only an OPTIMISATION that stops the engine subscribing on a known
# closure; the reactive tick-probe (engine.market_open_probe) remains the authority, so
# a stale entry here at worst wastes or skips one paper session, never trades a shut
# market. Bias the list toward certainty — omit a doubtful date rather than skip a real
# session; an unlisted holiday is caught by the probe anyway.
NSE_HOLIDAYS: set[str] = {
    # 2026 — verify against the NSE circular when it publishes 2027.
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Holi
    "2026-03-26",  # Ram Navami
    "2026-03-31",  # Mahavir Jayanti
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-28",  # Bakri Eid
    "2026-06-26",  # Muharram
    "2026-09-14",  # Ganesh Chaturthi
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-10",  # Diwali (Balipratipada)
    "2026-11-24",  # Guru Nanak Jayanti
    "2026-12-25",  # Christmas
}


def is_scheduled_market_day(day: str) -> bool:
    """Forward-looking weekday/holiday check for the live engine. Weekends and listed
    holidays are non-trading; every other day is assumed to trade and is confirmed by the
    reactive tick-probe. (Muhurat's special evening session is not the 09:15 ORB session,
    so a Muhurat weekend correctly reads as non-trading here.)"""
    d = date.fromisoformat(day)
    if d.weekday() >= 5:
        return False
    return day not in NSE_HOLIDAYS


def is_trading_day(day: str) -> bool:
    e = entry(day)
    return bool(e and e.get("trading"))


def session_bounds(day: str) -> tuple[int, int, int]:
    """(open, session_end, square_off) for a date — half-day aware."""
    e = entry(day) or {}
    end = e.get("session_end", MARKET_CLOSE)
    return MARKET_OPEN, end, e.get("square_off", min(SQUARE_OFF, end - 20))


# ── optional cross-check ──────────────────────────────────────────
def cross_check(published: set[str], start: date, end: date) -> dict:
    """Compare the derived calendar with a published holiday list. Returns the
    disagreements; the caller logs them for a human. Nothing here changes the
    calendar — the data is the authority, precisely because the list may be
    unavailable, stale, or wrong about an unscheduled closure."""
    derived_trading = set(trading_days(start, end))
    weekdays = set()
    d = start
    while d <= end:
        if d.weekday() < 5:
            weekdays.add(d.isoformat())
        d += timedelta(days=1)
    derived_holidays = weekdays - derived_trading
    return {
        "traded_but_listed_as_holiday": sorted(derived_trading & published),
        "no_data_but_not_a_listed_holiday": sorted(derived_holidays - published),
        "agree": len(derived_holidays & published),
    }
