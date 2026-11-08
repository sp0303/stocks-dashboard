"""Portfolio recompute smoke on a small fixture (pi_core pipeline, no DB)."""

from datetime import date
from decimal import Decimal

from pi_workers.portfolio_compute import (
    actions_from_rows,
    build_price_lookup,
    compute_client,
    trades_from_rows,
)

TRADES = [
    {
        "trade_id": 1,
        "trade_date": date(2026, 9, 28),
        "symbol": "AAA",
        "exchange": "NSE",
        "trade_type": "buy",
        "quantity": Decimal(10),
        "price": Decimal(100),
        "charges": None,
        "segment": "EQ",
        "extra": "{}",
    },
    {
        "trade_id": 2,
        "trade_date": date(2026, 9, 30),
        "symbol": "AAA",
        "exchange": "NSE",
        "trade_type": "sell",
        "quantity": Decimal(4),
        "price": Decimal(110),
        "charges": None,
        "segment": "EQ",
        "extra": {},
    },
]
PRICES = [
    ("AAA", "NSE", date(2026, 9, 28), 100.0),
    ("AAA", "NSE", date(2026, 9, 29), 105.0),
    ("AAA", "NSE", date(2026, 9, 30), 110.0),
    ("AAA", "NSE", date(2026, 10, 1), 120.0),
    ("AAA", "BSE", date(2026, 10, 1), 999.0),  # other exchange must never be used (R6)
]
HOLIDAY = date(2026, 10, 2)


def _run():
    return compute_client(
        trades_from_rows(TRADES),
        actions_from_rows([]),
        build_price_lookup(PRICES),
        today=date(2026, 10, 5),
        closed_days={HOLIDAY},
    )


def test_daily_rows_follow_trading_calendar():
    res = _run()
    days = [r[0] for r in res.daily]
    assert days == [
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
        date(2026, 10, 1),
        date(2026, 10, 5),
    ]
    assert HOLIDAY not in days  # R11: closed day from market.trading_calendar


def test_values_positions_and_carry_forward():
    res = _run()
    by_day = {r[0]: r for r in res.daily}
    _as_of, mv, open_cost, net_inv, realized, _base, _ret, nav, unpriced_cost = by_day[
        date(2026, 10, 1)
    ]
    assert unpriced_cost == 0.0  # everything held has a price here (R6: persisted per day)
    assert mv == 720.0 and open_cost == 600.0  # 6 x 120 (NSE, not the BSE 999)
    assert net_inv == 1000.0 - 440.0
    assert realized == 40.0
    assert nav > 100.0
    # 5 Oct: no print -> last close (1 Oct) carried, not dropped to cost
    assert by_day[date(2026, 10, 5)][1] == 720.0
    assert res.positions == [("AAA", "NSE", 6.0, 100.0, 600.0, date(2026, 9, 28))]
    assert res.overview["realized_pnl"] == 40.0
    assert res.obs == len(res.daily)


def test_price_lookup_carry_is_bounded():
    look = build_price_lookup([("X", "NSE", date(2026, 9, 1), 50.0)], max_carry_days=10)
    assert look("X", "NSE", date(2026, 9, 11)) == 50.0
    assert (
        look("X", "NSE", date(2026, 9, 12)) is None
    )  # too old: unpriced, held at cost by pi_core
    assert look("X", "NSE", date(2026, 8, 31)) is None
    # ADR-0009: no BSE close -> the same symbol's NSE close, never an average; own lookup stays strict
    assert look("X", "BSE", date(2026, 9, 2)) == 50.0
    assert look.own("X", "BSE", date(2026, 9, 2)) is None
    assert look("X", "BSE", date(2026, 9, 12)) is None  # the fallback obeys the same carry bound


def test_own_exchange_close_wins_over_the_other_exchange():
    look = build_price_lookup([("X", "NSE", date(2026, 9, 1), 50.0), ("X", "BSE", date(2026, 9, 1), 49.0)])
    assert look("X", "BSE", date(2026, 9, 1)) == 49.0 and look("X", "NSE", date(2026, 9, 1)) == 50.0
