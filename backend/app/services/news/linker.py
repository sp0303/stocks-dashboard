"""Entity/company detection — turns "article mentions Reliance" into "-> RELIANCE".

Offline, rule-based: no ML model, no network call. Reuses `securities.py` as the single
source of truth for which symbols exist (no second symbol list to keep in sync), plus a
small curated alias map here for the company-name variants a newspaper actually prints
(same "curated map, extend freely" philosophy `securities.py` already uses for sectors).

Match cascade, cheapest first:
  1. EXACT — the ticker itself appears as a token in the text.
  2. ALIAS — a curated company-name variant appears.
  3. FUZZY — most (but not all) of a multi-word alias's significant words appear —
     catches one OCR-mangled word in an otherwise-clear company name.

Matching tolerates OCR word-joining (space-collapsed substring, not just exact token
boundaries) — the dominant OCR failure mode found while accuracy-testing pdf_extract.py
on real newsprint (e.g. "Veolia has" -> "veoliahas").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.securities import _LARGE_MID, _REFERENCE

# SYMBOL -> extra name variants a newspaper might print instead of the ticker.
# Seeded for the symbols securities.py already knows about; extend freely.
ALIASES: dict[str, list[str]] = {
    "RELIANCE": ["reliance industries", "ril"],
    "TCS": ["tata consultancy", "tata consultancy services"],
    "HDFCBANK": ["hdfc bank"],
    "ICICIBANK": ["icici bank"],
    "INFY": ["infosys"],
    "BHARTIARTL": ["bharti airtel", "airtel"],
    "SBIN": ["state bank of india", "sbi"],
    "LT": ["larsen", "larsen & toubro", "larsen and toubro"],
    "AXISBANK": ["axis bank"],
    "KOTAKBANK": ["kotak mahindra bank", "kotak bank"],
    "TATAMOTORS": ["tata motors"],
    "TATASTEEL": ["tata steel"],
    "HCLTECH": ["hcl technologies", "hcl tech"],
    "SUNPHARMA": ["sun pharma", "sun pharmaceutical"],
    "BAJFINANCE": ["bajaj finance"],
    "BAJAJFINSV": ["bajaj finserv"],
    "ULTRACEMCO": ["ultratech cement", "ultratech"],
    "HINDUNILVR": ["hindustan unilever", "hul"],
    "NESTLEIND": ["nestle india", "nestle"],
    "TITAN": ["titan company"],
    "ASIANPAINT": ["asian paints"],
    "MARUTI": ["maruti suzuki"],
    "POWERGRID": ["power grid"],
    "ONGC": ["oil and natural gas"],
    "COALINDIA": ["coal india"],
    "BPCL": ["bharat petroleum"],
    "IOC": ["indian oil"],
    "ADANIENT": ["adani enterprises"],
    "ADANIPORTS": ["adani ports"],
    "ADANIGREEN": ["adani green"],
    "VEDL": ["vedanta"],
    "HINDALCO": ["hindalco industries"],
    "JSWSTEEL": ["jsw steel"],
    "GRASIM": ["grasim industries"],
    "DRREDDY": ["dr reddy", "dr reddys", "dr. reddy's"],
    "DIVISLAB": ["divi's laboratories", "divis lab"],
    "EICHERMOT": ["eicher motors"],
    "HEROMOTOCO": ["hero motocorp"],
    "TECHM": ["tech mahindra"],
    "LTIM": ["lti mindtree", "ltimindtree"],
    "SBILIFE": ["sbi life"],
    "ICICIPRULI": ["icici prudential"],
    "SHRIRAMFIN": ["shriram finance"],
    "CHOLAFIN": ["cholamandalam"],
    "MUTHOOTFIN": ["muthoot finance"],
    "INDHOTEL": ["indian hotels"],
    "TATACONSUM": ["tata consumer"],
    "GODREJCP": ["godrej consumer"],
    "DABUR": ["dabur india"],
    "PIDILITIND": ["pidilite industries", "pidilite"],
    "GAIL": ["gail india"],
    "PNB": ["punjab national bank"],
    "BANKBARODA": ["bank of baroda"],
    "INDUSINDBK": ["indusind bank"],
    "TATAPOWER": ["tata power"],
    "DMART": ["avenue supermarts"],
    "PAYTM": ["one 97", "one97"],
    "TVSMOTOR": ["tvs motor"],
    "BAJAJHLDNG": ["bajaj holdings"],
    "HDFCLIFE": ["hdfc life"],
    "APOLLOHOSP": ["apollo hospitals"],
    "AUBANK": ["au small finance bank", "au bank"],
}

# Tickers under this length are skipped for bare EXACT matching (too likely to collide
# with ordinary short words/abbreviations in prose); they still match via ALIAS.
_MIN_EXACT_TICKER_LEN = 3

_WORD = re.compile(r"[a-z0-9]+")
_FUZZY_MIN_OVERLAP = 0.6


@dataclass(frozen=True)
class LinkResult:
    symbol: str
    confidence: float
    match_method: str  # EXACT | ALIAS | FUZZY


def _known_symbols() -> set[str]:
    return set(_LARGE_MID) | set(_REFERENCE)


def _prep(text: str) -> tuple[str, str]:
    """(space-padded token stream, fully-collapsed no-space string) for substring
    checks that tolerate OCR word-joining."""
    toks = _WORD.findall(text.lower())
    return " " + " ".join(toks) + " ", "".join(toks)


def _contains(phrase: str, spaced: str, collapsed: str) -> bool:
    words = _WORD.findall(phrase.lower())
    if not words:
        return False
    joined = " ".join(words)
    return f" {joined} " in spaced or "".join(words) in collapsed


def _fuzzy_overlap(phrase: str, spaced: str, collapsed: str) -> float:
    words = [w for w in _WORD.findall(phrase.lower()) if len(w) >= 3]
    if len(words) < 2:  # fuzzy only makes sense for multi-word aliases
        return 0.0
    hits = sum(1 for w in words if f" {w} " in spaced or w in collapsed)
    return hits / len(words)


def link_text(text: str) -> list[LinkResult]:
    """Find every known symbol mentioned in `text`. One result per matched symbol,
    keeping its best (cheapest/most confident) match method."""
    if not text:
        return []
    spaced, collapsed = _prep(text)
    results: dict[str, LinkResult] = {}

    for symbol in _known_symbols():
        if len(symbol) >= _MIN_EXACT_TICKER_LEN and _contains(symbol, spaced, collapsed):
            results[symbol] = LinkResult(symbol, 1.0, "EXACT")
            continue

        best_fuzzy = 0.0
        matched_alias = False
        for alias in ALIASES.get(symbol, []):
            if _contains(alias, spaced, collapsed):
                matched_alias = True
                break
            best_fuzzy = max(best_fuzzy, _fuzzy_overlap(alias, spaced, collapsed))

        if matched_alias:
            results[symbol] = LinkResult(symbol, 0.9, "ALIAS")
        elif best_fuzzy >= _FUZZY_MIN_OVERLAP:
            # scale confidence within the 0.6-0.8 band by how much of the alias matched
            confidence = round(0.6 + 0.2 * (best_fuzzy - _FUZZY_MIN_OVERLAP) / (1 - _FUZZY_MIN_OVERLAP), 2)
            results[symbol] = LinkResult(symbol, confidence, "FUZZY")

    return sorted(results.values(), key=lambda r: -r.confidence)
