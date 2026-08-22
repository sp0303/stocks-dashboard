"""Summary / sentiment / event classification. RuleBasedEnricher runs fully offline
(no mocks needed); LocalModelEnricher/ClaudeEnricher are tested with a fake HTTP
transport so CI never needs a live Ollama server or an API key.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.news.nlp import (
    ClaudeEnricher,
    LocalModelEnricher,
    RuleBasedEnricher,
    get_enricher,
)

# ---------------------------------------------------------------------------
# RuleBasedEnricher — fully offline, deterministic
# ---------------------------------------------------------------------------


def test_positive_sentiment_and_earnings_event():
    e = RuleBasedEnricher()
    r = e.enrich(
        "Reliance profit surges",
        "Reliance Industries reported net profit surging 20% year-on-year, beating "
        "analyst estimates, with robust growth and record revenue.",
    )
    assert r.sentiment == "POSITIVE"
    assert r.sentiment_score > 0
    assert r.event_type == "EARNINGS"
    assert r.tier == "rules"
    assert r.summary  # non-empty


def test_negative_sentiment():
    e = RuleBasedEnricher()
    r = e.enrich(
        "Shares plunge",
        "Shares plunged after a fraud probe, with the company warning of a further decline and loss.",
    )
    assert r.sentiment == "NEGATIVE"
    assert r.sentiment_score < 0


def test_neutral_sentiment_when_no_lexicon_hits():
    e = RuleBasedEnricher()
    r = e.enrich("Board meeting scheduled", "The company announced a board meeting for next Tuesday.")
    assert r.sentiment == "NEUTRAL"
    assert r.sentiment_score == 0.0


def test_mixed_sentiment_stays_near_neutral_band():
    e = RuleBasedEnricher()
    # one positive, one negative word -> score 0, inside the neutral band
    r = e.enrich("Mixed results", "Analysts said the company beat estimates but the outlook remained weak.")
    assert r.sentiment == "NEUTRAL"
    assert r.sentiment_score == 0.0


@pytest.mark.parametrize(
    "text,expected_event",
    [
        ("The company declared a dividend of Rs 5 per share", "DIVIDEND"),
        ("The board approved a stock split", "SPLIT"),
        ("The company said it would acquire a rival for $2b", "MERGER"),
        ("Analysts upgraded the stock rating", "RATING"),
        ("The RBI held a board meeting", "BOARD_MEETING"),
        ("The Reserve Bank of India cut the repo rate amid inflation concerns", "MACRO"),
        ("The company opened a new store in Mumbai", "GENERIC"),
    ],
)
def test_event_classification_rules(text, expected_event):
    e = RuleBasedEnricher()
    r = e.enrich("headline", text)
    assert r.event_type == expected_event


def test_summary_uses_lead_sentences_and_truncates_long_body():
    e = RuleBasedEnricher()
    long_body = "First sentence is the lead. " + ("Padding word. " * 40)
    r = e.enrich("Title", long_body)
    assert r.summary.startswith("First sentence is the lead.")
    assert len(r.summary) <= 221  # max_chars=220 plus the ellipsis char


def test_empty_body_falls_back_to_title():
    e = RuleBasedEnricher()
    r = e.enrich("Just a headline", "")
    assert r.summary == "Just a headline"


def test_completely_empty_input():
    e = RuleBasedEnricher()
    r = e.enrich("", "")
    assert r.summary == ""
    assert r.sentiment == "NEUTRAL"
    assert r.event_type == "GENERIC"


# ---------------------------------------------------------------------------
# LocalModelEnricher — fake Ollama transport
# ---------------------------------------------------------------------------


def test_local_model_enricher_success(monkeypatch):
    import httpx

    import json as json_mod

    payload = {
        "response": json_mod.dumps(
            {"summary": "Local summary", "sentiment": "POSITIVE", "sentiment_score": 0.7, "event_type": "EARNINGS"}
        )
    }

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    enricher = LocalModelEnricher(base_url="http://localhost:11434", model="llama3.2")
    r = enricher.enrich("T", "B")
    assert r.tier == "local"
    assert r.summary == "Local summary"
    assert r.sentiment == "POSITIVE"
    assert r.event_type == "EARNINGS"


def test_local_model_enricher_falls_back_on_connection_error(monkeypatch):
    import httpx

    def raise_conn_error(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", raise_conn_error)

    enricher = LocalModelEnricher(base_url="http://localhost:11434", model="llama3.2")
    r = enricher.enrich(
        "Reliance profit surges",
        "Reliance Industries reported net profit surging with record growth.",
    )
    assert r.tier == "rules"  # fell back
    assert r.sentiment == "POSITIVE"  # fallback still produced a real answer


def test_local_model_enricher_falls_back_on_malformed_json(monkeypatch):
    import httpx

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "not valid json"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    enricher = LocalModelEnricher(base_url="http://localhost:11434", model="llama3.2")
    r = enricher.enrich("T", "some body text")
    assert r.tier == "rules"


# ---------------------------------------------------------------------------
# ClaudeEnricher — fake Messages API transport
# ---------------------------------------------------------------------------


def test_claude_enricher_no_api_key_falls_back_without_network_call(monkeypatch):
    import httpx

    def fail_if_called(*a, **k):
        raise AssertionError("should not call the network when no API key is set")

    monkeypatch.setattr(httpx, "post", fail_if_called)

    enricher = ClaudeEnricher(api_key="")
    r = enricher.enrich("Title", "Body text")
    assert r.tier == "rules"


def test_claude_enricher_success(monkeypatch):
    import httpx
    import json as json_mod

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "content": [
                    {
                        "text": json_mod.dumps(
                            {
                                "summary": "Claude summary",
                                "sentiment": "NEGATIVE",
                                "sentiment_score": -0.5,
                                "event_type": "MERGER",
                            }
                        )
                    }
                ]
            }

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    enricher = ClaudeEnricher(api_key="fake-key")
    r = enricher.enrich("T", "B")
    assert r.tier == "claude"
    assert r.summary == "Claude summary"
    assert r.event_type == "MERGER"


def test_claude_enricher_falls_back_on_api_error(monkeypatch):
    import httpx

    def raise_http_error(*a, **k):
        raise httpx.HTTPStatusError("401", request=None, response=None)

    monkeypatch.setattr(httpx, "post", raise_http_error)

    enricher = ClaudeEnricher(api_key="fake-key")
    r = enricher.enrich("Dividend declared", "The company declared a dividend of Rs 5 per share")
    assert r.tier == "rules"
    assert r.event_type == "DIVIDEND"  # fallback still classifies correctly


# ---------------------------------------------------------------------------
# get_enricher factory
# ---------------------------------------------------------------------------


def test_factory_defaults_to_rules():
    assert isinstance(get_enricher("rules"), RuleBasedEnricher)
    assert isinstance(get_enricher("unknown-tier"), RuleBasedEnricher)


def test_factory_local_requires_config():
    # tier=local but no ollama_url/model configured -> falls back to rules at the
    # factory level, not just inside the enricher
    assert isinstance(get_enricher("local"), RuleBasedEnricher)
    assert isinstance(get_enricher("local", ollama_url="http://x", ollama_model="m"), LocalModelEnricher)


def test_factory_claude_requires_api_key():
    assert isinstance(get_enricher("claude"), RuleBasedEnricher)
    assert isinstance(get_enricher("claude", anthropic_api_key="k"), ClaudeEnricher)
