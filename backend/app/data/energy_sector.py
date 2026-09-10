"""Energy, Oil & Gas, Power — NSE roster (validated against Angel scrip master).

Quarterly KPIs NOT filled yet (see RESEARCH_TODO.md). Sub-industries differ a lot, so KPIs
to research are per-type: Upstream — crude/gas production, net realisation; Refining/OMC —
GRM, marketing margin, inventory gain/loss; Gas — volumes (mmscmd), spread; Power gen —
capacity (MW), PLF, merchant/PPA mix, tariff; Transmission — network & availability.
"""
from __future__ import annotations

from app.data._sector_scaffold import covered, finalize, roster

ENERGY_COVERED = [
    covered("RELIANCE", "Reliance Industries", "Oil-to-Chemicals + Diversified"),
    covered("ONGC", "Oil & Natural Gas Corporation", "Upstream (E&P, PSU)"),
    covered("NTPC", "NTPC", "Power Generation (PSU)"),
    covered("POWERGRID", "Power Grid Corporation", "Power Transmission (PSU)"),
    covered("COALINDIA", "Coal India", "Mining (Coal, PSU)"),
    covered("BPCL", "Bharat Petroleum", "Refining / OMC (PSU)"),
    covered("IOC", "Indian Oil Corporation", "Refining / OMC (PSU)"),
    covered("GAIL", "GAIL (India)", "Gas Transmission (PSU)"),
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
