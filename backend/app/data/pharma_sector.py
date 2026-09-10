"""Pharma & Healthcare — NSE roster (validated against Angel scrip master).

Quarterly KPIs are NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research
later: US sales %, ANDA/ANDA-approval count, R&D as % of sales, API vs formulations mix,
USFDA plant status, domestic (IPM) growth; for hospitals: bed count, ARPOB, occupancy.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

# FY26 (consolidated) fundamentals compiled from Tijori Finance.
PHARMA_COVERED = [
    covered("SUNPHARMA", "Sun Pharmaceutical Industries", "Formulations (US + domestic)",
            pe_label="~37x", revenue_cr=59911, revenue_yoy_pct=2.5, ebitda_cr=17263,
            ebitda_margin_pct=28.8, pat_cr=12173, pat_yoy_pct=6.0, pat_yoy_label="+6.0% YoY"),
    covered("CIPLA", "Cipla", "Formulations (domestic + US)",
            market_cap_cr=110515, pe_label="~33x", revenue_cr=28324, revenue_yoy_pct=0.6,
            ebitda_cr=5339, ebitda_margin_pct=18.8, pat_cr=3365, pat_yoy_pct=-13.3, pat_yoy_label="−13.3% YoY"),
    covered("DRREDDY", "Dr. Reddy's Laboratories", "Formulations (US) + API",
            market_cap_cr=95421, pe_label="~30x", revenue_cr=33228, revenue_yoy_pct=-1.4,
            ebitda_cr=5140, ebitda_margin_pct=15.5, pat_cr=3169, pat_yoy_pct=-24.5, pat_yoy_label="−24.5% YoY"),
    covered("DIVISLAB", "Divi's Laboratories", "API / CDMO",
            market_cap_cr=251737, pe_label="~86x", revenue_cr=11230, revenue_yoy_pct=6.3,
            ebitda_cr=3967, ebitda_margin_pct=35.3, pat_cr=2925, pat_yoy_pct=13.9, pat_yoy_label="+13.9% YoY"),
    covered("LUPIN", "Lupin", "Formulations (US + domestic)",
            market_cap_cr=95660, pe_label="~17x", revenue_cr=29967, revenue_yoy_pct=7.2,
            ebitda_cr=9538, ebitda_margin_pct=31.8, pat_cr=5551, pat_yoy_pct=4.1, pat_yoy_label="+4.1% YoY"),
    covered("AUROPHARMA", "Aurobindo Pharma", "Formulations (US) + API",
            market_cap_cr=97239, pe_label="~26x", revenue_cr=34935, revenue_yoy_pct=3.8,
            ebitda_cr=7085, ebitda_margin_pct=20.3, pat_cr=3713, pat_yoy_pct=5.9, pat_yoy_label="+5.9% YoY"),
    covered("TORNTPHARM", "Torrent Pharmaceuticals", "Formulations (domestic)",
            market_cap_cr=187594, pe_label="~86x", revenue_cr=15723, revenue_yoy_pct=12.5,
            ebitda_cr=5191, ebitda_margin_pct=33.0, pat_cr=2156, pat_yoy_pct=-0.3, pat_yoy_label="−0.3% YoY"),
    covered("ALKEM", "Alkem Laboratories", "Formulations (domestic)",
            market_cap_cr=61456, pe_label="~28x", revenue_cr=15081, revenue_yoy_pct=2.5,
            ebitda_cr=3032, ebitda_margin_pct=20.1, pat_cr=2206, pat_yoy_pct=-4.1, pat_yoy_label="−4.1% YoY"),
]

PHARMA_ROSTER = [
    roster("ZYDUSLIFE", "Zydus Lifesciences", "Formulations (US + domestic)"),
    roster("BIOCON", "Biocon", "Biosimilars / API"),
    roster("GLENMARK", "Glenmark Pharmaceuticals", "Formulations"),
    roster("MANKIND", "Mankind Pharma", "Formulations (domestic)"),
    roster("LAURUSLABS", "Laurus Labs", "API / CDMO"),
    roster("ABBOTINDIA", "Abbott India", "Formulations (MNC)"),
    roster("APOLLOHOSP", "Apollo Hospitals Enterprise", "Hospitals"),
    roster("MAXHEALTH", "Max Healthcare Institute", "Hospitals"),
    roster("FORTIS", "Fortis Healthcare", "Hospitals"),
    roster("IPCALAB", "IPCA Laboratories", "Formulations / API"),
]

# India Pharma Market (IPM) + sector benchmark — to research (moving-annual-total growth,
# US price erosion, etc.). Left as a stub until the KPI phase.
INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(PHARMA_COVERED, PHARMA_ROSTER)
