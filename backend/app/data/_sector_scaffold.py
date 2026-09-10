"""Shared builders for the newer research sectors.

These sectors were added with validated NSE rosters (every ticker checked against Angel's
scrip master) and domain-specific sub-industry `segment` labels, but WITHOUT the
hand-researched quarterly KPIs yet — those fields are present and set to None, ready to be
filled in the KPI-research phase (see RESEARCH_TODO.md). Live market data (price, momentum,
RSI, levels) flows for these immediately via market_data; only the operational/fundamental
KPI *values* are pending.
"""
from __future__ import annotations


def covered(ticker: str, name: str, segment: str = "", **kpis) -> dict:
    """A 'covered' stock. KPI fields default to None (ready for research) and can be filled
    via kwargs — e.g. covered("TATASTEEL", "Tata Steel", "Ferrous", market_cap_cr=235376,
    pe_label="~21x", revenue_cr=239756, revenue_yoy_pct=3.3, ebitda_margin_pct=15.1, ...).
    Field names match the hotels/auto schema the screener's _fundamentals() reads.
    Fundamental values here are FY26 (consolidated) snapshots compiled from Tijori Finance."""
    base = {
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
    base.update(kpis)
    return base


def roster(ticker: str, name: str, segment: str = "", note: str = "", **kpis) -> dict:
    """A 'roster' stock. Profile by default; KPI fields (same schema as covered()) default to
    None and can be filled via kwargs so roster names can also carry FY26 fundamentals."""
    base = {
        "ticker": ticker, "exchange": "NSE", "name": name, "segment": segment,
        "model": None, "scale": "", "cap_label": "", "note": note,
        "market_cap_cr": None, "pe_label": None,
        "revenue_cr": None, "revenue_yoy_pct": None,
        "ebitda_cr": None, "ebitda_margin_pct": None,
        "pat_cr": None, "pat_yoy_pct": None, "pat_yoy_label": None,
    }
    base.update(kpis)
    return base


def finalize(covered_list: list[dict], roster_list: list[dict]) -> tuple[list[str], dict]:
    """Return (ALL_TICKERS, EXCHANGES) for a sector, matching the existing modules."""
    all_items = covered_list + roster_list
    tickers = [c["ticker"] for c in all_items]
    exchanges = {c["ticker"]: c["exchange"] for c in all_items}
    return tickers, exchanges
