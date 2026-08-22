"""Entity/company linking — pure, no I/O. Fixture headlines -> expected symbols + method.

Per LLD 06 sec5 / the news-pipeline plan: match cascade EXACT -> ALIAS -> FUZZY, tolerant
of OCR word-joining (the dominant real-world OCR error mode found while testing
pdf_extract.py — see test_pdf_extract.py's module docstring).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.news.linker import link_text


def _methods(text):
    return {r.symbol: r.match_method for r in link_text(text)}


def test_exact_ticker_match():
    r = link_text("RELIANCE shares closed higher on Thursday")
    assert len(r) == 1
    assert r[0].symbol == "RELIANCE"
    assert r[0].match_method == "EXACT"
    assert r[0].confidence == 1.0


def test_alias_company_name_match():
    r = link_text("Infosys reported a strong quarter")
    assert len(r) == 1
    assert r[0].symbol == "INFY"
    assert r[0].match_method == "ALIAS"
    assert 0.8 <= r[0].confidence < 1.0


def test_multiword_alias_match():
    r = link_text("Reliance Industries is in talks to acquire a stake")
    syms = _methods("Reliance Industries is in talks to acquire a stake")
    assert "RELIANCE" in syms
    # "reliance" alone is already the ticker -> EXACT, which is fine (cheaper tier wins)
    assert syms["RELIANCE"] in ("EXACT", "ALIAS")
    assert r


def test_multiple_companies_in_one_headline():
    syms = _methods("TCS and Infosys both reported earnings this week")
    assert syms.get("TCS") == "EXACT"
    assert syms.get("INFY") == "ALIAS"


def test_word_joined_ocr_noise_still_partially_recoverable():
    # Real OCR failure mode: "Tata Motors" -> "tatamotors" (space dropped). The
    # collapsed-string check should still catch this even though EXACT ticker
    # matching on "TATAMOTORS" (an 11-char run) requires the substring intact.
    text = "tatamotors posted a strong recovery in exports"
    r = link_text(text)
    symbols = {x.symbol for x in r}
    assert "TATAMOTORS" in symbols


def test_fuzzy_partial_alias_with_one_word_dropped():
    # "Tata Consultancy" (2 of 3 alias words for TCS's "tata consultancy services")
    # should not be missed just because "services" got OCR-mangled away.
    text = "Tata Consultancy Servces posted record profit"  # "Services" OCR-mangled
    syms = _methods(text)
    assert "TCS" in syms  # matches TCS ticker token itself here anyway
    # a case with NO literal ticker token present, only a degraded multi-word alias:
    text2 = "tata consultancy servces reported growth"
    r2 = link_text(text2)
    assert any(x.symbol == "TCS" for x in r2)


def test_unknown_company_returns_no_match():
    r = link_text("Veolia has emerged as frontrunner to acquire ReSustainability")
    assert r == []


def test_empty_text_returns_no_match():
    assert link_text("") == []
    assert link_text(None or "") == []


def test_short_ticker_not_bare_matched_to_avoid_false_positives():
    # "LT" (Larsen & Toubro) is only 2 chars — below _MIN_EXACT_TICKER_LEN, so a
    # stray "lt" abbreviation in prose must not false-positive into a match.
    r = link_text("the report was published at 5 pm lt")
    assert not any(x.symbol == "LT" for x in r)
    # but the real company name still links it
    r2 = link_text("Larsen & Toubro won a major infrastructure order")
    assert any(x.symbol == "LT" for x in r2)


def test_results_sorted_by_confidence_descending():
    r = link_text("RELIANCE gained while Infosys also advanced")
    assert r[0].confidence >= r[-1].confidence
