"""RSS related-coverage enrichment. parse_rss is pure (fixture XML, no network) and
covered directly. search_related's fetch is exercised with a fake httpx transport so
CI never needs live network access; a narrow opt-in test hits the real feed.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.news.rss import parse_rss, search_related

_FIXTURE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Reliance stock - Google News</title>
    <item>
      <title>Reliance shares hit record high - Economic Times</title>
      <link>https://example.com/reliance-record</link>
      <pubDate>Fri, 21 Aug 2026 09:00:00 GMT</pubDate>
      <source url="https://economictimes.com">Economic Times</source>
    </item>
    <item>
      <title>Reliance Q1 profit beats estimates - Mint</title>
      <link>https://example.com/reliance-q1</link>
      <pubDate>Fri, 21 Aug 2026 08:00:00 GMT</pubDate>
      <source url="https://livemint.com">Mint</source>
    </item>
  </channel>
</rss>"""


def test_parse_rss_extracts_articles():
    articles = parse_rss(_FIXTURE_RSS)
    assert len(articles) == 2
    assert articles[0].title == "Reliance shares hit record high - Economic Times"
    assert articles[0].url == "https://example.com/reliance-record"
    assert articles[0].source == "Economic Times"
    assert articles[0].published_at == "Fri, 21 Aug 2026 09:00:00 GMT"


def test_parse_rss_skips_items_missing_title_or_link():
    xml = """<rss><channel>
      <item><title>Has both</title><link>https://x.com/a</link></item>
      <item><title>No link here</title></item>
      <item><link>https://x.com/b</link></item>
    </channel></rss>"""
    articles = parse_rss(xml)
    assert len(articles) == 1
    assert articles[0].title == "Has both"


def test_parse_rss_handles_missing_source_gracefully():
    xml = """<rss><channel>
      <item><title>T</title><link>https://x.com/a</link></item>
    </channel></rss>"""
    articles = parse_rss(xml)
    assert articles[0].source == ""


def test_parse_rss_malformed_xml_returns_empty():
    assert parse_rss("<rss><channel><item><title>unclosed") == []
    assert parse_rss("") == []
    assert parse_rss(None) == []


def test_parse_rss_empty_channel_returns_empty():
    assert parse_rss("<rss><channel></channel></rss>") == []


def test_search_related_empty_query_returns_empty_without_network(monkeypatch):
    import httpx

    def fail_if_called(*a, **k):
        raise AssertionError("should not hit the network for an empty query")

    monkeypatch.setattr(httpx, "get", fail_if_called)
    assert search_related("") == []
    assert search_related("   ") == []


def test_search_related_success(monkeypatch):
    import httpx

    class FakeResponse:
        text = _FIXTURE_RSS

        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())

    articles = search_related("Reliance stock", limit=3)
    assert len(articles) == 2
    assert articles[0].title.startswith("Reliance shares")


def test_search_related_respects_limit(monkeypatch):
    import httpx

    class FakeResponse:
        text = _FIXTURE_RSS

        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())

    articles = search_related("Reliance stock", limit=1)
    assert len(articles) == 1


def test_search_related_network_failure_returns_empty_not_raises(monkeypatch):
    import httpx

    def raise_conn_error(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", raise_conn_error)
    assert search_related("Reliance stock") == []


def test_search_related_http_error_returns_empty_not_raises(monkeypatch):
    import httpx

    class FakeResponse:
        text = "irrelevant"

        def raise_for_status(self):
            raise httpx.HTTPStatusError("429", request=None, response=None)

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    assert search_related("Reliance stock") == []


# ---------------------------------------------------------------------------
# Opt-in live smoke test — real network, skipped unless explicitly requested.
# ---------------------------------------------------------------------------

RUN_SLOW = os.environ.get("RUN_SLOW") == "1"


@pytest.mark.slow
@pytest.mark.skipif(not RUN_SLOW, reason="set RUN_SLOW=1 to hit the real Google News RSS feed")
def test_live_search_related_returns_results():
    articles = search_related("Reliance Industries stock", limit=3)
    assert isinstance(articles, list)
    # Live feeds are not guaranteed non-empty, but a well-formed query for a large,
    # constantly-covered company should almost always return something.
    assert len(articles) >= 1
    assert all(a.title and a.url for a in articles)
