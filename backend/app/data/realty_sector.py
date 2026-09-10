"""Realty — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
pre-sales / bookings value (₹cr and area), collections, new launches, net debt, embedded/
unrecognised revenue, annuity (rental) income for the commercial-heavy names.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

REALTY_COVERED = [
    covered("DLF", "DLF", "Residential + Commercial"),
    covered("GODREJPROP", "Godrej Properties", "Residential"),
    covered("OBEROIRLTY", "Oberoi Realty", "Residential + Commercial"),
    covered("PRESTIGE", "Prestige Estates Projects", "Residential + Commercial"),
    covered("LODHA", "Macrotech Developers (Lodha)", "Residential"),
    covered("PHOENIXLTD", "The Phoenix Mills", "Retail Malls (annuity)"),
    covered("BRIGADE", "Brigade Enterprises", "Residential + Commercial"),
    covered("SOBHA", "Sobha", "Residential"),
]

REALTY_ROSTER = [
    roster("MAHLIFE", "Mahindra Lifespace Developers", "Residential"),
    roster("SUNTECK", "Sunteck Realty", "Residential"),
    roster("ANANTRAJ", "Anant Raj", "Residential + Data Centres"),
    roster("NBCC", "NBCC (India)", "Construction / PMC (PSU)"),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(REALTY_COVERED, REALTY_ROSTER)
