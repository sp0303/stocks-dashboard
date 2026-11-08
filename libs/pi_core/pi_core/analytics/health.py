"""Portfolio health score (0-100) with alerts -- v1's rules, with v1's unit bug fixed.

R12: every threshold is written in the metric's own unit. Weights, volatility and
drawdowns are DECIMALS (0.25 == 25 %); v1 compared them to 25 / -30, so no
volatility or drawdown penalty could ever fire. A missing metric adds no penalty
and is listed in ``missing`` instead of being treated as 0. Pure.
"""

from __future__ import annotations

from typing import Any

# (metric, comparison, threshold, penalty, alert code or None). First match per metric wins.
RULES: tuple[tuple[str, str, float, int, str | None], ...] = (
    ("top10_weight", ">", 0.70, 20, "HIGH_CONCENTRATION"),
    ("top10_weight", ">", 0.60, 10, None),
    ("largest_sector_weight", ">", 0.40, 15, "SECTOR_OVERWEIGHT"),
    ("largest_sector_weight", ">", 0.30, 5, None),
    ("volatility", ">", 0.25, 10, "HIGH_VOLATILITY"),
    ("volatility", ">", 0.20, 5, None),
    ("max_drawdown", "<", -0.30, 15, "DEEP_DRAWDOWN"),
    ("max_drawdown", "<", -0.20, 10, None),
    ("current_drawdown", "<", -0.15, 10, "IN_DRAWDOWN"),
    ("current_drawdown", "<", -0.10, 5, None),
)
ALERT_TEXT = {
    "HIGH_CONCENTRATION": "Top 10 holdings exceed 70% of the book",
    "SECTOR_OVERWEIGHT": "One sector exceeds 40% of the book",
    "HIGH_VOLATILITY": "Annualised volatility above 25%",
    "DEEP_DRAWDOWN": "Maximum drawdown deeper than 30%",
    "IN_DRAWDOWN": "Currently more than 15% below the peak",
}
METRICS = ("top10_weight", "largest_sector_weight", "volatility", "max_drawdown", "current_drawdown")


def _hit(value: float, op: str, threshold: float) -> bool:
    return value > threshold if op == ">" else value < threshold


def health_score(inputs: dict[str, float | None]) -> dict[str, Any]:
    """``inputs`` holds the five METRICS (decimals or None). Returns score, alerts, penalties."""
    score = 100
    penalties: list[dict[str, Any]] = []
    alerts: list[dict[str, str]] = []
    done: set[str] = set()
    for metric, op, threshold, penalty, code in RULES:
        value = inputs.get(metric)
        if metric in done or value is None or not _hit(value, op, threshold):
            continue
        done.add(metric)
        score -= penalty
        penalties.append({"metric": metric, "value": value, "threshold": threshold, "penalty": penalty})
        if code:
            alerts.append({"code": code, "message": ALERT_TEXT[code]})
    return {
        "score": max(0, min(100, score)),
        "alerts": alerts,
        "penalties": penalties,
        "missing": [m for m in METRICS if inputs.get(m) is None],
    }
