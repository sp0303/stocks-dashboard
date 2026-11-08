"""Unit tests for Time-Weighted Return (TWR) NAV calculation (Rules R2, R16)."""

from datetime import date
import pytest

from pi_core.models import DailySnapshot, Side, Trade
from pi_core.series.twr import calculate_twr_series


def test_twr_cash_flow_neutrality():
    """Property test: Adding deposits/withdrawals with constant prices produces 0% return and flat NAV."""
    # Day 1: Invest 10,000 at price 100 (MV = 10,000, Flow = 10,000)
    # Day 2: Deposit another 10,000 at price 100 (MV = 20,000, Flow = 10,000)
    # Stock price never moved -> TWR daily returns must be 0.0 and NAV must stay 100.0
    snapshots = [
        DailySnapshot(date(2024, 1, 1), 10000.0, 10000.0, 0.0, 0.0, 10000.0, 10000.0, 1),
        DailySnapshot(date(2024, 1, 2), 20000.0, 20000.0, 0.0, 0.0, 20000.0, 10000.0, 1),
    ]

    trades = [
        Trade("T1", date(2024, 1, 1), "XYZ", "NSE", Side.BUY, 100.0, 100.0),
        Trade("T2", date(2024, 1, 2), "XYZ", "NSE", Side.BUY, 100.0, 100.0),
    ]

    def close_lookup(sym, exch, d):
        return 100.0

    nav_points, warnings = calculate_twr_series(snapshots, trades, close_lookup)

    assert len(nav_points) == 2
    assert nav_points[0].nav == 100.0
    assert nav_points[1].nav == pytest.approx(100.0)
    assert nav_points[1].daily_return == pytest.approx(0.0)


def test_twr_full_exit_is_not_a_loss():
    """Property test: A complete sale to cash is not treated as a loss."""
    # Day 1: Bought 100 @ 100 (MV = 10,000)
    # Day 2: Price rose to 110 (MV = 11,000) -> 10% gain
    # Day 3: Sold all @ 110 (MV = 0, Flow = -11,000) -> Return must be 0% on day 3, NAV stays flat
    snapshots = [
        DailySnapshot(date(2024, 1, 1), 10000.0, 10000.0, 0.0, 0.0, 10000.0, 10000.0, 1),
        DailySnapshot(date(2024, 1, 2), 10000.0, 11000.0, 0.0, 1000.0, 10000.0, 0.0, 1),
        DailySnapshot(date(2024, 1, 3), 0.0, 0.0, 1000.0, 0.0, 10000.0, -11000.0, 0),
    ]

    trades = [
        Trade("T1", date(2024, 1, 1), "ABC", "NSE", Side.BUY, 100.0, 100.0),
        Trade("T2", date(2024, 1, 3), "ABC", "NSE", Side.SELL, 100.0, 110.0),
    ]

    def close_lookup(sym, exch, d):
        if d == date(2024, 1, 1):
            return 100.0
        return 110.0

    nav_points, warnings = calculate_twr_series(snapshots, trades, close_lookup)

    assert len(nav_points) == 3
    # Day 2 gained 10%: NAV = 110.0
    assert nav_points[1].nav == pytest.approx(110.0)
    # Day 3 exited completely: NAV remains 110.0, NOT 0 or a crash!
    assert nav_points[2].nav == pytest.approx(110.0)


def test_twr_small_base_protection_rule_r16():
    """Sanity guard R16: If capital base < ₹1, daily return is 0."""
    snapshots = [
        DailySnapshot(date(2024, 1, 1), 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 1),
        DailySnapshot(date(2024, 1, 2), 0.5, 0.5, 0.0, 0.0, 0.5, 0.0, 1),
    ]

    nav_points, warnings = calculate_twr_series(snapshots, [])
    assert nav_points[1].daily_return == 0.0
    assert nav_points[1].nav == 100.0
