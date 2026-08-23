"""Maps Upstox tradebook company display names to NSE ticker symbols.

Upstox exports carry a truncated company display name instead of a trading
symbol (e.g. "HDFC STANDARD LIFE INSURANCE C" for HDFC Life, truncated to a
fixed field width), unlike Zerodha which exports the real symbol directly.
This is a curated lookup for names observed in the wild; unmapped names fall
back to a cleaned-up version of the company name itself.
"""
from __future__ import annotations

import re

# key: company name as it appears (or is truncated to) in an Upstox export,
# upper-cased and with punctuation/legal suffixes stripped. value: NSE symbol.
_COMPANY_TO_SYMBOL = {
    "BURGER KING INDIA": "RBA",  # Restaurant Brands Asia (formerly Burger King India)
    "CANARA BANK": "CANBK",
    "CSB BANK": "CSBBANK",
    "HBL P SYS": "HBLPOWER",
    "HBL POWER SYSTEMS": "HBLPOWER",
    "HDFC BANK": "HDFCBANK",
    "HDFC BANK LT": "HDFCBANK",
    "HDFC MUTUAL FUND": "HDFCAMC",
    "HDFC STANDARD LIFE INSURANCE": "HDFCLIFE",
    "HDFC STANDARD LIFE INSURANCE C": "HDFCLIFE",  # Upstox truncates mid-word
    "INDIAN HOTELS": "INDHOTEL",
    "NIFTY BEES": "NIFTYBEES",
    "RAYMOND LIFESTYLE": "RAYMONDLSL",
    "RAYMOND REALTY": "RAYMONDREL",
    "RELAXO FOOTE": "RELAXO",
    "RELAXO FOOTWEARS": "RELAXO",
    "SOUTH INDIA": "SOUTHBANK",
    "SOUTH INDIAN BANK": "SOUTHBANK",
    "TRIDENT": "TRIDENT",
    "UGAR SUGAR W": "UGARSUGAR",
    "UGAR SUGAR WORKS": "UGARSUGAR",
    "VIMTA LABS": "VIMTALABS",
    "VIMTA LABS L": "VIMTALABS",
}

_SUFFIX_RE = re.compile(
    r"\b(LIMITED|LTD|LT|COMPANY|CO|PVT|PRIVATE)\b\.?"
)
_TAG_RE = re.compile(r"\(BSE INDONEXT\)|#\s*EQ\b", re.IGNORECASE)


def _clean(name: str) -> str:
    n = _TAG_RE.sub("", name.upper())
    n = _SUFFIX_RE.sub("", n)
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def resolve_symbol(company_name: str) -> str:
    """Best-effort company display name -> NSE ticker symbol.

    Falls back to the cleaned, upper-cased company name when no mapping is
    known — better than nothing, but won't resolve live quotes.
    """
    if not company_name:
        return company_name
    cleaned = _clean(company_name)
    return _COMPANY_TO_SYMBOL.get(cleaned, cleaned)
