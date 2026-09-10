"""Cement — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
sales volume (mt), realisation/tonne, EBITDA/tonne, capacity & utilisation, fuel/freight
cost, capex & expansion pipeline, regional mix (cement is a regional business).
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

CEMENT_COVERED = [
    covered("ULTRACEMCO", "UltraTech Cement", "Cement (pan-India)"),
    covered("SHREECEM", "Shree Cement", "Cement (North)"),
    covered("AMBUJACEM", "Ambuja Cements", "Cement (Adani group)"),
    covered("ACC", "ACC", "Cement (Adani group)"),
    covered("DALBHARAT", "Dalmia Bharat", "Cement (East / South)"),
    covered("JKCEMENT", "JK Cement", "Cement (North) + Paints"),
    covered("RAMCOCEM", "The Ramco Cements", "Cement (South)"),
    covered("JKLAKSHMI", "JK Lakshmi Cement", "Cement (North / West)"),
]

CEMENT_ROSTER = [
    roster("NUVOCO", "Nuvoco Vistas", "Cement (East)"),
    roster("INDIACEM", "The India Cements", "Cement (South)"),
    roster("BIRLACORPN", "Birla Corporation", "Cement (Central)"),
    roster("STARCEMENT", "Star Cement", "Cement (North-East)"),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(CEMENT_COVERED, CEMENT_ROSTER)
