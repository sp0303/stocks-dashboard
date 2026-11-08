"""Playbook rows + CSV (R14 round trip), benchmark index units (R10) and stale alarm."""

import csv
import io
from datetime import date, timedelta

from pi_core.analytics.benchmark_compare import (
    benchmark_track,
    beta_alpha,
    nav_points,
    portfolio_returns,
)
from pi_core.analytics.closed_trades import closed_trades_from_matches
from pi_core.analytics.playbook import CSV_COLUMNS, playbook_by_stock, playbook_csv
from pi_core.engine.matching import match_trades_fifo
from pi_core.models import Side, Trade

D0 = date(2025, 1, 6)


def _rows():
    trades = [
        Trade("1", D0, "AAA", "NSE", Side.BUY, 10, 100), Trade("2", D0 + timedelta(5), "AAA", "NSE", Side.SELL, 10, 110),
        Trade("3", D0, "AAA", "NSE", Side.BUY, 30, 200), Trade("4", D0 + timedelta(9), "AAA", "NSE", Side.SELL, 30, 190),
        Trade("5", D0, "=EVIL", "NSE", Side.BUY, 1, 10), Trade("6", D0 + timedelta(1), "=EVIL", "NSE", Side.SELL, 1, 12),
    ]
    matched, _, _ = match_trades_fifo(trades)
    return playbook_by_stock(closed_trades_from_matches(matched), {"1": "breakout", "3": "breakout", "5": "+tip"}, "delivery")


def test_playbook_weighted_averages():
    rows = _rows()
    aaa = next(r for r in rows if r["symbol"] == "AAA")
    assert aaa["trades"] == 2 and aaa["quantity"] == 40
    assert aaa["avg_buy_price"] == (1000 + 6000) / 40
    assert aaa["avg_sell_price"] == (1100 + 5700) / 40
    assert aaa["pnl"] == 100 - 300
    assert aaa["avg_days"] == (10 * 5 + 30 * 9) / 40
    assert aaa["reason"] == "breakout"
    assert rows[0]["symbol"] == "=EVIL"  # sorted by P&L desc


def test_csv_round_trips_and_guards_formulas():
    rows = _rows()
    parsed = list(csv.reader(io.StringIO(playbook_csv(rows))))
    assert parsed[0] == [label for _, label in CSV_COLUMNS]
    assert len(parsed) == len(rows) + 1
    evil = parsed[1]
    assert evil[1] == "'=EVIL" and evil[-1] == "'+tip"
    aaa = parsed[2]
    assert float(aaa[8]) == rows[1]["pnl"] and float(aaa[5]) == rows[1]["avg_buy_price"]  # full precision


def _days(n):
    return [D0 + timedelta(i) for i in range(n)]


def test_index_units_on_net_invested_baseline_r10():
    days = _days(4)
    # buy 1000 at 100; then sell 500 at 120 (full exit leaves gain on the index too).
    ni = [1000, 1000, 500, 500]
    levels = dict(zip(days, [100, 110, 120, 120]))
    t = benchmark_track(days, ni, levels)
    # units 10 -> 10 - 500/120; value at 120: 1200 - 500 = 700; pnl = 700 - 500 = 200
    assert t["pnl"][0] == 0 and abs(t["pnl"][1] - 100) < 1e-9
    assert abs(t["pnl"][3] - 200) < 1e-9
    assert t["stale"] is False and t["sessions_behind"] == 0
    assert abs(t["index_return"] - 0.2) < 1e-12


def test_stale_benchmark_stops_and_alarms_never_flatlines():
    days = _days(8)
    levels = dict(zip(days[:3], [100, 101, 102]))
    t = benchmark_track(days, [1000] * 8, levels)
    assert t["pnl"][3] is not None and t["pnl"][4] is not None  # carried <= 2 sessions
    assert t["pnl"][5:] == [None, None, None]
    assert t["stale"] is True and t["sessions_behind"] == 5
    assert t["last_index_date"] == days[2].isoformat()


def test_missing_benchmark_is_stale():
    t = benchmark_track(_days(3), [1, 1, 1], {})
    assert t["stale"] and t["pnl"] == [None, None, None]


def test_beta_of_portfolio_equal_to_index_is_one():
    days = _days(30)
    levels, navs, rets, lvl, nav = {}, [], [], 100.0, 100.0
    for i, d in enumerate(days):
        r = 0.01 if i % 3 else -0.012
        if i:
            lvl *= 1 + r
            nav *= 1 + r
        levels[d] = lvl
        navs.append(nav)
        rets.append(r if i else 0.0)
    ba = beta_alpha(nav_points(days, navs, rets), levels)
    assert abs(ba["beta"] - 1.0) < 1e-9
    assert portfolio_returns(nav_points(days, navs, rets))["cagr"] is None  # R3: < 365 days
