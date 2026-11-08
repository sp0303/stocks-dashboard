"""Money-weighted XIRR calculation adhering to Rule R4."""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple


def _xirr_npv(rate: float, dates: List[date], amounts: List[float], t0: date) -> float:
    """Calculates Net Present Value for a given annual rate."""
    val = 0.0
    for d, amt in zip(dates, amounts):
        dt = (d - t0).days / 365.25
        val += amt / ((1.0 + rate) ** dt)
    return val


def _xirr_derivative(rate: float, dates: List[date], amounts: List[float], t0: date) -> float:
    """Derivative of NPV with respect to rate."""
    d_val = 0.0
    for d, amt in zip(dates, amounts):
        dt = (d - t0).days / 365.25
        d_val -= dt * amt / ((1.0 + rate) ** (dt + 1.0))
    return d_val


def calculate_xirr(
    cash_flows: List[Tuple[date, float]],
    terminal_value: float,
    as_of: date,
    guess: float = 0.1,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> Optional[float]:
    """Computes annualized internal rate of return (XIRR) per Rule R4.

    Cash flows: list of (date, amount) where outflows (investments/buys) are NEGATIVE
                and inflows (sells/dividends) are POSITIVE.
    Terminal value: positive market value of portfolio on `as_of`.

    Rule R4 Policy: Returns None if span is < 365 days or solver fails to converge.
    """
    if not cash_flows:
        return None

    # Filter out zero amounts
    valid_flows = [(d, amt) for d, amt in cash_flows if abs(amt) > 1e-4]
    if not valid_flows:
        return None

    # Append terminal flow
    all_flows = sorted(valid_flows + [(as_of, terminal_value)], key=lambda x: x[0])
    dates = [x[0] for x in all_flows]
    amounts = [x[1] for x in all_flows]

    t0 = dates[0]
    total_days = (dates[-1] - t0).days

    # Rule R4: Suppressed under 365 days
    if total_days < 365:
        return None

    # Check for sign change (both positive and negative cash flows must exist)
    has_pos = any(a > 0 for a in amounts)
    has_neg = any(a < 0 for a in amounts)
    if not (has_pos and has_neg):
        return None

    # Newton-Raphson method
    rate = guess
    for _ in range(max_iter):
        if rate <= -0.999:
            rate = -0.99
        npv = _xirr_npv(rate, dates, amounts, t0)
        d_npv = _xirr_derivative(rate, dates, amounts, t0)

        if abs(d_npv) < 1e-10:
            break

        next_rate = rate - (npv / d_npv)
        if abs(next_rate - rate) < tol:
            return next_rate
        rate = next_rate

    # Fallback to Bisection search if Newton-Raphson did not converge
    low = -0.99
    high = 10.0  # 1000%
    npv_low = _xirr_npv(low, dates, amounts, t0)
    npv_high = _xirr_npv(high, dates, amounts, t0)

    if npv_low * npv_high > 0:
        return None  # No root in bracket

    for _ in range(100):
        mid = (low + high) / 2.0
        npv_mid = _xirr_npv(mid, dates, amounts, t0)
        if abs(npv_mid) < tol or (high - low) / 2.0 < tol:
            return mid
        if npv_low * npv_mid < 0:
            high = mid
            npv_high = npv_mid
        else:
            low = mid
            npv_low = npv_mid

    return None
