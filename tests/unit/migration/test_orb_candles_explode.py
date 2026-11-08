"""1m day-doc explode: synthetic handling, paise integrity, sanity rejects, session selection."""

from datetime import datetime
from zoneinfo import ZoneInfo

from migrate_orb_candles_1m import (
    BYTES_PER_ROW,
    estimate,
    explode_doc,
    minute_to_ts,
    select_sessions,
    to_paise,
    unit_check,
)

IST = ZoneInfo("Asia/Kolkata")


def _doc(**kw):
    d = {
        "_id": "INFY:2025-01-02",
        "sym": "INFY",
        "date": "2025-01-02",
        "exch": "NSE",
        "t": [555, 556, 557],
        "o": [10000, 10010, 10020],
        "h": [10050, 10030, 10020],
        "l": [9990, 10000, 10020],
        "c": [10010, 10020, 10020],
        "v": [500, 300, 0],
        "syn": [False, False, True],
        "n": 3,
    }
    d.update(kw)
    return d


def test_minute_to_ts_is_ist():
    assert minute_to_ts("2025-01-02", 555) == datetime(2025, 1, 2, 9, 15, tzinfo=IST)


def test_paise_copied_unchanged_and_non_integers_rejected():
    assert to_paise(10000) == 10000
    assert to_paise(10000.0) == 10000
    assert to_paise(100.5) is None  # rupees: never rescaled by guesswork
    assert to_paise(True) is None and to_paise(None) is None


def test_explode_flags_synthetic_by_default():
    rows, c = explode_doc(_doc(), 42)
    assert len(rows) == 3
    assert rows[0] == (
        42,
        minute_to_ts("2025-01-02", 555),
        10000,
        10050,
        9990,
        10010,
        500,
        False,
    )
    assert rows[2][-1] is True
    assert c["real"] == 2 and c["synthetic"] == 1


def test_explode_skip_synthetic():
    rows, c = explode_doc(_doc(), 42, skip_synthetic=True)
    assert len(rows) == 2 and all(r[-1] is False for r in rows)
    assert c["skip_synthetic"] == 1


def test_bars_after_last_real_are_synthetic_even_without_syn_array():
    rows, _ = explode_doc(_doc(syn=None, last_real=556), 1)
    assert [r[-1] for r in rows] == [False, False, True]


def test_sanity_rejects():
    d = _doc(o=[10000, 0, 100.5], h=[9000, 10030, 10020])
    rows, c = explode_doc(d, 1)
    assert rows == []
    assert c["reject_bad_ohlc"] == 2 and c["reject_non_paise"] == 1


def test_out_of_session_and_ragged():
    _, c = explode_doc(_doc(t=[500, 556, 557]), 1)
    assert c["reject_out_of_session"] == 1
    rows, c = explode_doc(_doc(v=[1, 2]), 1)
    assert rows == [] and c["doc_ragged_arrays"] == 1


def test_select_latest_sessions_and_estimate():
    ds = ["2025-01-01", "2025-01-03", "2025-01-02", "2025-01-03"]
    assert select_sessions(ds, 2) == ["2025-01-02", "2025-01-03"]
    assert select_sessions(ds, None) == ["2025-01-01", "2025-01-02", "2025-01-03"]
    rows, gb = estimate(1_000_000)
    assert rows == 1_000_000 and gb == 1_000_000 * BYTES_PER_ROW / 1024**3


def test_unit_check_against_daily_close_paise():
    assert unit_check(_doc(), 10020) == "ok"  # last real close (syn bar ignored)
    assert unit_check(_doc(), 1002000) == "looks_rupees"
    assert unit_check(_doc(), 50) == "mismatch"
    assert unit_check(_doc(), None) == "unchecked"
