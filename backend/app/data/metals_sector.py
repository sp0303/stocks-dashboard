"""Metals & Mining — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
sales volume (tonnes), realisation/tonne, EBITDA/tonne, capacity utilisation, input costs
(coking coal / alumina / ore), net debt & net-debt/EBITDA, export share.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

METALS_COVERED = [
    covered("TATASTEEL", "Tata Steel", "Ferrous (Steel)"),
    covered("JSWSTEEL", "JSW Steel", "Ferrous (Steel)"),
    covered("HINDALCO", "Hindalco Industries", "Non-Ferrous (Aluminium)"),
    covered("VEDL", "Vedanta", "Diversified Metals"),
    covered("JINDALSTEL", "Jindal Steel & Power", "Ferrous (Steel)"),
    covered("SAIL", "Steel Authority of India", "Ferrous (Steel, PSU)"),
    covered("NMDC", "NMDC", "Mining (Iron Ore, PSU)"),
    covered("NATIONALUM", "National Aluminium", "Non-Ferrous (Aluminium, PSU)"),
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
