"""R10 dead-ticker guard: sessions_behind and is_alarm."""

from datetime import date, datetime, timezone

from pi_api.modules.market import health


def _utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_empty_calendar_falls_back_to_weekdays():
    sessions = health.expected_sessions([], None, date(2026, 10, 4))
    assert date(2026, 10, 3) not in sessions and date(2026, 10, 2) in sessions
    assert all(d.weekday() < 5 for d in sessions)


def test_calendar_used_then_extended_with_weekdays_after_its_end():
    open_days = [date(2026, 9, 30), date(2026, 10, 1)]  # 2 Oct holiday: not open
    sessions = health.expected_sessions(open_days, date(2026, 10, 2), date(2026, 10, 7))
    assert sessions == [
        date(2026, 9, 30),
        date(2026, 10, 1),
        date(2026, 10, 5),
        date(2026, 10, 6),
        date(2026, 10, 7),
    ]


def test_stale_benchmark_alarms_the_old_bug_case():
    """Frozen at 22 Sep, now Sun 4 Oct with an empty calendar: was 0 / no alarm."""
    now = _utc(2026, 10, 4, 6)
    sessions = health.expected_sessions([], None, date(2026, 10, 4))
    last = health.last_expected_session(now, sessions)
    behind = health.sessions_behind(date(2026, 9, 22), sessions, last)
    assert last == date(2026, 10, 2)
    assert behind == 8  # 23,24,25,28,29,30 Sep, 1,2 Oct: weekdays, no calendar
    assert health.is_alarm(behind)


def test_holiday_is_not_counted_when_calendar_knows_it():
    open_days = [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]
    sessions = health.expected_sessions(open_days, date(2026, 10, 2), date(2026, 10, 4))
    last = health.last_expected_session(_utc(2026, 10, 4, 6), sessions)
    assert last == date(2026, 10, 1)
    assert health.sessions_behind(date(2026, 10, 1), sessions, last) == 0
    assert not health.is_alarm(0)


def test_threshold_is_more_than_two_sessions():
    assert not health.is_alarm(2)
    assert health.is_alarm(3)


def test_no_values_at_all_alarms():
    assert health.sessions_behind(None, [date(2026, 10, 1)], date(2026, 10, 1)) is None
    assert health.is_alarm(None)


def test_today_not_expected_before_eod_ready():
    sessions = [date(2026, 10, 5), date(2026, 10, 6)]
    # 10:00 IST on Tue 6 Oct -> today's close not due yet
    assert health.last_expected_session(_utc(2026, 10, 6, 4, 30), sessions) == date(
        2026, 10, 5
    )
    # 17:00 IST -> due
    assert health.last_expected_session(_utc(2026, 10, 6, 11, 30), sessions) == date(
        2026, 10, 6
    )
