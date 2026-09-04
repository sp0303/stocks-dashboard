"""Security master — symbol -> sector / market-cap / asset class.

Maintains a persistent classification cache in the data store. When an unknown stock
is encountered, it's looked up from NSE/yfinance and cached for future use.

This approach scales to any number of stocks because:
1. Classifications are stored in the persistent data store (JSON/MongoDB)
2. Each stock is looked up once, then cached forever
3. New stocks auto-classify on first encounter
4. CSV provides seed data for common stocks (fast startup)
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

# Seed stock master from CSV (loaded at startup for common stocks)
_STOCK_MASTER: dict[str, tuple[str, str]] = {}

# Runtime cache (loaded from store on init, persisted back on updates)
_CLASSIFICATION_CACHE: dict[str, dict] = {}
_CACHE_INITIALIZED = False

# Non-equity asset classes
_ASSET_CLASS_OVERRIDE = {
    "NIFTYBEES": "ETF",
    "NDTV-RE": "OTHER",
}


def _load_seed_data():
    """Load common stocks from CSV seed file for fast startup."""
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
        print(f"Warning: could not load seed data from {csv_path}: {e}")


def _fetch_from_nse_yfinance(symbol: str) -> dict | None:
    """Attempt to fetch stock classification from yfinance as NSE doesn't have a free API.

    Returns {"sector": str, "cap": str} or None if lookup fails.
    Sector comes from yfinance; cap is inferred from market cap if available.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info or {}

        sector = info.get("sector")
        if not sector:
            return None

        # Infer market cap from listed market cap or market cap value
        market_cap = info.get("marketCap") or 0
        if market_cap > 100_000_000_000:
            cap = "Large Cap"
        elif market_cap > 5_000_000_000:
            cap = "Mid Cap"
        else:
            cap = "Small Cap"

        return {"sector": sector, "cap": cap, "fetched_at": time.time()}
    except Exception:
        return None


def init_cache(stored_classifications: dict | None = None):
    """Initialize classification cache from stored data.

    Called by store module after loading persisted data.
    stored_classifications: dict of symbol -> classification from store.
    """
    global _CACHE_INITIALIZED

    _load_seed_data()

    # Load persisted classifications from store
    if stored_classifications:
        _CLASSIFICATION_CACHE.update(stored_classifications)

    _CACHE_INITIALIZED = True


def classify(symbol: str) -> dict:
    """Classify a stock by symbol, with automatic lookup for unknown stocks.

    Returns dict with sector, cap, and asset class.
    """
    symbol = symbol.upper()
    asset_class = _ASSET_CLASS_OVERRIDE.get(symbol, "EQUITY")

    # Try seed data first (fast path for common stocks)
    if symbol in _STOCK_MASTER:
        sector, cap = _STOCK_MASTER[symbol]
        return {"symbol": symbol, "sector": sector, "cap": cap, "asset_class": asset_class}

    # Try runtime cache (persisted classifications)
    if symbol in _CLASSIFICATION_CACHE:
        cached = _CLASSIFICATION_CACHE[symbol]
        return {"symbol": symbol, "sector": cached["sector"], "cap": cached["cap"], "asset_class": asset_class}

    # Try external lookup (yfinance)
    result = _fetch_from_nse_yfinance(symbol)
    if result:
        # Store in cache for future use
        _CLASSIFICATION_CACHE[symbol] = result
        # Return to caller
        return {"symbol": symbol, "sector": result["sector"], "cap": result["cap"], "asset_class": asset_class}

    # Fallback: unknown stock
    return {"symbol": symbol, "sector": "Unclassified", "cap": "—", "asset_class": asset_class}


def get_cache() -> dict:
    """Get current classification cache (for persistence)."""
    return _CLASSIFICATION_CACHE.copy()
