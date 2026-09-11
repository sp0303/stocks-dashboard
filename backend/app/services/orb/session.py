"""IST session arithmetic.

Every time in this package is a **minute of day in Asia/Kolkata** — a plain int, 555
for 09:15. Wall-clock ints compare and store cleanly, survive JSON, and remove a whole
class of timezone bugs from bar keys and job schedules. Real datetimes appear only at
the edges, where the exchange feed and the scheduler touch the outside world.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Session landmarks, minute-of-day.
MARKET_OPEN = 9 * 60 + 15      # 555  first bar of the session
OR_END = 9 * 60 + 30           # 570  opening range is [MARKET_OPEN, OR_END)
ENTRY_FIRST = 9 * 60 + 35      # 575  earliest 5-minute bar close we may act on
ENTRY_CUTOFF = 11 * 60 + 30    # 690  no new entries at or after this
SQUARE_OFF = 15 * 60 + 10      # 910  unconditional flat
MARKET_CLOSE = 15 * 60 + 30    # 930

FULL_SESSION_BARS = MARKET_CLOSE - MARKET_OPEN  # 375


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def minute_of_day(dt: datetime) -> int:
    """Minute-of-day in IST for an aware datetime (converted) or a naive one (assumed IST)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    ist = dt.astimezone(IST)
    return ist.hour * 60 + ist.minute


def minute_from_epoch_ms(ms: int) -> int:
    """Angel's websocket exchange_timestamp is epoch milliseconds."""
    return minute_of_day(datetime.fromtimestamp(ms / 1000.0, tz=IST))


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_candle_ts(ts: str) -> datetime:
    """Angel candle timestamps look like '2026-09-09T09:15:00+05:30'."""
    return datetime.fromisoformat(ts)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def iso(d: date) -> str:
    return d.isoformat()


def daterange(start: date, end: date):
    """Inclusive of both ends, ascending."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def to_paise(rupees: float) -> int:
    """Prices are stored and compared as integer paise. Angel's websocket already sends
    paise; its REST candles send rupees, so this is the one conversion point."""
    return int(round(rupees * 100))


def to_rupees(paise: int | None) -> float | None:
    return None if paise is None else round(paise / 100.0, 2)
