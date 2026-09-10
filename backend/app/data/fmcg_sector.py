"""FMCG — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
underlying volume growth (UVG), gross margin, rural vs urban growth, A&P spend % of sales,
price/mix, direct-reach/outlet count.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

FMCG_COVERED = [
    covered("HINDUNILVR", "Hindustan Unilever", "Home & Personal Care"),
    covered("ITC", "ITC", "Diversified FMCG / Cigarettes"),
    covered("NESTLEIND", "Nestlé India", "Packaged Foods"),
    covered("VBL", "Varun Beverages", "Beverages"),
    covered("BRITANNIA", "Britannia Industries", "Packaged Foods"),
    covered("DABUR", "Dabur India", "Ayurvedic / Personal Care"),
    covered("GODREJCP", "Godrej Consumer Products", "Home & Personal Care"),
    covered("MARICO", "Marico", "Personal Care / Edible Oil"),
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
