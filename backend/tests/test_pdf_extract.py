"""PDF text extraction correctness + OCR accuracy.

Three tiers, cheapest first:
  1. Synthetic digital-text PDF -> exercises the text-layer path with no OCR, no
     external fixture, runs everywhere.
  2. Real newspaper PDF (~/Downloads/ET.pdf), page 1 only -> proves OCR actually
     recovers headlines, body-copy, entities and bylines, not just "some text".
     Skipped automatically if the file isn't present (same convention as
     test_ingestion_and_store.py's tradebook fixtures).
  3. Full 16-page OCR run -> multi-minute, opt-in via RUN_SLOW=1.

Ground truth for tier 2/3 was transcribed by hand from the ET.pdf page images.

Matching uses SUBSTRING recall on a space-collapsed token stream, not exact
word-boundary matching. This isn't test-scaffolding laxity — it's a real, observed
Tesseract failure mode on tight-kerned newsprint: adjacent words get joined
("Veolia has" -> "veoliahas", "Chandrasekaran's" -> "mannchandrasekaran's"). The
entity-linker (LLD 06 sec5) must tolerate the same thing, so this helper doubles as
the reference implementation for that requirement.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.news.pdf_extract import _readability, extract_pdf, extract_pdf_file

ET_PDF = "/home/sumanth/Downloads/ET.pdf"
HAVE_ET_PDF = Path(ET_PDF).exists()

_WORD = re.compile(r"[a-z0-9]+")


def word_recall(expected: str, ocr_text: str) -> float:
    """Fraction of `expected`'s significant words (len>=3) found in `ocr_text`,
    tolerant of OCR word-joining (see module docstring)."""
    words = [w for w in _WORD.findall(expected.lower()) if len(w) >= 3]
    if not words:
        return 1.0
    spaced = " " + " ".join(_WORD.findall(ocr_text.lower())) + " "
    collapsed = "".join(_WORD.findall(ocr_text.lower()))
    present = sum(1 for w in words if f" {w} " in spaced or w in collapsed)
    return present / len(words)


# ---------------------------------------------------------------------------
# Tier 1 — synthetic digital PDF, no OCR involved
# ---------------------------------------------------------------------------

def _make_digital_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def test_text_layer_used_when_present():
    pdf = _make_digital_pdf("Reliance Q1 profit beats estimates")
    result = extract_pdf(pdf, ocr_fallback=True)
    assert result.page_count == 1
    page = result.pages[0]
    assert page.method == "text-layer"
    assert "Reliance" in page.text
    assert "beats estimates" in page.text


def test_empty_page_without_ocr_fallback_stays_empty():
    import fitz

    doc = fitz.open()
    doc.new_page()  # blank page, no text layer
    pdf = doc.tobytes()
    doc.close()

    result = extract_pdf(pdf, ocr_fallback=False)
    assert result.pages[0].method == "empty"
    assert result.pages[0].text == ""
    assert result.pages[0].char_count == 0


def test_full_text_joins_pages_and_methods_tally():
    pdf = _make_digital_pdf("Page one body has enough characters")
    result = extract_pdf(pdf, ocr_fallback=True)
    assert result.full_text.strip() == "Page one body has enough characters"
    assert result.methods == {"text-layer": 1}


def test_page_filter_limits_extraction():
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "first page has enough characters")
    doc.new_page().insert_text((72, 72), "second page has enough characters")
    pdf = doc.tobytes()
    doc.close()

    result = extract_pdf(pdf, ocr_fallback=False, pages=[2])
    assert len(result.pages) == 1
    assert result.pages[0].page == 2
    assert "second" in result.pages[0].text


# ---------------------------------------------------------------------------
# Tier 1b — orientation self-correction (regression for rotated pages)
#
# Found while testing 3 ET editions: prospectus continuation pages are sometimes
# printed upside-down, which OCR'd to 4% gibberish until pdf_extract learned to
# retry rotations. These lock that behaviour in with a synthetic fixture (no
# dependency on any downloaded PDF).
# ---------------------------------------------------------------------------

# Dense with English function words so the readability signal has something to latch
# onto — the same property real article prose has.
_ROT_TEXT = (
    "The board of the company said that the results for the quarter were in line with "
    "what the analysts had expected and that the demand for the products would continue "
    "to grow in the year ahead as more of the customers move to the new platform."
)


def _make_rotated_image_pdf(text: str, angle: int) -> bytes:
    """Render `text` to a bitmap, rotate it by `angle`, and embed it as an image-only
    PDF page (no text layer) — forcing the OCR path on deliberately-rotated content."""
    import io

    import fitz
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1200, 1600
    img = Image.new("L", (W, H), color=255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=34)
    except TypeError:  # very old Pillow without size arg
        font = ImageFont.load_default()

    # naive word-wrap
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) > 42:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    lines.append(cur)
    y = 80
    for ln in lines:
        draw.text((80, y), ln, fill=0, font=font)
        y += 60

    img = img.rotate(angle, expand=True)
    png = io.BytesIO()
    img.save(png, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    page.insert_image(page.rect, stream=png.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def test_readability_density_separates_english_from_garbled():
    # Pure/fast: no OCR. Upright prose scores high; the same text reversed (what a
    # 180-degree page looks like to OCR) scores near zero.
    assert _readability(_ROT_TEXT) > 0.10
    assert _readability(_ROT_TEXT[::-1]) < 0.04
    assert _readability("x9 z2 qk vv") == 1.0  # too little text to judge -> no retry


def test_upside_down_page_is_recovered_by_ocr():
    pdf = _make_rotated_image_pdf(_ROT_TEXT, angle=180)
    result = extract_pdf(pdf, ocr_fallback=True)
    page = result.pages[0]
    assert page.method == "ocr"
    # Without orientation self-correction this comes back as gibberish; with it, the
    # real words are recovered.
    assert word_recall("the board of the company said the results", page.text) >= 0.7
    assert word_recall("demand for the products would continue to grow", page.text) >= 0.7


# ---------------------------------------------------------------------------
# Tier 2 — real scanned newspaper, page 1, OCR path
# ---------------------------------------------------------------------------

pytestmark_et = pytest.mark.skipif(not HAVE_ET_PDF, reason="ET.pdf fixture not present")

HEADLINES = [
    "Aegis Logistics in Talks to Buy UAE Tristar for 1.5b",
    "BJP Resets Team with Debutants and Poll Specialists",
    "Rupee Slide Chips Away at ISM Outlay",
    "Tata Sons Board Differs Over Chandra Decision",
    "Two More Air India Pilots Fail Drug Test",
    "Suntory Pegs India as 3rd Largest Mkt by 2030",
    "Banking Panel for Viksit Bharat Soon",
    "Sebi Chief Rules Out CAS Rollback",
    "ICICI Goes Past HDFC to Emerge Top MF Holding",
    "Ground Airlines if Airfare Caps Violated",
    "Mid Small-cap Cos Log Best Growth in 16 Qtrs",
    "I Squared Team Leads Race to Buy ReSL",
    "Overleveraged Microfin Borrowers on Decline",
    "Rahul Urges Soren to Meet Students",
]

ENTITIES = [
    "Aegis Logistics", "Tristar", "ADNOC", "KKR", "Veolia", "ICICI", "HDFC",
    "Tata Sons", "Air India", "Suntory", "Diageo", "Pernod Ricard", "Indel Money",
    "Nuvama", "Chandrasekaran", "Smriti Irani",
]

BYLINES = [
    "Arijit Barman", "Forum Gandhi", "Jatin Takkar", "Dia Rekhi",
    "Kala Vijayraghavan", "Maulik Vyas", "Aanya Thakur", "Sagar Malviya",
    "Indu Bhan", "Ravindra Sonavane", "Atmadip Ray",
]

BODY_SENTENCES = [
    "Aegis Logistics, a leading Indian importer, storage and distribution company "
    "for oil and gas, is in advanced discussions to acquire UAE-based Tristar",
    "the largest privately owned liquid logistics company in West Asia",
    "The Mumbai-based company, with a market capitalisation of 45,156.15 crore, has "
    "initiated discussions with a group of European and Indian private sector "
    "lenders for acquisition financing",
    "Tristar operates across 30 plus countries across West Asia, Africa, Asia, the "
    "Pacific, the Americas and Europe",
    "A debate is underway among some Tata Sons directors on how the board should "
    "formally respond to chairman N Chandrasekaran decision not to seek "
    "reappointment",
    "A weak rupee is causing what analysts and industry insiders estimate to be a "
    "net double-digit cost overrun for businesses relying on imported goods and "
    "services",
    "Suntory Global Spirits expects India to become its third-largest market by "
    "revenue by the turn of the decade",
    "adopting a focused strategy of selling locally-made whiskies along with "
    "imported Japanese and American brands",
    "The Supreme Court on Monday asked the Centre to ground airlines that do not "
    "follow airfare rules",
    "A consortium of US firm I Squared Capital and French environmental services "
    "group Veolia has emerged as frontrunner to acquire KKR-backed Re "
    "Sustainability",
]


@pytest.fixture(scope="module")
def et_page1_text() -> str:
    result = extract_pdf_file(ET_PDF, pages=[1])
    page = result.pages[0]
    assert page.method == "ocr", "page 1 of ET.pdf is a scanned image; expected OCR path"
    return page.text


@pytestmark_et
def test_page1_is_image_only_and_routes_to_ocr(et_page1_text):
    # Documents the core finding: this e-paper has no embedded text layer anywhere,
    # so extraction MUST go through OCR, not plain PyMuPDF text extraction.
    assert len(et_page1_text) > 5000


@pytestmark_et
def test_page1_headline_recall(et_page1_text):
    recalls = [word_recall(h, et_page1_text) for h in HEADLINES]
    hit_rate = sum(r >= 0.7 for r in recalls) / len(HEADLINES)
    assert hit_rate >= 0.95, f"headline recall {hit_rate:.0%} below 95% floor"


@pytestmark_et
def test_page1_entity_recall(et_page1_text):
    recalls = [word_recall(e, et_page1_text) for e in ENTITIES]
    hit_rate = sum(r >= 0.7 for r in recalls) / len(ENTITIES)
    assert hit_rate >= 0.85, f"entity recall {hit_rate:.0%} below 85% floor"


@pytestmark_et
def test_page1_byline_recall(et_page1_text):
    recalls = [word_recall(b, et_page1_text) for b in BYLINES]
    hit_rate = sum(r >= 0.7 for r in recalls) / len(BYLINES)
    assert hit_rate >= 0.85, f"byline recall {hit_rate:.0%} below 85% floor"


@pytestmark_et
def test_page1_body_matter_recall(et_page1_text):
    """The metric that matters for summarization/entity-linking: not just
    headlines, but faithful reproduction of article body paragraphs."""
    recalls = [word_recall(s, et_page1_text) for s in BODY_SENTENCES]
    avg = sum(recalls) / len(recalls)
    assert avg >= 0.85, f"body word-recall {avg:.0%} below 85% floor"


# ---------------------------------------------------------------------------
# Tier 3 — full document, opt-in only (multi-minute)
# ---------------------------------------------------------------------------

RUN_SLOW = os.environ.get("RUN_SLOW") == "1"


@pytest.mark.slow
@pytest.mark.skipif(not HAVE_ET_PDF, reason="ET.pdf fixture not present")
@pytest.mark.skipif(not RUN_SLOW, reason="set RUN_SLOW=1 to run full 16-page OCR")
def test_all_pages_extract_without_error():
    result = extract_pdf_file(ET_PDF, max_workers=4)
    assert result.page_count == 16
    assert len(result.pages) == 16
    # every page should yield a non-trivial amount of text; a near-empty page
    # signals a rendering/OCR regression, not a genuinely blank newspaper page.
    thin_pages = [p.page for p in result.pages if p.char_count < 500]
    assert len(thin_pages) <= 1, f"unexpectedly thin OCR output on pages {thin_pages}"
