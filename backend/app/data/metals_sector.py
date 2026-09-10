"""Metals & Mining — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
sales volume (tonnes), realisation/tonne, EBITDA/tonne, capacity utilisation, input costs
(coking coal / alumina / ore), net debt & net-debt/EBITDA, export share.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

# FY26 (consolidated) fundamentals compiled from Tijori Finance. Market data (price/
# momentum/RSI) stays live; these are the researched quarterly/annual snapshots.
METALS_COVERED = [
    covered("TATASTEEL", "Tata Steel", "Ferrous (Steel)",
            market_cap_cr=235376, pe_label="~21x", revenue_cr=239756, revenue_yoy_pct=3.3,
            ebitda_cr=36189, ebitda_margin_pct=15.1, pat_cr=10879, pat_yoy_pct=0.8, pat_yoy_label="+0.8% YoY"),
    covered("JSWSTEEL", "JSW Steel", "Ferrous (Steel)",
            market_cap_cr=320440, pe_label="~13x", revenue_cr=189687, revenue_yoy_pct=2.3,
            ebitda_cr=31628, ebitda_margin_pct=16.7, pat_cr=28468, pat_yoy_pct=27.6, pat_yoy_label="+27.6% YoY"),
    covered("HINDALCO", "Hindalco Industries", "Non-Ferrous (Aluminium)",
            market_cap_cr=230341, pe_label="~14x", revenue_cr=295537, revenue_yoy_pct=7.5,
            ebitda_cr=40910, ebitda_margin_pct=13.8, pat_cr=16400, pat_yoy_pct=22.5, pat_yoy_label="+22.5% YoY"),
    covered("VEDL", "Vedanta", "Diversified Metals",
            market_cap_cr=107066, pe_label="~5.4x", revenue_cr=112051, revenue_yoy_pct=42.9,
            ebitda_cr=34323, ebitda_margin_pct=30.6, pat_cr=28557, pat_yoy_pct=64.2, pat_yoy_label="+64.2% YoY"),
    covered("JINDALSTEL", "Jindal Steel & Power", "Ferrous (Steel)",
            market_cap_cr=117055, pe_label="~43x", revenue_cr=56413, revenue_yoy_pct=6.0,
            ebitda_cr=9314, ebitda_margin_pct=16.5, pat_cr=2724, pat_yoy_pct=-19.1, pat_yoy_label="−19.1% YoY"),
    covered("SAIL", "Steel Authority of India", "Ferrous (Steel, PSU)",
            market_cap_cr=76931, pe_label="~18x", revenue_cr=111135, revenue_yoy_pct=0.3,
            ebitda_cr=13384, ebitda_margin_pct=12.0, pat_cr=3894, pat_yoy_pct=15.5, pat_yoy_label="+15.5% YoY"),
    covered("NMDC", "NMDC", "Mining (Iron Ore, PSU)",
            market_cap_cr=75258, pe_label="~10x", revenue_cr=32127, revenue_yoy_pct=0.2,
            ebitda_cr=9249, ebitda_margin_pct=28.8, pat_cr=7453, pat_yoy_pct=0.0, pat_yoy_label="flat YoY"),
    covered("NATIONALUM", "National Aluminium", "Non-Ferrous (Aluminium, PSU)",
            market_cap_cr=69608, pe_label="~10x", revenue_cr=19338, revenue_yoy_pct=8.4,
            ebitda_cr=9162, ebitda_margin_pct=47.4, pat_cr=6754, pat_yoy_pct=16.5, pat_yoy_label="+16.5% YoY"),
]

METALS_ROSTER = [
    roster("HINDZINC", "Hindustan Zinc", "Non-Ferrous (Zinc)"),
    roster("APLAPOLLO", "APL Apollo Tubes", "Steel Products (Tubes)"),
    roster("JSL", "Jindal Stainless", "Stainless Steel"),
    roster("RATNAMANI", "Ratnamani Metals & Tubes", "Steel Pipes"),
    roster("WELCORP", "Welspun Corp", "Steel Pipes"),
    roster("MOIL", "MOIL", "Mining (Manganese, PSU)"),
    roster("HINDCOPPER", "Hindustan Copper", "Non-Ferrous (Copper, PSU)"),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(METALS_COVERED, METALS_ROSTER)
