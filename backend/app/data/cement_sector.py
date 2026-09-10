"""Cement — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sector-specific KPIs to research:
sales volume (mt), realisation/tonne, EBITDA/tonne, capacity & utilisation, fuel/freight
cost, capex & expansion pipeline, regional mix (cement is a regional business).
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

# FY26 (consolidated) fundamentals compiled from Tijori Finance.
CEMENT_COVERED = [
    covered("ULTRACEMCO", "UltraTech Cement", "Cement (pan-India)",
            market_cap_cr=321082, pe_label="~38x", revenue_cr=91884, revenue_yoy_pct=3.8,
            ebitda_cr=17625, ebitda_margin_pct=19.2, pat_cr=8581, pat_yoy_pct=5.1, pat_yoy_label="+5.1% YoY"),
    covered("SHREECEM", "Shree Cement", "Cement (North)",
            market_cap_cr=82666, pe_label="~51x", revenue_cr=21896, revenue_yoy_pct=4.5,
            ebitda_cr=4577, ebitda_margin_pct=20.9, pat_cr=1636, pat_yoy_pct=-6.2, pat_yoy_label="−6.2% YoY"),
    covered("AMBUJACEM", "Ambuja Cements", "Cement (Adani group)",
            market_cap_cr=98411, pe_label="~22x", revenue_cr=39867, revenue_yoy_pct=-1.9,
            ebitda_cr=6167, ebitda_margin_pct=15.5, pat_cr=5166, pat_yoy_pct=9.3, pat_yoy_label="+9.3% YoY"),
    covered("ACC", "ACC", "Cement (Adani group)",
            market_cap_cr=23620, pe_label="~12x", revenue_cr=25369, revenue_yoy_pct=-2.3,
            ebitda_cr=2629, ebitda_margin_pct=10.4, pat_cr=1902, pat_yoy_pct=-11.0, pat_yoy_label="−11.0% YoY"),
    covered("DALBHARAT", "Dalmia Bharat", "Cement (East / South)",
            market_cap_cr=32526, pe_label="~35x", revenue_cr=15058, revenue_yoy_pct=1.7,
            ebitda_cr=3005, ebitda_margin_pct=20.0, pat_cr=953, pat_yoy_pct=-16.3, pat_yoy_label="−16.3% YoY"),
    covered("JKCEMENT", "JK Cement", "Cement (North) + Paints",
            market_cap_cr=38555, pe_label="~41x", revenue_cr=14401, revenue_yoy_pct=4.9,
            ebitda_cr=2334, ebitda_margin_pct=16.2, pat_cr=938, pat_yoy_pct=-5.5, pat_yoy_label="−5.5% YoY"),
    covered("RAMCOCEM", "The Ramco Cements", "Cement (South)",
            market_cap_cr=20450, pe_label="~32x", revenue_cr=9228, revenue_yoy_pct=2.2,
            ebitda_cr=1345, ebitda_margin_pct=14.6, pat_cr=639, pat_yoy_pct=-8.6, pat_yoy_label="−8.6% YoY"),
    covered("JKLAKSHMI", "JK Lakshmi Cement", "Cement (North / West)",
            market_cap_cr=6194, pe_label="~17x", revenue_cr=6926, revenue_yoy_pct=2.4,
            ebitda_cr=958, ebitda_margin_pct=13.8, pat_cr=380, pat_yoy_pct=-7.7, pat_yoy_label="−7.7% YoY"),
]

# FY26 fundamentals from Tijori. BIRLACORPN left profile-only (entity didn't resolve).
CEMENT_ROSTER = [
    roster("NUVOCO", "Nuvoco Vistas", "Cement (East)",
           market_cap_cr=11970, pe_label="~31x", revenue_cr=11594, revenue_yoy_pct=2.3,
           ebitda_cr=1907, ebitda_margin_pct=16.4, pat_cr=386, pat_yoy_pct=7.5),
    roster("INDIACEM", "The India Cements", "Cement (South)",
           market_cap_cr=10898, pe_label="~118x", revenue_cr=4479, revenue_yoy_pct=-0.1,
           ebitda_cr=469, ebitda_margin_pct=10.5, pat_cr=92, pat_yoy_pct=237.5),
    roster("BIRLACORPN", "Birla Corporation", "Cement (Central)"),
    roster("STARCEMENT", "Star Cement", "Cement (North-East)",
           market_cap_cr=7740, pe_label="~21x", revenue_cr=3807, revenue_yoy_pct=20.4,
           ebitda_cr=902, ebitda_margin_pct=23.7, pat_cr=366, pat_yoy_pct=116.7),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(CEMENT_COVERED, CEMENT_ROSTER)
