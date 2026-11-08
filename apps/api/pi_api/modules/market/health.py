"""Benchmark staleness (R10 dead-ticker guard). Pure functions, no I/O.

DOMAIN-RULES R10: "a benchmark whose last value is more than 2 sessions behind
the calendar raises a BLOCK data-quality issue and a visible banner".
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone

ALARM_SESSIONS_BEHIND = 2  # alarm when sessions_behind > 2 (DOMAIN-RULES R10)
IST = timezone(timedelta(hours=5, minutes=30))
EOD_READY_IST = time(16, 0)  # a session's close is not expected before this


def expected_sessions(
    open_days: Iterable[date],
    calendar_max: date | None,
    upto: date,
) -> list[date]:
    """Sessions up to ``upto``: the stored calendar where it exists, weekdays after it.

    The calendar is derived from loaded data, so it stops where the data stops;
    trusting it alone would hide exactly the staleness we are checking for.
    """
    days = sorted(d for d in open_days if d <= upto)
    d = (
        (calendar_max + timedelta(days=1))
        if calendar_max
        else (upto - timedelta(days=400))
    )
    while d <= upto:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def last_expected_session(now: datetime, sessions: list[date]) -> date | None:
    """Latest session whose close should already be available at ``now``."""
    local = now.astimezone(IST)
    today = local.date()
    eligible = [
        d
        for d in sessions
        if d < today or (d == today and local.time() >= EOD_READY_IST)
    ]
    return eligible[-1] if eligible else None


def sessions_behind(
    last_date: date | None, sessions: list[date], last_session: date | None
) -> int | None:
    """Number of expected sessions after ``last_date``; None when there is no data at all."""
    if last_date is None:
        return None
    if last_session is None:
        return 0
    return sum(1 for d in sessions if last_date < d <= last_session)


def is_alarm(behind: int | None) -> bool:
    """No data at all is an alarm too: a missing benchmark must never look healthy."""
    return behind is None or behind > ALARM_SESSIONS_BEHIND


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
