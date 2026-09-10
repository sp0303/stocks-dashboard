"""Shared builders for the newer research sectors.

These sectors were added with validated NSE rosters (every ticker checked against Angel's
scrip master) and domain-specific sub-industry `segment` labels, but WITHOUT the
hand-researched quarterly KPIs yet — those fields are present and set to None, ready to be
filled in the KPI-research phase (see RESEARCH_TODO.md). Live market data (price, momentum,
RSI, levels) flows for these immediately via market_data; only the operational/fundamental
KPI *values* are pending.
"""
from __future__ import annotations


def covered(ticker: str, name: str, segment: str = "") -> dict:
    """A 'covered' stock: full KPI schema present but unfilled (None), ready for research.
    Field names match the hotels/auto schema the screener's _fundamentals() reads."""
    return {
        "ticker": ticker, "exchange": "NSE", "name": name, "segment": segment,
        "model": None,
        "market_cap_cr": None, "pe_label": None,
        "revenue_cr": None, "revenue_yoy_pct": None,
        "ebitda_cr": None, "ebitda_margin_pct": None, "ebitda_margin_delta_bps": None,
        "pat_cr": None, "pat_yoy_pct": None, "pat_yoy_label": None,
        "leverage_status": None, "leverage_label": None,
        "driver": None, "driver_note": None, "note": None,
        "segments": [],
    }


def roster(ticker: str, name: str, segment: str = "", note: str = "") -> dict:
    """A 'roster' stock: profile only (no KPIs), same shape as the existing sector rosters."""
    return {
        "ticker": ticker, "exchange": "NSE", "name": name, "segment": segment,
        "model": None, "scale": "", "cap_label": "", "note": note,
    }


def finalize(covered_list: list[dict], roster_list: list[dict]) -> tuple[list[str], dict]:
    """Return (ALL_TICKERS, EXCHANGES) for a sector, matching the existing modules."""
    all_items = covered_list + roster_list
    tickers = [c["ticker"] for c in all_items]
    exchanges = {c["ticker"]: c["exchange"] for c in all_items}
    return tickers, exchanges
