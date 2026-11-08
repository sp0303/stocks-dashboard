"""Allocation / concentration (R6 unpriced, R1 peak not recycled legs) and health (R12 units)."""

import random
from datetime import date, timedelta

from pi_core.analytics.allocation import calculate_symbol_allocation
from pi_core.analytics.exposure import (
    HoldingValue,
    SecurityClass,
    allocation,
    allocation_matrix,
    concentration_summary,
    unpriced,
)
from pi_core.analytics.health import health_score
from pi_core.models import Side, Trade

CLS = {("A", "NSE"): SecurityClass("IT", "Large", "Equity"), ("B", "NSE"): SecurityClass("Bank", "Mid", "Equity")}


def _h(sym, cost, mv):
    return HoldingValue(sym, "NSE", 1, cost, mv)


def test_current_basis_excludes_unpriced_r6():
    hs = [_h("A", 100, 300), _h("B", 100, 100), _h("C", 500, None)]
    a = allocation(hs, {}, CLS, "sector", "current")
    assert a["total"] == 400
    assert [(b["key"], b["weight"]) for b in a["buckets"]] == [("IT", 0.75), ("Bank", 0.25)]
    assert unpriced(hs) == {"count": 1, "open_cost": 500, "symbols": ["C"]}


def test_invested_basis_uses_peak_capital_not_recycled_legs():
    d = date(2025, 1, 1)
    # Z traded 3 times with 1000 recycled each time: peak capital 1000, not 3000.
    trades = []
    for k in range(3):
        trades += [Trade(f"b{k}", d + timedelta(k * 10), "Z", "NSE", Side.BUY, 10, 100),
                   Trade(f"s{k}", d + timedelta(k * 10 + 5), "Z", "NSE", Side.SELL, 10, 100)]
    peaks = {(a.symbol, a.exchange): a.peak_capital for a in calculate_symbol_allocation(trades, 1.0)}
    assert peaks[("Z", "NSE")] == 1000
    a = allocation([_h("A", 1000, 1200)], peaks, CLS, "stock", "invested")
    assert a["total"] == 2000 and {b["key"]: b["weight"] for b in a["buckets"]} == {"A": 0.5, "Z": 0.5}
    assert a["unclassified"]["count"] == 0
    s = allocation([_h("A", 1000, 1200)], peaks, CLS, "sector", "invested")
    assert s["unclassified"] == {"count": 1, "value": 1000, "weight": 0.5, "symbols": ["Z"]}


def test_weights_sum_to_one_property():
    rng = random.Random(3)
    for _ in range(100):
        hs = [_h(f"S{i}", rng.uniform(1, 100), rng.choice([None, rng.uniform(1, 100)])) for i in range(rng.randint(0, 15))]
        for dims in allocation_matrix(hs, {("X", "NSE"): 50.0}, CLS).values():
            for a in dims.values():
                if a["total"] > 0:
                    assert abs(sum(b["weight"] for b in a["buckets"]) - 1) < 1e-9


def test_concentration_summary():
    hs = [_h(f"S{i}", 1, float(i + 1)) for i in range(12)] + [_h("U", 5, None)]
    c = concentration_summary(hs, {})
    total = sum(range(1, 13))
    assert c["holdings_count"] == 12
    assert abs(c["top5_weight"] - (12 + 11 + 10 + 9 + 8) / total) < 1e-12
    assert c["largest_stock"]["symbol"] == "S11"
    assert c["largest_sector"] == {"key": "Unclassified", "weight": 1.0}
    assert concentration_summary([], {})["top10_weight"] is None


def test_health_thresholds_are_decimals_r12():
    h = health_score({"top10_weight": 0.5, "largest_sector_weight": 0.2, "volatility": 0.26,
                      "max_drawdown": -0.31, "current_drawdown": -0.12})
    assert h["score"] == 100 - 10 - 15 - 5
    assert {a["code"] for a in h["alerts"]} == {"HIGH_VOLATILITY", "DEEP_DRAWDOWN"}


def test_health_missing_is_not_zero_and_zero_is_value():
    h = health_score({"top10_weight": 0.0, "largest_sector_weight": None, "volatility": None,
                      "max_drawdown": 0.0, "current_drawdown": 0.0})
    assert h["score"] == 100
    assert h["missing"] == ["largest_sector_weight", "volatility"]
