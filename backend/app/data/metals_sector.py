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

# FY26 fundamentals from Tijori. MOIL left profile-only (PAT didn't resolve cleanly).
METALS_ROSTER = [
    roster("HINDZINC", "Hindustan Zinc", "Non-Ferrous (Zinc)",
           market_cap_cr=256054, pe_label="~15x", revenue_cr=46820, revenue_yoy_pct=14.6,
           ebitda_cr=26255, ebitda_margin_pct=56.1, pat_cr=17067, pat_yoy_pct=23.4),
    roster("APLAPOLLO", "APL Apollo Tubes", "Steel Products (Tubes)",
           market_cap_cr=60182, pe_label="~49x", revenue_cr=22897, revenue_yoy_pct=-0.8,
           ebitda_cr=1841, ebitda_margin_pct=8.0, pat_cr=1229, pat_yoy_pct=2.2),
    roster("JSL", "Jindal Stainless", "Stainless Steel",
           market_cap_cr=64536, pe_label="~20x", revenue_cr=44026, revenue_yoy_pct=2.5,
           ebitda_cr=5580, ebitda_margin_pct=12.7, pat_cr=3174, pat_yoy_pct=-0.6),
    roster("RATNAMANI", "Ratnamani Metals & Tubes", "Steel Pipes",
           market_cap_cr=20064, pe_label="~46x", revenue_cr=4314, revenue_yoy_pct=-4.0,
           ebitda_cr=732, ebitda_margin_pct=17.0, pat_cr=514, pat_yoy_pct=6.6),
    roster("WELCORP", "Welspun Corp", "Steel Pipes",
           market_cap_cr=68795, pe_label="~30x", revenue_cr=17300, revenue_yoy_pct=3.2,
           ebitda_cr=2403, ebitda_margin_pct=13.9, pat_cr=1405, pat_yoy_pct=-12.9),
    roster("MOIL", "MOIL", "Mining (Manganese, PSU)"),
    roster("HINDCOPPER", "Hindustan Copper", "Non-Ferrous (Copper, PSU)",
           market_cap_cr=51480, pe_label="~45x", revenue_cr=3498, revenue_yoy_pct=13.6,
           ebitda_cr=1662, ebitda_margin_pct=47.5, pat_cr=1139, pat_yoy_pct=24.0),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(METALS_COVERED, METALS_ROSTER)
