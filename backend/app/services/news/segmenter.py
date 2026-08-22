"""Rules + NLP — splits one page's OCR text blob into distinct story candidates.

Offline, zero dependencies. Real ET pages OCR as a stream of paragraph blocks
separated by blank lines (Tesseract's own block segmentation); a headline visually
differs from body copy mainly by being short relative to what follows it, so that's
the heuristic used here: a short block immediately followed by a meaningfully longer
one starts a new story, and body blocks accumulate until the next such headline.

This intentionally doesn't need to be perfect — a caption or byline occasionally gets
misread as a headline, or two short related stories occasionally merge. That's fine:
downstream linking/ranking already tolerates noisy or merged items (see nlp.py /
linker.py); segmentation just needs to get most real stories right without heavy
machinery (no ML model, no column/bbox clustering).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_BLOCK_SPLIT = re.compile(r"\n\s*\n+")
_TOKEN = re.compile(r"\S+")

# Masthead/page-furniture text is short (word-count-wise indistinguishable from a real
# headline) but constant across every edition — sourced from the real ET pages OCR'd
# and accuracy-tested this session. Filtered out before segmentation so it can't be
# mistaken for a headline or swallow a real one via the lookahead. Curated, extend
# freely (same pattern as securities.py's sector map).
_MASTHEAD_NOISE = re.compile(
    r"(www\.\w+\.com|bennett,?\s*coleman|estd\.?\s*\d{4}|vol\.\s*\d+\s*no\.\s*\d+|"
    r"times of india|mumbai mirror|to order your favourite newspaper|"
    r"applicable (only )?on \w+ purchase|the economic times)",
    re.IGNORECASE,
)

MIN_HEADLINE_WORDS = 2
MAX_HEADLINE_WORDS = 15
# A story needs at least this many body words to be kept — filters out headline-only
# fragments (a trailing short block, a caption with no real body) as noise.
MIN_BODY_WORDS = 15
# How many short blocks (byline, dateline, subhead) between a headline and its first
# real paragraph we'll tolerate before giving up on that headline having a body.
_LOOKAHEAD_BLOCKS = 2


@dataclass(frozen=True)
class StoryCandidate:
    title: str
    body: str


def _word_count(text: str) -> int:
    return len(_TOKEN.findall(text))


def segment_page(
    text: str,
    *,
    min_headline_words: int = MIN_HEADLINE_WORDS,
    max_headline_words: int = MAX_HEADLINE_WORDS,
    min_body_words: int = MIN_BODY_WORDS,
    lookahead_blocks: int = _LOOKAHEAD_BLOCKS,
) -> list[StoryCandidate]:
    """Split one page's OCR text into story candidates.

    A short block (2-15 words) is a candidate headline. The blocks immediately after
    it may include a byline/dateline/subhead (also short) before the real paragraph
    text starts — those are tolerated (folded into the body) rather than mistaken for
    a second headline, up to `lookahead_blocks` of them. Once a long block appears,
    every consecutive long block is absorbed as body until the next candidate
    headline. A candidate with no body found within the lookahead window is dropped
    (it was noise — a caption, page furniture, or a genuine headline with an article
    that continues off-page).
    """
    blocks = [b.strip() for b in _BLOCK_SPLIT.split(text or "") if b.strip()]
    blocks = [b for b in blocks if not _MASTHEAD_NOISE.search(b)]
    n = len(blocks)
    stories: list[StoryCandidate] = []

    i = 0
    while i < n:
        wc = _word_count(blocks[i])
        if not (min_headline_words <= wc <= max_headline_words):
            i += 1  # long orphan block or junk fragment with no preceding headline
            continue

        # scan past up to `lookahead_blocks` short blocks (byline/dateline/subhead)
        j = i + 1
        skipped = 0
        while j < n and skipped < lookahead_blocks and _word_count(blocks[j]) <= max_headline_words:
            j += 1
            skipped += 1

        if j < n and _word_count(blocks[j]) > max_headline_words:
            body_parts = [blocks[k].replace("\n", " ").strip() for k in range(i + 1, j)]
            while j < n and _word_count(blocks[j]) > max_headline_words:
                body_parts.append(blocks[j].replace("\n", " ").strip())
                j += 1
            body = " ".join(p for p in body_parts if p).strip()
            if _word_count(body) >= min_body_words:
                stories.append(StoryCandidate(title=blocks[i].replace("\n", " ").strip(), body=body))
            i = j
        else:
            i += 1  # no body found within the lookahead window — drop this candidate

    return stories
