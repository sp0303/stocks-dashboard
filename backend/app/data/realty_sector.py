"""Realty — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
pre-sales / bookings value (₹cr and area), collections, new launches, net debt, embedded/
unrecognised revenue, annuity (rental) income for the commercial-heavy names.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

# FY26 (consolidated) fundamentals compiled from Tijori Finance. NOTE: for developers, a
# lot of profit flows through JV/associate income *below* the operating line, so reported
# operating margin understates economics and PAT can exceed operating profit (e.g. DLF,
# Godrej Props) — that's real-estate accounting, not a data error.
REALTY_COVERED = [
    covered("DLF", "DLF", "Residential + Commercial",
            market_cap_cr=162479, pe_label="~37x", revenue_cr=6758, revenue_yoy_pct=-17.5,
            ebitda_cr=1235, ebitda_margin_pct=18.3, pat_cr=2548, pat_yoy_pct=-42.3, pat_yoy_label="−42.3% YoY",
            note="PAT > operating profit: much of DLF's profit is JV/rental income below the operating line."),
    covered("GODREJPROP", "Godrej Properties", "Residential",
            market_cap_cr=56028, pe_label="~35x", revenue_cr=5203, revenue_yoy_pct=1.4,
            ebitda_cr=-458, ebitda_margin_pct=-8.8, pat_cr=1610, pat_yoy_pct=-13.0, pat_yoy_label="−13.0% YoY",
            note="Operating line negative; profit comes from JV/associate income (typical for the asset-light model)."),
    covered("OBEROIRLTY", "Oberoi Realty", "Residential + Commercial",
            market_cap_cr=65314, pe_label="~25x", revenue_cr=6322, revenue_yoy_pct=5.2,
            ebitda_cr=3572, ebitda_margin_pct=56.5, pat_cr=2616, pat_yoy_pct=4.3, pat_yoy_label="+4.3% YoY"),
    covered("PRESTIGE", "Prestige Estates Projects", "Residential + Commercial",
            market_cap_cr=66412, pe_label="~58x", revenue_cr=13053, revenue_yoy_pct=2.9,
            ebitda_cr=3675, ebitda_margin_pct=28.2, pat_cr=1276, pat_yoy_pct=6.8, pat_yoy_label="+6.8% YoY"),
    covered("LODHA", "Macrotech Developers (Lodha)", "Residential",
            market_cap_cr=116454, pe_label="~28x", revenue_cr=18181, revenue_yoy_pct=9.0,
            ebitda_cr=5859, ebitda_margin_pct=32.2, pat_cr=4118, pat_yoy_pct=20.1, pat_yoy_label="+20.1% YoY"),
    covered("PHOENIXLTD", "The Phoenix Mills", "Retail Malls (annuity)",
            market_cap_cr=67884, pe_label="~53x", revenue_cr=4545, revenue_yoy_pct=2.8,
            ebitda_cr=2714, ebitda_margin_pct=59.7, pat_cr=1630, pat_yoy_pct=33.2, pat_yoy_label="+33.2% YoY"),
    covered("BRIGADE", "Brigade Enterprises", "Residential + Commercial",
            market_cap_cr=21598, pe_label="~31x", revenue_cr=5532, revenue_yoy_pct=-2.9,
            ebitda_cr=1465, ebitda_margin_pct=26.5, pat_cr=784, pat_yoy_pct=21.6, pat_yoy_label="+21.6% YoY"),
    covered("SOBHA", "Sobha", "Residential",
            market_cap_cr=13138, pe_label="~57x", revenue_cr=5617, revenue_yoy_pct=8.2,
            ebitda_cr=364, ebitda_margin_pct=6.5, pat_cr=231, pat_yoy_pct=19.5, pat_yoy_label="+19.5% YoY"),
]

REALTY_ROSTER = [
    roster("MAHLIFE", "Mahindra Lifespace Developers", "Residential"),
    roster("SUNTECK", "Sunteck Realty", "Residential"),
    roster("ANANTRAJ", "Anant Raj", "Residential + Data Centres"),
    roster("NBCC", "NBCC (India)", "Construction / PMC (PSU)"),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(REALTY_COVERED, REALTY_ROSTER)
