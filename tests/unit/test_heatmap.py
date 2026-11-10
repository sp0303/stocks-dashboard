"""Holdings heatmap maths (pi_core.heatmap): one day's move, period returns, splits. Ported from v1."""

import math
import random

import pytest
from pi_core import heatmap as hm


def test_day_return_is_close_to_close_and_missing_day_is_none():
    s = {
        "A": hm.adjusted_closes([("2026-10-29", 100), ("2026-10-30", 103)]),
        "B": hm.adjusted_closes([("2026-10-29", 50)]),
    }
    r = hm.day_returns(s, "2026-10-30")
    assert math.isclose(r["A"]["ret"], 0.03) and r["A"]["prev_close"] == 100
    assert r["B"]["ret"] is None and r["B"]["close"] is None


def test_first_bar_has_no_return_but_keeps_its_close():
    r = hm.day_returns({"A": [("2026-10-30", 103.0)]}, "2026-10-30")
    assert r["A"]["ret"] is None and r["A"]["close"] == 103.0


def test_split_jump_is_adjusted_only_when_the_series_shows_it():
    split = [{"type": "SPLIT", "ex_date": "2025-12-26", "qty_multiplier": 5.0}]
    raw = hm.adjusted_closes([("2025-12-24", 6000), ("2025-12-26", 1210)], split)
    assert math.isclose(raw[0][1], 1200) and raw[1][1] == 1210  # as-traded: adjusted
    already = hm.adjusted_closes([("2025-12-24", 1200), ("2025-12-26", 1210)], split)
    assert already[0][1] == 1200  # already adjusted: left alone
    r = hm.day_returns({"N": raw}, "2025-12-26")
    assert math.isclose(r["N"]["ret"], 1210 / 1200 - 1) and not r["N"]["suspect"]


def test_unexplained_big_move_is_flagged_suspect():
    r = hm.day_returns(
        {"X": [("2026-10-29", 100.0), ("2026-10-30", 50.0)]}, "2026-10-30"
    )
    assert r["X"]["suspect"] is True


def test_range_matrix_starts_at_each_stocks_tracking_day():
    s = {
        "A": hm.adjusted_closes(
            [
                ("2026-10-01", 90),
                ("2026-10-02", 100),
                ("2026-10-05", 110),
                ("2026-10-06", 99),
            ]
        ),
        "B": hm.adjusted_closes(
            [("2026-10-01", 10), ("2026-10-05", 12), ("2026-10-06", 12)]
        ),
    }
    m = hm.range_matrix(s, {"A": "2026-10-02", "B": "2026-10-05"}, "2026-10-06", "day")
    rows = {r["symbol"]: r for r in m["rows"]}
    assert rows["A"]["start"] == "2026-10-02" and "2026-10-01" not in rows["A"]["cells"]
    assert math.isclose(rows["A"]["cells"]["2026-10-05"], 0.10)
    assert math.isclose(rows["A"]["cells"]["2026-10-06"], -0.10)
    assert math.isclose(rows["A"]["total"], -0.01)
    assert (
        rows["B"]["cells"]["2026-10-05"] == 0.0 and rows["B"]["total"] == 0.0
    )  # 0 is a value (R12)
    assert [c["key"] for c in m["columns"]] == [
        "2026-10-02",
        "2026-10-05",
        "2026-10-06",
    ]


def test_grain_and_period_keys():
    assert hm.pick_grain("2026-09-01", "2026-10-15") == "day"
    assert hm.pick_grain("2025-11-01", "2026-10-15") == "week"
    assert hm.pick_grain("2021-01-01", "2026-10-15") == "month"
    assert hm.period_of("2026-10-06", "week") == "2026-W41"
    assert hm.period_of("2026-10-06", "month") == "2026-10"


def test_common_latest_ignores_one_stray_late_bar():
    s = {
        "A": [("2026-11-06", 1.0)],
        "B": [("2026-11-06", 1.0)],
        "C": [("2026-11-08", 1.0)],
    }
    assert hm.common_latest(s) == "2026-11-06"


@pytest.mark.parametrize("seed", range(200))
def test_period_returns_compound_to_total(seed):
    """Property: for any close path and grain, the period cells compound to the total."""
    rnd = random.Random(seed)
    n = rnd.randint(2, 60)
    closes = [rnd.uniform(1, 1e5) for _ in range(n)]
    days = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    grain = rnd.choice(["day", "week", "month"])
    m = hm.range_matrix({"S": list(zip(days, closes))}, {"S": days[0]}, days[-1], grain)
    row = m["rows"][0]
    prod = 1.0
    for v in row["cells"].values():
        prod *= 1 + v
    assert math.isclose(prod - 1, row["total"], rel_tol=1e-9, abs_tol=1e-9)
