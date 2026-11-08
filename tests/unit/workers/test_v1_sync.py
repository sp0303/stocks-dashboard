"""v1 -> v2 market sync: pure transforms (R6, R10, R11, R17)."""

from datetime import date
from decimal import Decimal

import pytest
from pi_workers.v1_sync import (
    build_upsert_sql,
    derive_calendar,
    map_symbols_to_securities,
    paise_to_rupees,
    transform_benchmark_docs,
    transform_daily_rows,
)

# ---- paise -> rupees -------------------------------------------------------


@pytest.mark.parametrize(
    "paise,rupees",
    [
        (250035, "2500.35"),
        (1, "0.01"),
        (100, "1.00"),
        ("99999", "999.99"),
        (12345.0, "123.45"),
    ],
)
def test_paise_to_rupees_exact(paise, rupees):
    assert paise_to_rupees(paise) == Decimal(rupees)


def test_paise_to_rupees_is_decimal_not_float():
    assert isinstance(paise_to_rupees(10), Decimal)


# ---- daily rows -------------------------------------------------------------


def _row(d, o, h, l, c, v=1000):
    return {"date": d, "o": o, "h": h, "l": l, "c": c, "v": v}


def test_daily_rows_converted_and_sorted():
    rows = [
        _row("2026-10-01", 101_00, 105_00, 100_00, 104_50),
        _row("2026-09-30", 100_00, 102_00, 99_00, 101_00),
    ]
    out, st = transform_daily_rows(rows)
    assert [r.price_date for r in out] == [date(2026, 9, 30), date(2026, 10, 1)]
    assert out[1].close == Decimal("104.50") and out[1].high == Decimal("105.00")
    assert st.accepted == 2 and not st.rejects


def test_daily_rows_reject_bad_and_frozen():
    rows = [
        _row("2026-09-28", 100_00, 101_00, 99_00, 100_00),
        _row("2026-09-29", 100_00, 100_00, 100_00, 100_00, v=0),  # frozen forward-fill
        _row("2026-09-30", 0, 1, 0, 0),  # non-positive
        _row("2026-10-01", 100_00, 99_00, 98_00, 101_00),  # close above high
        {"date": "not-a-date", "o": 1, "h": 1, "l": 1, "c": 1},
    ]
    out, st = transform_daily_rows(rows)
    assert [r.price_date for r in out] == [date(2026, 9, 28)]
    assert st.rejects == {
        "frozen": 1,
        "non_positive": 1,
        "ohlc_inconsistent": 1,
        "bad_date": 1,
    }


def test_daily_rows_flat_bar_with_volume_is_not_frozen():
    rows = [
        _row("2026-09-29", 100_00, 101_00, 99_00, 100_00),
        _row("2026-09-30", 100_00, 100_00, 100_00, 100_00, v=5),
    ]
    out, st = transform_daily_rows(rows)
    assert len(out) == 2 and not st.rejects


def test_daily_rows_since_filters_but_keeps_prev_close_for_frozen_check():
    rows = [
        _row("2026-09-29", 100_00, 101_00, 99_00, 100_00),
        _row("2026-09-30", 100_00, 100_00, 100_00, 100_00, v=0),
    ]
    out, st = transform_daily_rows(rows, since=date(2026, 9, 30))
    assert out == [] and st.rejects == {"frozen": 1}


# ---- calendar ----------------------------------------------------------------


def test_calendar_from_data_marks_holiday_closed_and_never_opens_sunday():
    per_date = {
        date(2026, 9, 30): 2600,  # Wed
        date(2026, 10, 1): 2650,  # Thu
        # 2026-10-02 Fri: Gandhi Jayanti, no rows
        date(2026, 10, 4): 2699,  # Sun: v1 orb_calendar wrongly says open
        date(2026, 10, 5): 2600,  # Mon
    }
    cal = derive_calendar(per_date)
    as_map = {d: is_open for d, is_open, _ in cal}
    assert as_map[date(2026, 10, 1)] is True
    assert as_map[date(2026, 10, 2)] is False
    assert (
        date(2026, 10, 3) not in as_map and date(2026, 10, 4) not in as_map
    )  # weekends not stored
    assert as_map[date(2026, 10, 5)] is True


def test_calendar_ignores_sparse_dates():
    cal = derive_calendar({date(2026, 9, 30): 2600, date(2026, 10, 1): 3})
    assert cal == [(date(2026, 9, 30), True, cal[0][2])]


def test_calendar_empty():
    assert derive_calendar({}) == []


# ---- benchmarks ----------------------------------------------------------------


def test_benchmark_incremental_and_frozen():
    docs = [
        {"date": "2026-09-22", "close": 25000.0},  # already loaded
        {"date": "2026-09-23", "close": 25100.5},
        {"date": "2026-09-24", "close": 25100.5},  # frozen repeat
        {"date": "2026-09-25", "close": 25200.0},
        {"date": "2026-09-26", "close": -1},
    ]
    out, st = transform_benchmark_docs(
        docs, after=date(2026, 9, 22), last_value=Decimal(25000)
    )
    assert out == [
        (date(2026, 9, 23), Decimal("25100.5000")),
        (date(2026, 9, 25), Decimal("25200.0000")),
    ]
    assert st.rejects == {"frozen": 1, "non_positive": 1}


def test_benchmark_first_new_value_equal_to_last_stored_is_frozen():
    out, st = transform_benchmark_docs(
        [{"date": "2026-09-23", "close": 100}], date(2026, 9, 22), Decimal(100)
    )
    assert out == [] and st.rejects == {"frozen": 1}


# ---- upsert SQL builder (idempotency) ------------------------------------------


def test_upsert_sql_is_idempotent_and_guarded():
    sql = build_upsert_sql(
        "market.eod_prices",
        "stg_eod",
        ("security_id", "price_date", "close", "source"),
        ("security_id", "price_date"),
        ("close", "source"),
        "t.source = 'orb_rollup'",
    )
    assert (
        "ON CONFLICT (security_id, price_date) DO UPDATE SET close = EXCLUDED.close"
        in sql
    )
    # An unchanged re-run matches no row in the WHERE, so it updates nothing.
    assert (
        "t.close IS DISTINCT FROM EXCLUDED.close OR t.source IS DISTINCT FROM EXCLUDED.source"
        in sql
    )
    assert "(t.source = 'orb_rollup') AND (" in sql
    assert sql.endswith("RETURNING (xmax = 0) AS inserted")
    assert sql == build_upsert_sql(
        "market.eod_prices",
        "stg_eod",
        ("security_id", "price_date", "close", "source"),
        ("security_id", "price_date"),
        ("close", "source"),
        "t.source = 'orb_rollup'",
    )


def test_upsert_sql_insert_only():
    sql = build_upsert_sql(
        "market.benchmark_values",
        "stg",
        ("benchmark_id", "value_date"),
        ("benchmark_id", "value_date"),
    )
    assert "DO NOTHING" in sql and "DO UPDATE" not in sql


def test_upsert_sql_rejects_unsafe_identifiers():
    with pytest.raises(ValueError):
        build_upsert_sql("t", "s", ("a; DROP TABLE x",), ("a",))


def test_symbol_mapping_with_alias():
    m = map_symbols_to_securities(
        {"RELIANCE": 1, "OLDCO": 2}, [("OLDCO", "NEWCO"), ("GONE", "X")]
    )
    assert m == {"RELIANCE": [1], "OLDCO": [2], "NEWCO": [2]}
