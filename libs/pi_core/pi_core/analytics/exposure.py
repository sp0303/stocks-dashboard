"""Allocation buckets and concentration for one client's delivery book.

Two bases, as in v1:
  * ``current``  -- open holdings weighted by market value. Unpriced holdings leave
                    the denominator entirely and are reported (R6), never valued at cost.
  * ``invested`` -- every stock ever held: open holdings at open cost plus closed
                    stocks at the PEAK capital they ever required (never the sum of
                    recycled buy legs, R1/R5).
Weights are decimals (R12). Pure: no I/O, no clock.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pi_core.analytics.concentration import calculate_concentration

UNCLASSIFIED = "Unclassified"
DIMENSIONS = ("sector", "cap", "asset", "stock")
Key = tuple[str, str]


@dataclass(frozen=True)
class HoldingValue:
    symbol: str
    exchange: str
    quantity: float
    open_cost: float
    market_value: float | None  # None = unpriced (R6)


@dataclass(frozen=True)
class SecurityClass:
    sector: str | None = None
    cap: str | None = None
    asset_class: str | None = None


def _label(key: Key, dim: str, classes: Mapping[Key, SecurityClass]) -> str:
    if dim == "stock":
        return key[0]
    c = classes.get(key) or SecurityClass()
    raw = {"sector": c.sector, "cap": c.cap, "asset": c.asset_class}[dim]
    return raw.strip() if raw and raw.strip() else UNCLASSIFIED


def _basis_values(
    basis: str, holdings: Sequence[HoldingValue], closed_peaks: Mapping[Key, float]
) -> dict[Key, float]:
    if basis == "current":
        return {
            (h.symbol, h.exchange): h.market_value
            for h in holdings
            if h.market_value is not None and h.market_value > 0
        }
    values = {(h.symbol, h.exchange): h.open_cost for h in holdings if h.open_cost > 0}
    for key, peak in closed_peaks.items():
        if key not in values and peak > 0:
            values[key] = peak
    return values


def allocation(
    holdings: Sequence[HoldingValue],
    closed_peaks: Mapping[Key, float],
    classes: Mapping[Key, SecurityClass],
    dim: str,
    basis: str,
) -> dict[str, Any]:
    """Buckets for one dimension and basis, with the unclassified share called out."""
    values = _basis_values(basis, holdings, closed_peaks)
    total = sum(values.values())
    buckets: dict[str, float] = defaultdict(float)
    unclassified: list[str] = []
    for key, v in values.items():
        label = _label(key, dim, classes)
        buckets[label] += v
        if label == UNCLASSIFIED:
            unclassified.append(key[0])
    rows = [
        {"key": k, "value": v, "weight": v / total if total > 0 else None}
        for k, v in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    un_value = buckets.get(UNCLASSIFIED, 0.0)
    return {
        "total": total,
        "buckets": rows,
        "unclassified": {
            "count": len(unclassified),
            "value": un_value,
            "weight": un_value / total if total > 0 else None,
            "symbols": sorted(unclassified),
        },
    }


def unpriced(holdings: Sequence[HoldingValue]) -> dict[str, Any]:
    rows = [h for h in holdings if h.market_value is None]
    return {
        "count": len(rows),
        "open_cost": sum(h.open_cost for h in rows),
        "symbols": sorted(h.symbol for h in rows),
    }


def allocation_matrix(
    holdings: Sequence[HoldingValue],
    closed_peaks: Mapping[Key, float],
    classes: Mapping[Key, SecurityClass],
) -> dict[str, Any]:
    """Every (basis, dimension) pair, so the UI toggles without another request."""
    return {
        basis: {d: allocation(holdings, closed_peaks, classes, d, basis) for d in DIMENSIONS}
        for basis in ("current", "invested")
    }


def concentration_summary(
    holdings: Sequence[HoldingValue], classes: Mapping[Key, SecurityClass]
) -> dict[str, Any]:
    """Top-5 / top-10 weight, largest stock and largest sector, by market value (priced only)."""
    mv = {
        (h.symbol, h.exchange): h.market_value
        for h in holdings
        if h.market_value is not None and h.market_value > 0
    }
    base = calculate_concentration(mv)
    total = sum(mv.values())
    largest_stock = None
    if mv:
        key, v = max(mv.items(), key=lambda kv: (kv[1], kv[0]))
        largest_stock = {"symbol": key[0], "exchange": key[1], "weight": v / total}
    sectors = allocation(holdings, {}, classes, "sector", "current")["buckets"]
    largest_sector = {"key": sectors[0]["key"], "weight": sectors[0]["weight"]} if sectors else None
    return {
        "holdings_count": base.holdings_count,
        "top5_weight": base.top_5_weight if mv else None,
        "top10_weight": base.top_10_weight if mv else None,
        "herfindahl": base.herfindahl_index if mv else None,
        "largest_stock": largest_stock,
        "largest_sector": largest_sector,
    }
