"""Unit tests for Capital, Returns, Risk, and Drawdown metrics (Rules R1, R3, R11)."""

from datetime import date
import pytest

from pi_core.metrics.capital import calculate_capital_metrics
from pi_core.metrics.drawdown import calculate_drawdown_series
from pi_core.metrics.returns import calculate_returns
from pi_core.metrics.risk import calculate_risk_metrics
from pi_core.models import BenchmarkPoint, DailySnapshot, NAVPoint


def test_capital_metrics_return_on_capital_rule_r1():
    """Verify Return on Capital = Total PnL / Capital Deployed."""
    snapshots = [
        DailySnapshot(
            snapshot_date=date(2024, 1, 1),
            open_cost=50000.0,
            market_value=60000.0,
            realized_pnl_cumulative=15000.0,
            unrealized_pnl=10000.0,
            capital_deployed=100000.0,
            net_cash_flow=50000.0,
            open_positions_count=2,
        )
    ]

    metrics = calculate_capital_metrics(snapshots)
    assert metrics is not None
    assert metrics.capital_deployed == 100000.0
    assert metrics.current_invested == 50000.0
    assert metrics.realized_pnl == 15000.0
    assert metrics.unrealized_pnl == 10000.0
    assert metrics.total_pnl == 25000.0
    assert metrics.return_on_capital == pytest.approx(0.25)  # 25.0% return on capital


def test_returns_cagr_suppression_rule_r3():
    """Verify CAGR is None when portfolio span is less than 365 days."""
    # 180 days span
    nav_short = [
        NAVPoint(date(2024, 1, 1), 100.0, 0.0, 10000.0, 10000.0, 0.0),
        NAVPoint(date(2024, 7, 1), 120.0, 0.2, 10000.0, 12000.0, 0.0),
    ]

    res_short = calculate_returns(nav_short)
    assert res_short is not None
    assert res_short.total_return == pytest.approx(0.20)
    assert res_short.cagr is None  # Suppressed!
    assert res_short.is_annualized is False

    # 400 days span (exceeds 365 days) -> CAGR calculated
    nav_long = [
        NAVPoint(date(2024, 1, 1), 100.0, 0.0, 10000.0, 10000.0, 0.0),
        NAVPoint(date(2025, 2, 5), 120.0, 0.01, 10000.0, 12000.0, 0.0),
    ]

    res_long = calculate_returns(nav_long)
    assert res_long is not None
    assert res_long.cagr is not None
    assert res_long.is_annualized is True
    assert 0.15 < res_long.cagr < 0.20


def test_drawdown_calculation_and_recovery():
    """Verify max drawdown bounds and recovery peak tracking."""
    # NAV starts 100 -> peaks 120 -> drops to 90 (-25% from peak 120) -> recovers to 110
    nav_series = [
        NAVPoint(date(2024, 1, 1), 100.0, 0.0, 10000.0, 10000.0, 0.0),
        NAVPoint(date(2024, 1, 2), 120.0, 0.2, 10000.0, 12000.0, 0.0),
        NAVPoint(date(2024, 1, 3), 90.0, -0.25, 10000.0, 9000.0, 0.0),
        NAVPoint(date(2024, 1, 4), 110.0, 0.22, 10000.0, 11000.0, 0.0),
    ]

    dd = calculate_drawdown_series(nav_series)
    assert dd is not None
    # Peak was 120, trough was 90: drop = (90 - 120)/120 = -0.25 (-25%)
    assert dd.max_drawdown == pytest.approx(-0.25)
    assert dd.peak_date == date(2024, 1, 2)
    assert dd.trough_date == date(2024, 1, 3)
    # Current drawdown from peak 120 is (110 - 120)/120 = -0.0833
    assert dd.current_drawdown == pytest.approx((110.0 - 120.0) / 120.0)


def test_risk_metrics_volatility_and_sharpe():
    """Verify annualized volatility and Sharpe ratio on daily returns."""
    nav_series = [
        NAVPoint(date(2024, 1, 1), 100.0, 0.0, 1000.0, 1000.0, 0.0),
        NAVPoint(date(2024, 1, 2), 101.0, 0.01, 1000.0, 1010.0, 0.0),
        NAVPoint(date(2024, 1, 3), 102.0, 0.0099, 1000.0, 1020.0, 0.0),
        NAVPoint(date(2024, 1, 4), 101.5, -0.0049, 1000.0, 1015.0, 0.0),
        NAVPoint(date(2024, 1, 5), 103.0, 0.0147, 1000.0, 1030.0, 0.0),
    ]

    risk = calculate_risk_metrics(nav_series)
    assert risk.annualized_volatility is not None
    assert risk.annualized_volatility > 0.0
    assert risk.sharpe_ratio is not None
    assert risk.observations_count == 4
