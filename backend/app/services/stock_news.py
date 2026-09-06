"""Lightweight stock-news fetch via Google News RSS.

Free, no API key. We fetch a per-company RSS search, parse it with the stdlib XML parser
(no extra dependency), and return recent headlines with source + timestamp + link.

Important: we surface *headlines as context* — title, source, date, link — and never
reproduce article bodies or assert a verified cause for a price move. Any "catalyst" tag is
a factual keyword match on the headline text itself, not an inference. Consumers should treat
this as "here's what's being written about this stock lately", not investment advice.
"""
from __future__ import annotations

import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

_CACHE: dict[str, tuple[dict, float]] = {}
_TTL = 1800  # 30 min — headlines don't need to be second-fresh, and this protects the source

# Factual keyword tags extracted from the headline text (not an inferred cause).
_CATALYST_KEYWORDS = {
    "Results": ["results", "profit", "q1", "q2", "q3", "q4", "earnings", "pat", "revenue", "net profit", "quarter"],
    "Order / Deal": ["order", "contract", "deal", "wins", "bags", "won", "awarded", "tender"],
    "Stake / Block": ["block deal", "stake", "promoter", "pledge", "acquire stake", "offloads", "buys stake"],
    "Broker action": ["upgrade", "downgrade", "target price", "brokerage", "rating", "buy call", "sell call", "initiate"],
    "M&A": ["merger", "acquisition", "demerger", "amalgamation", "takeover"],
    "Management": ["ceo", "cfo", "resign", "appoint", "md ", "managing director"],
    "Dividend": ["dividend", "bonus", "split", "buyback"],
}


def _tag_catalyst(title: str) -> list[str]:
    t = title.lower()
    return [tag for tag, kws in _CATALYST_KEYWORDS.items() if any(k in t for k in kws)]


def _parse_rss(xml_text: str, limit: int) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = item.findtext("pubDate")
        source_el = item.find("source")
        source = (source_el.text.strip() if source_el is not None and source_el.text else "")
        # Google News titles are usually "Headline - Source"; drop the trailing source echo.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        published_iso = None
        age_days = None
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published_iso = dt.isoformat()
                age_days = round((datetime.now(timezone.utc) - dt).total_seconds() / 86400, 1)
            except (TypeError, ValueError):
                pass
        if not title:
            continue
        items.append({
            "title": title,
            "source": source,
            "link": link,
            "published": published_iso,
            "age_days": age_days,
            "catalysts": _tag_catalyst(title),
        })
        if len(items) >= limit:
            break
    return items


def get_stock_news(company_name: str, ticker: str, *, window_days: int = 14, limit: int = 6) -> dict:
    """Recent headlines for a company via Google News RSS. Cached per (ticker, window).

    Returns {ticker, query, headlines: [...], fetched_at}. Never raises — on any network or
    parse failure it returns an empty headline list so the caller degrades gracefully.
    """
    cache_key = f"{ticker}:{window_days}:{limit}"
    hit = _CACHE.get(cache_key)
    if hit and time.time() - hit[1] < _TTL:
        return hit[0]

    # Quote the company name for an exact-phrase match, restrict to a recent window, India edition.
    query = f'"{company_name}" stock when:{window_days}d'
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    headlines: list[dict] = []
    try:
        r = httpx.get(url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0 (compatible; PortfolioDashboard/1.0)"})
        if r.status_code == 200:
            headlines = _parse_rss(r.text, limit)
    except (httpx.HTTPError, Exception):
        headlines = []

    result = {
        "ticker": ticker,
        "company": company_name,
        "query": query,
        "headlines": headlines,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _CACHE[cache_key] = (result, time.time())
    return result
