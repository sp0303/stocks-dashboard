"""Energy, Oil & Gas, Power — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sub-industries differ a lot, so KPIs
to research are per-type: Upstream — crude/gas production, net realisation; Refining/OMC —
GRM, marketing margin, inventory gain/loss; Gas — volumes (mmscmd), spread; Power gen —
capacity (MW), PLF, merchant/PPA mix, tariff; Transmission — network & availability.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

# FY26 (consolidated) fundamentals compiled from Tijori Finance.
ENERGY_COVERED = [
    covered("RELIANCE", "Reliance Industries", "Oil-to-Chemicals + Diversified",
            market_cap_cr=1733518, pe_label="~23x", revenue_cr=1138865, revenue_yoy_pct=7.7,
            ebitda_cr=183561, ebitda_margin_pct=16.1, pat_cr=87930, pat_yoy_pct=8.9, pat_yoy_label="+8.9% YoY"),
    covered("ONGC", "Oil & Natural Gas Corporation", "Upstream (E&P, PSU)",
            market_cap_cr=294127, pe_label="~6.8x", revenue_cr=704127, revenue_yoy_pct=15.7,
            ebitda_cr=92698, ebitda_margin_pct=13.2, pat_cr=40966, pat_yoy_pct=-1.1, pat_yoy_label="−1.1% YoY"),
    covered("NTPC", "NTPC", "Power Generation (PSU)",
            market_cap_cr=323141, pe_label="~12x", revenue_cr=191060, revenue_yoy_pct=2.8,
            ebitda_cr=58936, ebitda_margin_pct=30.8, pat_cr=25318, pat_yoy_pct=-6.4, pat_yoy_label="−6.4% YoY"),
    covered("POWERGRID", "Power Grid Corporation", "Power Transmission (PSU)",
            market_cap_cr=247350, pe_label="~16x", revenue_cr=47033, revenue_yoy_pct=0.6,
            ebitda_cr=38369, ebitda_margin_pct=81.6, pat_cr=15981, pat_yoy_pct=0.3, pat_yoy_label="+0.3% YoY"),
    covered("COALINDIA", "Coal India", "Mining (Coal, PSU)",
            market_cap_cr=265922, pe_label="~8.5x", revenue_cr=157856, revenue_yoy_pct=-6.3,
            ebitda_cr=40789, ebitda_margin_pct=25.8, pat_cr=30332, pat_yoy_pct=-2.5, pat_yoy_label="−2.5% YoY"),
    covered("BPCL", "Bharat Petroleum", "Refining / OMC (PSU)",
            market_cap_cr=131630, pe_label="~7.7x", revenue_cr=552733, revenue_yoy_pct=21.4,
            ebitda_cr=27469, ebitda_margin_pct=5.0, pat_cr=16378, pat_yoy_pct=-36.6, pat_yoy_label="−36.6% YoY"),
    covered("IOC", "Indian Oil Corporation", "Refining / OMC (PSU)",
            market_cap_cr=190990, pe_label="~5.7x", revenue_cr=961537, revenue_yoy_pct=22.6,
            ebitda_cr=68515, ebitda_margin_pct=7.1, pat_cr=33204, pat_yoy_pct=-21.1, pat_yoy_label="−21.1% YoY"),
    covered("GAIL", "GAIL (India)", "Gas Transmission (PSU)",
            market_cap_cr=115064, pe_label="~12x", revenue_cr=148016, revenue_yoy_pct=4.5,
            ebitda_cr=14939, ebitda_margin_pct=10.1, pat_cr=8445, pat_yoy_pct=11.4, pat_yoy_label="+11.4% YoY"),
]

ENERGY_ROSTER = [
    roster("HINDPETRO", "Hindustan Petroleum", "Refining / OMC (PSU)"),
    roster("TATAPOWER", "Tata Power", "Power (Integrated)"),
    roster("ADANIGREEN", "Adani Green Energy", "Renewables"),
    roster("OIL", "Oil India", "Upstream (E&P, PSU)"),
    roster("PETRONET", "Petronet LNG", "Gas (LNG regas)"),
    roster("IGL", "Indraprastha Gas", "Gas Distribution (CGD)"),
    roster("JSWENERGY", "JSW Energy", "Power Generation"),
    roster("NHPC", "NHPC", "Power (Hydro, PSU)"),
    roster("TORNTPOWER", "Torrent Power", "Power (Integrated)"),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(ENERGY_COVERED, ENERGY_ROSTER)
