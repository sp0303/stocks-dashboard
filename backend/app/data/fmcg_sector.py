"""FMCG — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
underlying volume growth (UVG), gross margin, rural vs urban growth, A&P spend % of sales,
price/mix, direct-reach/outlet count.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

# FY26 (consolidated) fundamentals compiled from Tijori Finance.
FMCG_COVERED = [
    covered("HINDUNILVR", "Hindustan Unilever", "Home & Personal Care",
            market_cap_cr=456996, pe_label="~31x", revenue_cr=66374, revenue_yoy_pct=3.0,
            ebitda_cr=15305, ebitda_margin_pct=23.1, pat_cr=14985, pat_yoy_pct=-0.4, pat_yoy_label="−0.4% YoY"),
    covered("ITC", "ITC", "Diversified FMCG / Cigarettes",
            market_cap_cr=327278, pe_label="~17x", revenue_cr=96307, revenue_yoy_pct=22.1,
            ebitda_cr=25682, ebitda_margin_pct=26.7, pat_cr=19789, pat_yoy_pct=-4.4, pat_yoy_label="−4.4% YoY"),
    covered("NESTLEIND", "Nestlé India", "Packaged Foods",
            market_cap_cr=268633, pe_label="~70x", revenue_cr=24437, revenue_yoy_pct=5.5,
            ebitda_cr=5674, ebitda_margin_pct=23.2, pat_cr=3860, pat_yoy_pct=10.3, pat_yoy_label="+10.3% YoY"),
    covered("VBL", "Varun Beverages", "Beverages",
            market_cap_cr=137328, pe_label="~41x", revenue_cr=24755, revenue_yoy_pct=14.2,
            ebitda_cr=5659, ebitda_margin_pct=22.9, pat_cr=3422, pat_yoy_pct=12.7, pat_yoy_label="+12.7% YoY"),
    covered("BRITANNIA", "Britannia Industries", "Packaged Foods",
            market_cap_cr=122831, pe_label="~47x", revenue_cr=19529, revenue_yoy_pct=2.0,
            ebitda_cr=3627, ebitda_margin_pct=18.6, pat_cr=2637, pat_yoy_pct=4.1, pat_yoy_label="+4.1% YoY"),
    covered("DABUR", "Dabur India", "Ayurvedic / Personal Care",
            market_cap_cr=65991, pe_label="~33x", revenue_cr=13552, revenue_yoy_pct=2.7,
            ebitda_cr=2525, ebitda_margin_pct=18.6, pat_cr=1948, pat_yoy_pct=2.8, pat_yoy_label="+2.8% YoY"),
    covered("GODREJCP", "Godrej Consumer Products", "Home & Personal Care",
            market_cap_cr=88516, pe_label="~46x", revenue_cr=16050, revenue_yoy_pct=5.7,
            ebitda_cr=3257, ebitda_margin_pct=20.3, pat_cr=1914, pat_yoy_pct=2.8, pat_yoy_label="+2.8% YoY"),
    covered("MARICO", "Marico", "Personal Care / Edible Oil",
            market_cap_cr=105348, pe_label="~56x", revenue_cr=14309, revenue_yoy_pct=5.1,
            ebitda_cr=2492, ebitda_margin_pct=17.4, pat_cr=1952, pat_yoy_pct=10.8, pat_yoy_label="+10.8% YoY"),
]

FMCG_ROSTER = [
    roster("COLPAL", "Colgate-Palmolive (India)", "Oral Care"),
    roster("TATACONSUM", "Tata Consumer Products", "Beverages / Foods"),
    roster("UBL", "United Breweries", "Beverages (Beer)"),
    roster("RADICO", "Radico Khaitan", "Beverages (Spirits)"),
    roster("EMAMILTD", "Emami", "Personal Care"),
    roster("PGHH", "Procter & Gamble Hygiene & Health Care", "Personal Care (MNC)"),
    roster("JYOTHYLAB", "Jyothy Labs", "Home Care"),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(FMCG_COVERED, FMCG_ROSTER)
