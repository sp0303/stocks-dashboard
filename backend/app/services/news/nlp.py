"""Summary / sentiment / event classification — offline-first, tiered.

`ContentEnricher` is the pluggable interface (same provider-ABC shape as
`market_data.MarketDataProvider`). Three tiers, offline-first per the news-pipeline plan:

  - RuleBasedEnricher   — default, always available, zero external calls/deps. Lead-
    paragraph extractive summary (news' own inverted-pyramid convention), a curated
    finance-lexicon sentiment scorer, and keyword/regex event-type rules. Same
    "curated map, extend freely" philosophy `securities.py` already uses.
  - LocalModelEnricher  — optional, talks to a locally-running Ollama server for
    better summary/sentiment quality. Nothing leaves the machine. Falls back to
    RuleBasedEnricher on any failure (not running, model missing, timeout).
  - ClaudeEnricher       — optional, cloud, requires ANTHROPIC_API_KEY. Falls back the
    same way. Uses httpx directly (already a dependency) rather than adding the
    `anthropic` SDK, keeping this tier a zero-new-dependency opt-in.

**Privacy boundary enforced by construction:** every `enrich()` signature only accepts
(title, body) — public article text. Holdings never enter this module.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Shared result shape
# --------------------------------------------------------------------------- #


@dataclass
class Enrichment:
    summary: str
    sentiment: str  # POSITIVE | NEGATIVE | NEUTRAL
    sentiment_score: float  # -1..1
    event_type: str  # EARNINGS | DIVIDEND | SPLIT | MERGER | RATING | BOARD_MEETING | MACRO | GENERIC
    tier: str = "rules"  # which enricher actually produced this


class ContentEnricher(ABC):
    @abstractmethod
    def enrich(self, title: str, body: str) -> Enrichment:
        """Public article text in, structured enrichment out. No holdings, ever."""


# --------------------------------------------------------------------------- #
# Tier 1 — RuleBasedEnricher (default)
# --------------------------------------------------------------------------- #

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Finance-news sentiment lexicon — curated, extend freely (same pattern as
# securities.py's sector map). Deliberately biased toward market-report vocabulary
# rather than a generic sentiment wordlist.
_POSITIVE_WORDS = frozenset(
    """surge surges surged rally rallies rallied jump jumps jumped gain gains gained
    beat beats record rise rises risen soar soars soared rebound rebounds rebounded
    upgrade upgrades upgraded outperform outperforms bullish strong strength robust
    profit profits profitable growth grows grew expand expands expanded boost boosts
    boosted win wins won advance advances advanced climb climbs climbed""".split()
)
_NEGATIVE_WORDS = frozenset(
    """slump slumps slumped fall falls fell decline declines declined drop drops dropped
    plunge plunges plunged miss misses missed downgrade downgrades downgraded
    bearish weak weakness probe probes probed fraud default defaults defaulted
    loss losses losing crash crashes crashed slide slides slid tumble tumbles
    tumbled warn warns warned cut cuts curbs curb restriction restrictions
    lawsuit lawsuits penalty penalties fine fined layoff layoffs job cuts""".split()
)
_SENTIMENT_NEUTRAL_BAND = 0.15

# Event-type keyword rules, checked in this priority order (most specific first) so a
# story mentioning both "results" and "board meeting" lands on the more informative tag.
_EVENT_RULES: list[tuple[str, re.Pattern]] = [
    ("EARNINGS", re.compile(r"\b(q[1-4]\b|quarterly results|earnings|net profit|net loss|revenue grew|revenue fell)")),
    ("DIVIDEND", re.compile(r"\bdividend\b")),
    ("SPLIT", re.compile(r"\b(stock split|bonus shares|bonus issue)\b")),
    ("MERGER", re.compile(r"\b(merger|acquisition|acquire[sd]?|stake sale|takeover|to buy\b)")),
    ("RATING", re.compile(r"\b(upgrade[sd]?|downgrade[sd]?|rating|outlook (raised|cut|revised))\b")),
    ("BOARD_MEETING", re.compile(r"\bboard meeting\b")),
    ("MACRO", re.compile(r"\b(rbi|reserve bank|inflation|gdp|union budget|repo rate|rupee|sensex|nifty)\b")),
]


def _lead_summary(title: str, body: str, max_sentences: int = 2, max_chars: int = 220) -> str:
    """Extractive summary: the lead sentence(s) of the body. News writing already
    front-loads the who/what/why (the "inverted pyramid"), so this is a legitimate,
    well-known offline summarization technique for news, not a shortcut hack."""
    text = (body or title or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    out = " ".join(sentences[:max_sentences]) if sentences else text
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0] + "…"
    return out


def _score_sentiment(text: str) -> tuple[str, float]:
    words = re.findall(r"[a-z]+", text.lower())
    pos = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg = sum(1 for w in words if w in _NEGATIVE_WORDS)
    if pos + neg == 0:
        return "NEUTRAL", 0.0
    score = round((pos - neg) / (pos + neg), 2)
    if score > _SENTIMENT_NEUTRAL_BAND:
        label = "POSITIVE"
    elif score < -_SENTIMENT_NEUTRAL_BAND:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"
    return label, score


def _classify_event(text: str) -> str:
    lowered = text.lower()
    for event_type, pattern in _EVENT_RULES:
        if pattern.search(lowered):
            return event_type
    return "GENERIC"


class RuleBasedEnricher(ContentEnricher):
    def enrich(self, title: str, body: str) -> Enrichment:
        combined = f"{title or ''} {body or ''}"
        sentiment, score = _score_sentiment(combined)
        return Enrichment(
            summary=_lead_summary(title, body),
            sentiment=sentiment,
            sentiment_score=score,
            event_type=_classify_event(combined),
            tier="rules",
        )


# --------------------------------------------------------------------------- #
# Tier 2 — LocalModelEnricher (optional, Ollama)
# --------------------------------------------------------------------------- #

_LOCAL_PROMPT = """Summarize this news snippet in one short sentence, and classify its \
sentiment and event type.

