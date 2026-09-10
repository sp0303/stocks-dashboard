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

# FY26 (consolidated) fundamentals from Tijori. HINDPETRO left profile-only (PAT figure
# didn't resolve cleanly — to re-read).
ENERGY_ROSTER = [
    roster("HINDPETRO", "Hindustan Petroleum", "Refining / OMC (PSU)"),
    roster("TATAPOWER", "Tata Power", "Power (Integrated)",
           market_cap_cr=117908, pe_label="~31x", revenue_cr=63445, revenue_yoy_pct=1.6,
           ebitda_cr=14639, ebitda_margin_pct=23.1, pat_cr=4436, pat_yoy_pct=18.4),
    roster("ADANIGREEN", "Adani Green Energy", "Renewables",
           market_cap_cr=216472, pe_label="~121x", revenue_cr=13559, revenue_yoy_pct=4.9,
           ebitda_cr=11711, ebitda_margin_pct=86.4, pat_cr=1788, pat_yoy_pct=8.2),
    roster("OIL", "Oil India", "Upstream (E&P, PSU)",
           market_cap_cr=81168, pe_label="~9.7x", revenue_cr=41186, revenue_yoy_pct=21.3,
           ebitda_cr=13887, ebitda_margin_pct=33.7, pat_cr=8954, pat_yoy_pct=35.3),
    roster("PETRONET", "Petronet LNG", "Gas (LNG regas)",
           market_cap_cr=42818, pe_label="~10x", revenue_cr=37173, revenue_yoy_pct=-14.5,
           ebitda_cr=5711, ebitda_margin_pct=15.4, pat_cr=4093, pat_yoy_pct=4.6),
    roster("IGL", "Indraprastha Gas", "Gas Distribution (CGD)",
           market_cap_cr=21336, pe_label="~16x", revenue_cr=18563, revenue_yoy_pct=14.8,
           ebitda_cr=1627, ebitda_margin_pct=8.8, pat_cr=1071, pat_yoy_pct=-30.9),
    roster("JSWENERGY", "JSW Energy", "Power Generation",
           market_cap_cr=98027, pe_label="~50x", revenue_cr=18965, revenue_yoy_pct=0.3,
           ebitda_cr=10149, ebitda_margin_pct=53.5, pat_cr=2448, pat_yoy_pct=9.3),
    roster("NHPC", "NHPC", "Power (Hydro, PSU)",
           market_cap_cr=77146, pe_label="~20x", revenue_cr=12210, revenue_yoy_pct=5.1,
           ebitda_cr=5787, ebitda_margin_pct=47.4, pat_cr=4264, pat_yoy_pct=13.2),
    roster("TORNTPOWER", "Torrent Power", "Power (Integrated)",
           market_cap_cr=65717, pe_label="~28x", revenue_cr=29184, revenue_yoy_pct=0.8,
           ebitda_cr=5596, ebitda_margin_pct=19.2, pat_cr=2390, pat_yoy_pct=-1.1),
]

INDUSTRY_BENCHMARK = {"period": None, "source": None, "note": "to research"}

ALL_TICKERS, EXCHANGES = finalize(ENERGY_COVERED, ENERGY_ROSTER)
