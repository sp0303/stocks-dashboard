"""Orchestrator: OCR pages -> ad-page skip -> segment -> link -> enrich -> RSS ->
ready-to-store rows. Uses the real RuleBasedEnricher (deterministic, no mocks needed)
and monkeypatches rss.search_related so the standard test tier never hits the network.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.news.nlp import RuleBasedEnricher
from app.services.news.pdf_extract import PageText
from app.services.news.pdf_pipeline import ingest_pdf
from app.services.news.rss import RelatedArticle

_NEWS_BODY = (
    "The Supreme Court on Monday asked the Centre to ground airlines that do not "
    "follow airfare rules, even as the government said the final rules to regulate "
    "airfares in the country would be finalised within three weeks, reports Indu "
    "Bhan. The top court also perused the draft rules to regulate airfares that "
    "were submitted by the government in a sealed cover."
)

_RELIANCE_BODY = (
    "Reliance Industries reported net profit surging 20% year-on-year, beating "
    "analyst estimates, with robust growth in retail and telecom. The company "
    "cited record revenue across its core segments this quarter as the main "
    "driver of the strong result."
)


def _news_page(page_no: int, headline: str, body: str) -> PageText:
    text = f"{headline}\n\n{body}"
    return PageText(page=page_no, text=text, method="ocr")


def _ad_page(page_no: int) -> PageText:
    return PageText(page=page_no, text="50% OFF\n\nCall now", method="ocr")


def test_ad_pages_are_skipped_entirely():
    pages = [_ad_page(1), _ad_page(2)]
    results = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0)
    assert results == []


def test_news_page_produces_a_linked_enriched_item():
    pages = [_news_page(3, "SC: Ground Airlines if Airfare Caps Violated", _NEWS_BODY)]
    results = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0)
    assert len(results) == 1

    item = results[0].item
    assert item["title"] == "SC: Ground Airlines if Airfare Caps Violated"
    assert item["page"] == 3
    assert item["pdf_upload_id"] == "u1"
    assert item["summary"]  # non-empty, produced by the enricher
    assert item["sentiment"] in ("POSITIVE", "NEGATIVE", "NEUTRAL")
    assert item["event_type"]
    assert item["enrichment_tier"] == "rules"
    assert item["status"] == "DONE"
    assert item["id"]
    assert item["symbols"] == []  # this story doesn't mention a known company
    assert results[0].links == []


def test_news_page_with_linkable_company_produces_symbols_and_links():
    pages = [_news_page(1, "Reliance profit surges on strong quarter", _RELIANCE_BODY)]
    results = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0)
    assert len(results) == 1

    item, links = results[0].item, results[0].links
    assert "RELIANCE" in item["symbols"]
    assert item["sentiment"] == "POSITIVE"
    assert item["event_type"] == "EARNINGS"

    assert len(links) == 1
    assert links[0]["symbol"] == "RELIANCE"
    assert links[0]["item_id"] == item["id"]  # links correlate to the item by id
    assert links[0]["match_method"] == "EXACT"
    assert links[0]["confidence"] == 1.0


def test_multiple_pages_and_multiple_stories_all_aggregate():
    pages = [
        _ad_page(1),
        _news_page(2, "SC: Ground Airlines if Airfare Caps Violated", _NEWS_BODY),
        _news_page(3, "Reliance profit surges on strong quarter", _RELIANCE_BODY),
    ]
    results = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0)
    assert len(results) == 2
    titles = {r.item["title"] for r in results}
    assert titles == {
        "SC: Ground Airlines if Airfare Caps Violated",
        "Reliance profit surges on strong quarter",
    }


def test_published_at_defaults_and_can_be_overridden():
    pages = [_news_page(1, "Reliance profit surges on strong quarter", _RELIANCE_BODY)]

    with_meta = ingest_pdf(
        pages, {"pdf_upload_id": "u1", "published_at": "2026-08-18T06:00:00+00:00"},
        enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0,
    )
    assert with_meta[0].item["published_at"] == "2026-08-18T06:00:00+00:00"

    without_meta = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0)
    assert without_meta[0].item["published_at"]  # defaulted to "now", non-empty


def test_rss_enrichment_attached_when_enabled(monkeypatch):
    from app.services.news import pdf_pipeline

    called_with = {}

    def fake_search_related(query, *, limit=3):
        called_with["query"] = query
        called_with["limit"] = limit
        return [RelatedArticle(title="Related story", url="https://x.com/a", source="ET", published_at="today")]

    monkeypatch.setattr(pdf_pipeline.rss, "search_related", fake_search_related)

    pages = [_news_page(1, "Reliance profit surges on strong quarter", _RELIANCE_BODY)]
    results = ingest_pdf(
        pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(),
        rss_enabled=True, rss_max_related=2, min_page_chars=0,
    )
    item = results[0].item
    assert len(item["related_articles"]) == 1
    assert item["related_articles"][0]["title"] == "Related story"
    assert called_with["query"] == "RELIANCE stock"
    assert called_with["limit"] == 2


def test_rss_not_queried_when_no_symbols_linked(monkeypatch):
    from app.services.news import pdf_pipeline

    def fail_if_called(*a, **k):
        raise AssertionError("RSS should not be queried when no company was linked")

    monkeypatch.setattr(pdf_pipeline.rss, "search_related", fail_if_called)

    pages = [_news_page(1, "SC: Ground Airlines if Airfare Caps Violated", _NEWS_BODY)]
    results = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=True, min_page_chars=0)
    assert results[0].item["related_articles"] == []


def test_rss_disabled_flag_skips_rss_even_with_symbols(monkeypatch):
    from app.services.news import pdf_pipeline

    def fail_if_called(*a, **k):
        raise AssertionError("RSS should not be queried when rss_enabled=False")

    monkeypatch.setattr(pdf_pipeline.rss, "search_related", fail_if_called)

    pages = [_news_page(1, "Reliance profit surges on strong quarter", _RELIANCE_BODY)]
    results = ingest_pdf(pages, {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(), rss_enabled=False, min_page_chars=0)
    assert results[0].item["related_articles"] == []


def test_min_page_chars_threshold_is_configurable():
    # a page that's technically "news-shaped" but shorter than a custom threshold
    short_page = _news_page(1, "SC: Ground Airlines if Airfare Caps Violated", _NEWS_BODY)
    assert short_page.char_count < 1000

    results_default = ingest_pdf(
        [short_page], {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(),
        rss_enabled=False, min_page_chars=400,
    )
    assert len(results_default) == 1

    results_strict = ingest_pdf(
        [short_page], {"pdf_upload_id": "u1"}, enricher=RuleBasedEnricher(),
        rss_enabled=False, min_page_chars=100_000,
    )
    assert results_strict == []
