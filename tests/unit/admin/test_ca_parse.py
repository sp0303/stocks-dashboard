"""NSE corporate-action parsing (R8: only parsed SPLIT/BONUS carry a quantity multiplier)."""

from datetime import date

import pytest
from pi_api.modules.admin.ca_parse import (
    iso_date,
    normalize,
    parse_action,
    parse_equity_list,
)


@pytest.mark.parametrize(
    "subject,kind,mult",
    [
        (
            "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
            "SPLIT",
            5.0,
        ),
        ("Bonus 1:1", "BONUS", 2.0),
        ("Bonus 3:2", "BONUS", 2.5),
        ("Stock Split", "SPLIT", None),
        ("Demerger", "DEMERGER", None),
        ("Buy Back", "BUYBACK", None),
        ("Rights 1:5 @ Premium Rs 100/-", "RIGHTS", None),
        ("Annual General Meeting", "OTHER", None),
    ],
)
def test_parse_action(subject, kind, mult):
    p = parse_action(subject)
    assert p["type"] == kind
    assert p["qty_multiplier"] == (pytest.approx(mult) if mult else None)


def test_dividend_amount():
    assert (
        parse_action("Interim Dividend - Rs 5.50 Per Share")["amount_per_share"] == 5.5
    )


def test_iso_date():
    assert iso_date("05-Jun-2026") == date(2026, 6, 5)
    assert iso_date("-") is None and iso_date("junk") is None


def test_normalize_key_and_skips():
    rec = {
        "symbol": "abc",
        "isin": "INE1",
        "exDate": "05-Jun-2026",
        "subject": "Bonus 1:1",
    }
    row = normalize(rec)
    assert row["symbol"] == "ABC" and row["key"] == "INE1|2026-06-05|BONUS|Bonus 1:1"
    assert normalize({**rec, "exDate": "-"}) is None
    assert normalize({**rec, "subject": "AGM"}) is None


def test_parse_equity_list():
    text = "SYMBOL,NAME OF COMPANY\nTCS,Tata\ninfy,Infosys\n\nTCS,dup\n"
    assert parse_equity_list(text) == ["INFY", "TCS"]
    assert parse_equity_list("") == []
