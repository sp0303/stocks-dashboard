"""Trading calendar generator adhering to Rule R11."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Set


def generate_trading_calendar(
    start_date: date,
    end_date: date,
    known_holidays: Set[date] | None = None,
    extra_trading_dates: Iterable[date] | None = None,
) -> List[date]:
    """Generates consecutive market trading dates between start_date and end_date.

    Excludes weekends (Saturday, Sunday) and known market holidays.
    Includes any explicit extra_trading_dates (e.g. special Muhurat trading sessions).
    """
    holidays = known_holidays or set()
    extras = set(extra_trading_dates or [])

    calendar: List[date] = []
    curr = start_date
    while curr <= end_date:
        is_weekend = curr.weekday() in (5, 6)
        if (not is_weekend and curr not in holidays) or curr in extras:
            calendar.append(curr)
        curr += timedelta(days=1)

    return calendar
