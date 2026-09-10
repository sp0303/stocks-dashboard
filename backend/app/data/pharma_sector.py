"""Pharma & Healthcare — NSE roster (validated against Angel scrip master).

Quarterly KPIs are NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research
later: US sales %, ANDA/ANDA-approval count, R&D as % of sales, API vs formulations mix,
USFDA plant status, domestic (IPM) growth; for hospitals: bed count, ARPOB, occupancy.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

PHARMA_COVERED = [
    covered("SUNPHARMA", "Sun Pharmaceutical Industries", "Formulations (US + domestic)"),
    covered("CIPLA", "Cipla", "Formulations (domestic + US)"),
    covered("DRREDDY", "Dr. Reddy's Laboratories", "Formulations (US) + API"),
    covered("DIVISLAB", "Divi's Laboratories", "API / CDMO"),
    covered("LUPIN", "Lupin", "Formulations (US + domestic)"),
    covered("AUROPHARMA", "Aurobindo Pharma", "Formulations (US) + API"),
    covered("TORNTPHARM", "Torrent Pharmaceuticals", "Formulations (domestic)"),
    covered("ALKEM", "Alkem Laboratories", "Formulations (domestic)"),
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
