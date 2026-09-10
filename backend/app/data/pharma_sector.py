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

# FY26 (consolidated) fundamentals from Tijori Finance. ABBOTINDIA left profile-only
# (consolidated P&L didn't resolve cleanly — to re-read).
PHARMA_ROSTER = [
    roster("ZYDUSLIFE", "Zydus Lifesciences", "Formulations (US + domestic)",
           market_cap_cr=112618, pe_label="~25x", revenue_cr=28592, revenue_yoy_pct=5.3,
           ebitda_cr=7257, ebitda_margin_pct=25.4, pat_cr=4492, pat_yoy_pct=-10.9),
    roster("BIOCON", "Biocon", "Biosimilars / API",
           market_cap_cr=64373, pe_label="~130x", revenue_cr=17321, revenue_yoy_pct=2.3,
           ebitda_cr=3536, ebitda_margin_pct=20.4, pat_cr=416, pat_yoy_pct=8.0),
    roster("GLENMARK", "Glenmark Pharmaceuticals", "Formulations",
           market_cap_cr=68850, pe_label="~38x", revenue_cr=17737, revenue_yoy_pct=4.4,
           ebitda_cr=4797, ebitda_margin_pct=27.0, pat_cr=1798, pat_yoy_pct=32.0),
    roster("MANKIND", "Mankind Pharma", "Formulations (domestic)",
           market_cap_cr=93596, pe_label="~46x", revenue_cr=14738, revenue_yoy_pct=3.2,
           ebitda_cr=3827, ebitda_margin_pct=26.0, pat_cr=2055, pat_yoy_pct=7.4),
    roster("LAURUSLABS", "Laurus Labs", "API / CDMO",
           market_cap_cr=104456, pe_label="~96x", revenue_cr=7270, revenue_yoy_pct=6.7,
           ebitda_cr=2034, ebitda_margin_pct=28.0, pat_cr=1091, pat_yoy_pct=22.7),
    roster("ABBOTINDIA", "Abbott India", "Formulations (MNC)"),
    roster("APOLLOHOSP", "Apollo Hospitals Enterprise", "Hospitals",
           market_cap_cr=128831, pe_label="~62x", revenue_cr=26430, revenue_yoy_pct=4.8,
           ebitda_cr=4010, ebitda_margin_pct=15.2, pat_cr=2127, pat_yoy_pct=9.6),
    roster("MAXHEALTH", "Max Healthcare Institute", "Hospitals",
           market_cap_cr=100884, pe_label="~69x", revenue_cr=8712, revenue_yoy_pct=4.0,
           ebitda_cr=2318, ebitda_margin_pct=26.6, pat_cr=1457, pat_yoy_pct=1.0),
    roster("FORTIS", "Fortis Healthcare", "Hospitals",
           market_cap_cr=68845, pe_label="~66x", revenue_cr=9506, revenue_yoy_pct=4.1,
           ebitda_cr=2131, ebitda_margin_pct=22.4, pat_cr=1052, pat_yoy_pct=1.0),
    roster("IPCALAB", "IPCA Laboratories", "Formulations / API",
           market_cap_cr=49820, pe_label="~38x", revenue_cr=10126, revenue_yoy_pct=5.5,
           ebitda_cr=2232, ebitda_margin_pct=22.0, pat_cr=1380, pat_yoy_pct=20.9),
]

# India Pharma Market (IPM) + sector benchmark — to research (moving-annual-total growth,
# US price erosion, etc.). Left as a stub until the KPI phase.
INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(PHARMA_COVERED, PHARMA_ROSTER)
