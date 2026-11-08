"""Golden + property tests for manager-book aggregation (R5, R6, R10, R12, R16)."""

import random
from datetime import date, timedelta
from uuid import uuid4

import pytest
from pi_api.modules.admin import book_math


def _day(i):
    return date(2026, 1, 1) + timedelta(days=i)


def test_index_units_golden_flat_index_tracks_zero_pnl():
    # R10: with a flat index the benchmark P&L is 0 whatever the flows.
    book = [
        {"as_of": _day(i), "net_invested": n} for i, n in enumerate([100, 150, 50, 50])
    ]
    res = book_math.index_units(book, {_day(i): 200.0 for i in range(4)})
    assert res["points"] == pytest.approx([0, 0, 0, 0])
    assert res["stale"] is False


def test_index_units_golden_full_exit_keeps_gain():
    # Buy 1000 at 100, index +10% to 110, sell all 1100 -> benchmark keeps the 100 gain.
    book = [
        {"as_of": _day(0), "net_invested": 1000.0},
        {
            "as_of": _day(1),
            "net_invested": -100.0,
        },  # sold 1100 of value: net = 1000 - 1100
    ]
    res = book_math.index_units(book, {_day(0): 100.0, _day(1): 110.0})
    assert res["points"][0] == pytest.approx(0.0)
    # units 10 -> -1100/110 = -10 -> 0 units; value 0; pnl = 0 - (-100) = +100
    assert res["points"][1] == pytest.approx(100.0)


def test_index_units_stale_benchmark_stops_and_alarms():
    book = [{"as_of": _day(i), "net_invested": 100.0} for i in range(6)]
    res = book_math.index_units(book, {_day(0): 10.0, _day(1): 11.0})
    assert res["points"][2:] == [None, None, None, None]  # never flatlines
    assert res["sessions_behind"] == 4 and res["stale"] is True
    assert res["last_date"] == _day(1)


def test_index_units_late_start_defers_flows():
    book = [
        {"as_of": _day(0), "net_invested": 100.0},
        {"as_of": _day(1), "net_invested": 300.0},
    ]
    res = book_math.index_units(book, {_day(1): 50.0})
    assert res["points"] == [None, pytest.approx(0.0)]


def test_index_units_property_constant_growth_matches_return():
    rng = random.Random(7)
    for _ in range(50):
        n = rng.randint(2, 30)
        nets, total = [], 0.0
        for _i in range(n):
            total += rng.uniform(0, 1000)  # buys only
            nets.append(total)
        book = [{"as_of": _day(i), "net_invested": v} for i, v in enumerate(nets)]
        # index constant until the last day, then +5% -> pnl = 5% of all units' value
        bench = {_day(i): 100.0 for i in range(n - 1)}
        bench[_day(n - 1)] = 105.0
        res = book_math.index_units(book, bench)
        last_flow = nets[-1] - nets[-2] if n > 1 else nets[-1]
        expected = (nets[-1] - last_flow) * 0.05
        assert res["points"][-1] == pytest.approx(expected, rel=1e-9, abs=1e-6)


def test_insights_unpriced_leaves_cost_and_value():
    pos = [
        {"symbol": "AAA", "quantity": 10, "invested": 1000, "price": 120},
        {"symbol": "AAA", "quantity": 5, "invested": 500, "price": 120},
        {"symbol": "BBB", "quantity": 1, "invested": 9000, "price": None},  # R6
        {"symbol": "CCC", "quantity": 10, "invested": 1000, "price": 80},
    ]
    ins = book_math.book_insights(pos, {"CCC": 9, "AAA": 2})
    assert ins["unique_stocks"] == 3
    assert ins["unpriced_symbols"] == ["BBB"]
    assert ins["most_invested"] == {"symbol": "AAA", "value": 1500}
    assert ins["top_holding"] == {"symbol": "AAA", "value": 1800}
    assert ins["best_performer"]["symbol"] == "AAA"
    assert ins["best_performer"]["value"] == pytest.approx(0.2)  # decimal (R12)
    assert ins["worst_performer"]["value"] == pytest.approx(-0.2)
    assert ins["most_traded"] == {"symbol": "CCC", "value": 9}


def test_insights_empty_book():
    ins = book_math.book_insights([], {})
    assert ins["most_invested"] is None and ins["unique_stocks"] == 0


def test_totals_sum_clients_and_return_on_capital_deployed():
    roster = [
        {
            "market_value": 110,
            "capital_deployed": 100,
            "current_invested": 100,
            "realized_pnl": 0,
            "unrealized_pnl": 10,
            "total_pnl": 10,
        },
        {
            "market_value": None,
            "capital_deployed": None,
            "total_pnl": None,
        },  # not computed yet
        {
            "market_value": 0,
            "capital_deployed": 100,
            "current_invested": 0,
            "realized_pnl": -10,
            "unrealized_pnl": 0,
            "total_pnl": -10,
        },
    ]
    t = book_math.book_totals(roster)
    assert t["client_count"] == 3
    assert t["total_pnl"] == 0 and t["return_on_capital"] == 0  # 0 is a value (R12)
    assert book_math.book_totals([])["return_on_capital"] is None


def test_client_returns_rebased_and_skip_bad_nav():
    a, b = uuid4(), uuid4()
    rows = [
        {"client_id": a, "name": "Zed", "as_of": _day(0), "nav": 100.0},
        {"client_id": a, "name": "Zed", "as_of": _day(1), "nav": 110.0},
        {"client_id": b, "name": "Amy", "as_of": _day(0), "nav": 0.0},  # R16 data error
        {"client_id": b, "name": "Amy", "as_of": _day(1), "nav": 50.0},
        {"client_id": b, "name": "Amy", "as_of": _day(2), "nav": 45.0},
    ]
    out = book_math.client_returns(rows)
    assert [c["name"] for c in out] == ["Amy", "Zed"]
    assert out[0]["series"][0]["value"] == 0.0
    assert out[0]["series"][1]["value"] == pytest.approx(-0.1)
    assert out[1]["series"][1]["value"] == pytest.approx(0.1)
