"""RSS search for related coverage — real-time network I/O, but no LLM and no ML
model: a plain httpx GET (already a dependency, used in market_data.py) against
Google News RSS plus a stdlib XML parse. Optional-but-on-by-default per the
news-pipeline plan; a config flag disables it for fully air-gapped operation.

This enriches a linked story with corroborating coverage — "here's what else is being
reported about this company" — after linker.py has already identified the company.
Never a hard dependency: any failure (network down, timeout, malformed XML) returns
an empty list rather than raising, since related coverage is a nice-to-have, not
something the pipeline should ever block on.
"""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_RSS_URL = "https://news.google.com/rss/search"
_DEFAULT_TIMEOUT = 8.0


@dataclass(frozen=True)
class RelatedArticle:
    title: str
    url: str
    source: str
    published_at: str  # raw RFC822 pubDate string as provided by the feed


def parse_rss(xml_text: str) -> list[RelatedArticle]:
    """Parse RSS 2.0 XML into RelatedArticle rows. Pure function, no network — the
    part of this module that's meaningfully unit-testable without live fetches."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    out: list[RelatedArticle] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        pub_date = (item.findtext("pubDate") or "").strip()
        out.append(RelatedArticle(title=title, url=link, source=source, published_at=pub_date))
    return out


def search_related(query: str, *, limit: int = 3, timeout: float = _DEFAULT_TIMEOUT) -> list[RelatedArticle]:
    """Query Google News RSS for `query`, return up to `limit` related articles.
    Returns [] on any failure — enrichment only, never a hard pipeline dependency."""
    if not query or not query.strip():
        return []
    try:
        import httpx

        params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
        url = f"{_RSS_URL}?{urllib.parse.urlencode(params)}"
        r = httpx.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return parse_rss(r.text)[:limit]
    except Exception:
        return []