Title: {title}
Body: {body}

Respond with ONLY compact JSON, no other text:
{{"summary": "...", "sentiment": "POSITIVE|NEGATIVE|NEUTRAL", "sentiment_score": -1..1, \
"event_type": "EARNINGS|DIVIDEND|SPLIT|MERGER|RATING|BOARD_MEETING|MACRO|GENERIC"}}"""


class LocalModelEnricher(ContentEnricher):
    """Talks to a locally-running Ollama server. Genuinely offline (nothing leaves the
    machine) but requires Ollama installed and a model pulled. Falls back to
    RuleBasedEnricher on any failure — the pipeline never blocks on an unavailable
    local model."""

    def __init__(self, base_url: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._fallback = RuleBasedEnricher()

    def enrich(self, title: str, body: str) -> Enrichment:
        try:
            import httpx

            prompt = _LOCAL_PROMPT.format(title=title or "", body=(body or "")[:2000])
            r = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            payload = json.loads(r.json()["response"])
            return Enrichment(
                summary=str(payload["summary"])[:220],
                sentiment=str(payload.get("sentiment", "NEUTRAL")).upper(),
                sentiment_score=float(payload.get("sentiment_score", 0.0)),
                event_type=str(payload.get("event_type", "GENERIC")).upper(),
                tier="local",
            )
        except Exception:
            return self._fallback.enrich(title, body)


# --------------------------------------------------------------------------- #
# Tier 3 — ClaudeEnricher (optional, cloud)
# --------------------------------------------------------------------------- #

_CLAUDE_PROMPT = _LOCAL_PROMPT  # same instruction shape


class ClaudeEnricher(ContentEnricher):
    """Cloud tier for when quality matters more than the offline constraint. Uses
    httpx directly against the Messages API (already a dependency) rather than adding
    the `anthropic` SDK, so this stays a zero-new-dependency opt-in. Falls back to
    RuleBasedEnricher on any failure."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022", timeout: float = 20.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._fallback = RuleBasedEnricher()

    def enrich(self, title: str, body: str) -> Enrichment:
        if not self.api_key:
            return self._fallback.enrich(title, body)
        try:
            import httpx

            prompt = _CLAUDE_PROMPT.format(title=title or "", body=(body or "")[:2000])
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            text = r.json()["content"][0]["text"]
            payload = json.loads(text)
            return Enrichment(
                summary=str(payload["summary"])[:220],
                sentiment=str(payload.get("sentiment", "NEUTRAL")).upper(),
                sentiment_score=float(payload.get("sentiment_score", 0.0)),
                event_type=str(payload.get("event_type", "GENERIC")).upper(),
                tier="claude",
            )
        except Exception:
            return self._fallback.enrich(title, body)


# --------------------------------------------------------------------------- #
# Factory — reads config, always with automatic fallback toward rules
# --------------------------------------------------------------------------- #


def get_enricher(tier: str, *, ollama_url: str = "", ollama_model: str = "", anthropic_api_key: str = "") -> ContentEnricher:
    if tier == "local" and ollama_url and ollama_model:
        return LocalModelEnricher(ollama_url, ollama_model)
    if tier == "claude" and anthropic_api_key:
        return ClaudeEnricher(anthropic_api_key)
    return RuleBasedEnricher()
