"""Orchestrator — wires OCR output through the full offline-first pipeline:

    OCR'd pages -> skip ad/light pages -> segment -> link -> enrich -> RSS enrich
    -> ready-to-store rows

Pure function core (`ingest_pdf`): no store I/O happens here, so it's fully
unit-testable with fixture pages and any `ContentEnricher` (typically
`RuleBasedEnricher` in tests — deterministic, no mocks needed). The caller (the news
router's background task) is responsible for actually writing the returned rows via
`store.insert_news_items` / `store.insert_news_links`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.news import linker, rss, segmenter
from app.services.news.nlp import ContentEnricher
from app.services.news.pdf_extract import PageText

# Below this many characters, a page is ad/light rather than news — matches the
# threshold found while accuracy-testing pdf_extract.py across 4 real ET editions
# (news pages consistently landed >400 chars; ad/light pages <150).
DEFAULT_MIN_PAGE_CHARS = 400


@dataclass
class StoryResult:
    item: dict
    links: list[dict]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:24]


def ingest_pdf(
    pages: list[PageText],
    upload_meta: dict,
    *,
    enricher: ContentEnricher,
    rss_enabled: bool = True,
    rss_max_related: int = 3,
    min_page_chars: int = DEFAULT_MIN_PAGE_CHARS,
) -> list[StoryResult]:
    """Run the full pipeline over one PDF's OCR'd pages.

    `upload_meta` should contain `pdf_upload_id` and (optionally) `published_at` —
    the edition date/time to stamp every resulting item with; defaults to now.
    """
    results: list[StoryResult] = []
    published_at = upload_meta.get("published_at") or _now_iso()

    for page in pages:
        if page.char_count < min_page_chars:
            continue  # ad/light page — no stages run

        for story in segmenter.segment_page(page.text):
            links = linker.link_text(f"{story.title} {story.body}")
            symbols = [lk.symbol for lk in links]

            enrichment = enricher.enrich(story.title, story.body)

            related_articles: list[dict] = []
            if rss_enabled and symbols:
                # highest-confidence linked symbol drives the related-coverage query
                related = rss.search_related(f"{symbols[0]} stock", limit=rss_max_related)
                related_articles = [
                    {"title": a.title, "url": a.url, "source": a.source, "published_at": a.published_at}
                    for a in related
                ]

            item_id = _new_id()
            item = {
                "id": item_id,
                "pdf_upload_id": upload_meta.get("pdf_upload_id"),
                "page": page.page,
                "title": story.title,
                "summary": enrichment.summary,
                "sentiment": enrichment.sentiment,
                "sentiment_score": enrichment.sentiment_score,
                "event_type": enrichment.event_type,
                "symbols": symbols,
                "related_articles": related_articles,
                "enrichment_tier": enrichment.tier,
                "published_at": published_at,
                "created_at": _now_iso(),
                "status": "DONE",
            }
            link_rows = [
                {
                    "item_id": item_id,
                    "symbol": lk.symbol,
                    "confidence": lk.confidence,
                    "match_method": lk.match_method,
                }
                for lk in links
            ]
            results.append(StoryResult(item=item, links=link_rows))

    return results
