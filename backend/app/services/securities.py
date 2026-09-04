"""Security master — symbol -> sector / market-cap / asset class.

Loads NSE stock classifications from a curated CSV file. This provides accurate,
verified sector classifications for all traded stocks.
"""
from __future__ import annotations

import csv
from pathlib import Path

# Load stock master from CSV at module init
_STOCK_MASTER: dict[str, tuple[str, str]] = {}

def _load_stock_master():
    """Load NSE stock classifications from CSV file."""
    csv_path = Path(__file__).parent.parent / "data" / "nse_stocks.csv"
    try:
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row["symbol"].strip().upper()
                sector = row["sector"].strip()
                market_cap = row["market_cap"].strip()
                _STOCK_MASTER[symbol] = (sector, market_cap)
    except Exception as e:
        print(f"Warning: could not load stock master from {csv_path}: {e}")


_load_stock_master()

# Non-equity asset classes (overrides from CSV)
_ASSET_CLASS_OVERRIDE = {
    "NIFTYBEES": "ETF",
    "NDTV-RE": "OTHER",
}


def classify(symbol: str) -> dict:
    """Classify a stock by symbol. Returns dict with sector, cap, and asset class."""
    symbol = symbol.upper()
    asset_class = _ASSET_CLASS_OVERRIDE.get(symbol, "EQUITY")

    # Look up in stock master (loaded from CSV)
    if symbol in _STOCK_MASTER:
        sector, cap = _STOCK_MASTER[symbol]
    else:
        sector, cap = "Unclassified", "—"

    return {"symbol": symbol, "sector": sector, "cap": cap, "asset_class": asset_class}
