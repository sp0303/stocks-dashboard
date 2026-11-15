"""Holdings heatmap maths: one day's move, period returns since the tracking day, splits."""
import math

from app.services import heatmap as hm


def _pts(*pairs):
    return [{"date": d, "close": c} for d, c in pairs]


def test_day_return_is_close_to_close_and_missing_day_is_none():
    s = {"A": hm.adjusted_closes(_pts(("2026-10-29", 100), ("2026-10-30", 103))),
         "B": hm.adjusted_closes(_pts(("2026-10-29", 50)))}
    r = hm.day_returns(s, "2026-10-30")
    assert math.isclose(r["A"]["ret"], 0.03) and r["A"]["prev_close"] == 100
    assert r["B"]["ret"] is None


def test_split_jump_is_adjusted_only_when_the_series_shows_it():
    split = [{"type": "SPLIT", "ex_date": "2025-12-26", "qty_multiplier": 5.0}]
    raw = hm.adjusted_closes(_pts(("2025-12-24", 6000), ("2025-12-26", 1210)), split)
    assert math.isclose(raw[0][1], 1200) and raw[1][1] == 1210          # as-traded: adjusted
    already = hm.adjusted_closes(_pts(("2025-12-24", 1200), ("2025-12-26", 1210)), split)
    assert already[0][1] == 1200                                          # adjusted: left alone
    r = hm.day_returns({"N": raw}, "2025-12-26")
    assert math.isclose(r["N"]["ret"], 1210 / 1200 - 1) and not r["N"]["suspect"]


def test_range_matrix_starts_at_each_stocks_tracking_day():
    s = {"A": hm.adjusted_closes(_pts(("2026-10-01", 90), ("2026-10-02", 100), ("2026-10-05", 110), ("2026-10-06", 99))),
         "B": hm.adjusted_closes(_pts(("2026-10-01", 10), ("2026-10-05", 12), ("2026-10-06", 12)))}
    m = hm.range_matrix(s, {"A": "2026-10-02", "B": "2026-10-05"}, "2026-10-06", "day")
    rows = {r["symbol"]: r for r in m["rows"]}
    assert rows["A"]["start"] == "2026-10-02" and "2026-10-01" not in rows["A"]["cells"]
    assert math.isclose(rows["A"]["cells"]["2026-10-05"], 0.10)
    assert math.isclose(rows["A"]["cells"]["2026-10-06"], -0.10)
    assert math.isclose(rows["A"]["total"], -0.01)
    assert rows["B"]["cells"]["2026-10-05"] == 0.0 and rows["B"]["total"] == 0.0
    assert [c["key"] for c in m["columns"]] == ["2026-10-02", "2026-10-05", "2026-10-06"]


def test_weekly_and_monthly_buckets_chain_into_the_total():
    s = {"A": hm.adjusted_closes(_pts(("2026-01-05", 100), ("2026-01-30", 110), ("2026-02-27", 121)))}
    m = hm.range_matrix(s, {"A": "2026-01-05"}, "2026-02-27", "month")
    cells = m["rows"][0]["cells"]
    assert math.isclose(cells["2026-01"], 0.10) and math.isclose(cells["2026-02"], 0.10)
    assert math.isclose((1 + cells["2026-01"]) * (1 + cells["2026-02"]) - 1, m["rows"][0]["total"])


def test_grain_follows_the_span():
    assert hm.pick_grain("2026-09-01", "2026-10-30") == "day"
    assert hm.pick_grain("2025-11-01", "2026-10-30") == "week"
    assert hm.pick_grain("2021-06-14", "2026-10-30") == "month"


def test_unexplained_huge_move_is_flagged():
    s = {"A": hm.adjusted_closes(_pts(("2026-10-29", 100), ("2026-10-30", 45)))}
    assert hm.day_returns(s, "2026-10-30")["A"]["suspect"] is True
