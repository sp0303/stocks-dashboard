"""Page -> story-candidate segmentation. Pure, no I/O.

Fixtures are shaped like real Tesseract PSM-3 output on ET newsprint: paragraph
blocks separated by blank lines, a short headline block, sometimes a short
byline/dateline block, then a longer body paragraph.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.news.segmenter import segment_page

_BODY_1 = (
    "The Supreme Court on Monday asked the Centre to ground airlines that do not "
    "follow airfare rules, even as the government said the final rules to regulate "
    "airfares in the country would be finalised within three weeks, reports Indu "
    "Bhan. The top court also perused the draft rules to regulate airfares that "
    "were submitted by the government in a sealed cover."
)

_BODY_2 = (
    "Mumbai: Aegis Logistics, a leading Indian importer, storage and distribution "
    "company for oil and gas, is in advanced discussions to acquire UAE-based "
    "Tristar, the largest privately owned liquid logistics company in West Asia. "
    "The Mumbai-based company has initiated discussions with a group of European "
    "and Indian private sector lenders for acquisition financing."
)


def test_single_story_headline_plus_body():
    page = f"SC: Ground Airlines if Airfare Caps Violated\n\n{_BODY_1}"
    stories = segment_page(page)
    assert len(stories) == 1
    assert stories[0].title == "SC: Ground Airlines if Airfare Caps Violated"
    assert stories[0].body == _BODY_1


def test_byline_between_headline_and_body_is_absorbed_not_a_new_story():
    page = (
        "Aegis Logistics in Talks to Buy UAE Tristar for $1.5b\n\n"
        "Arijit Barman & Forum Gandhi\n\n"
        f"{_BODY_2}"
    )
    stories = segment_page(page)
    assert len(stories) == 1
    assert stories[0].title == "Aegis Logistics in Talks to Buy UAE Tristar for $1.5b"
    assert "Arijit Barman" in stories[0].body  # byline folded into body, not lost
    assert "Aegis Logistics, a leading Indian" in stories[0].body


def test_masthead_noise_is_filtered_and_does_not_swallow_real_headline():
    page = (
        "WWW.ECONOMICTIMES.COM\n\n"
        "THE ECONOMIC TIMES\n\n"
        "BENNETT, COLEMAN & CO. LTD. | ESTD. 1838 VOL. 66 NO. 195\n\n"
        "SC: Ground Airlines if Airfare Caps Violated\n\n"
        f"{_BODY_1}"
    )
    stories = segment_page(page)
    assert len(stories) == 1
    assert stories[0].title == "SC: Ground Airlines if Airfare Caps Violated"
    assert "BENNETT" not in stories[0].title
    assert "ECONOMIC TIMES" not in stories[0].title


def test_multiple_stories_on_one_page():
    page = (
        "SC: Ground Airlines if Airfare Caps Violated\n\n"
        f"{_BODY_1}\n\n"
        "Aegis Logistics in Talks to Buy UAE Tristar for $1.5b\n\n"
        "Arijit Barman & Forum Gandhi\n\n"
        f"{_BODY_2}"
    )
    stories = segment_page(page)
    assert len(stories) == 2
    assert stories[0].title == "SC: Ground Airlines if Airfare Caps Violated"
    assert stories[1].title == "Aegis Logistics in Talks to Buy UAE Tristar for $1.5b"


def test_multi_paragraph_story_body_all_absorbed():
    page = (
        "SC: Ground Airlines if Airfare Caps Violated\n\n"
        f"{_BODY_1}\n\n"
        f"{_BODY_2}"
    )
    stories = segment_page(page)
    assert len(stories) == 1
    assert _BODY_1 in stories[0].body
    assert _BODY_2 in stories[0].body


def test_ad_heavy_page_with_no_real_body_yields_no_stories():
    page = "SPECIAL OFFER\n\n50% OFF TODAY\n\nTerms and conditions apply\n\nCall now"
    assert segment_page(page) == []


def test_trailing_headline_with_no_body_is_dropped():
    page = f"SC: Ground Airlines if Airfare Caps Violated\n\n{_BODY_1}\n\nAnd Finally"
    stories = segment_page(page)
    assert len(stories) == 1  # the trailing short fragment isn't a phantom 2nd story


def test_empty_and_none_input():
    assert segment_page("") == []
    assert segment_page(None) == []


def test_line_break_within_headline_is_joined_with_space():
    page = f"SC: Ground Airlines if\nAirfare Caps Violated\n\n{_BODY_1}"
    stories = segment_page(page)
    assert stories[0].title == "SC: Ground Airlines if Airfare Caps Violated"


def test_body_below_min_words_is_dropped_as_noise():
    page = "Breaking News\n\nMore details soon."
    assert segment_page(page) == []
