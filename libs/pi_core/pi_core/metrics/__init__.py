"""Performance, Risk, and Capital Metrics adhering to Rules R1, R3, R4, R11."""

from pi_core.metrics.capital import calculate_capital_metrics, CapitalMetrics
from pi_core.metrics.drawdown import calculate_drawdown_series, DrawdownSummary
from pi_core.metrics.returns import calculate_returns, ReturnsSummary
from pi_core.metrics.risk import calculate_risk_metrics, RiskSummary
from pi_core.metrics.xirr import calculate_xirr

__all__ = [
    "calculate_capital_metrics",
    "CapitalMetrics",
    "calculate_drawdown_series",
    "DrawdownSummary",
    "calculate_returns",
    "ReturnsSummary",
    "calculate_risk_metrics",
    "RiskSummary",
    "calculate_xirr",
]
