"""Unit tests for XIRR calculation and policy suppression (Rule R4)."""

from datetime import date
import pytest

from pi_core.metrics.xirr import calculate_xirr


def test_xirr_exact_doubling_in_one_year():
    """Verify XIRR equals 100% when investment doubles in exactly one year."""
    # Invest 10,000 on 2023-01-01, worth 20,000 on 2024-01-01
    flows = [(date(2023, 1, 1), -10000.0)]
    terminal_val = 20000.0
    as_of = date(2024, 1, 1)

    irr = calculate_xirr(flows, terminal_val, as_of)
    assert irr is not None
    assert irr == pytest.approx(1.0, abs=0.01)  # ~100% annualized


def test_xirr_suppression_under_365_days_rule_r4():
    """Rule R4: XIRR is suppressed (returns None) if span is under 365 days."""
    flows = [(date(2024, 1, 1), -10000.0)]
    terminal_val = 12000.0
    as_of = date(2024, 6, 1)  # Only 152 days

    irr = calculate_xirr(flows, terminal_val, as_of)
    assert irr is None
