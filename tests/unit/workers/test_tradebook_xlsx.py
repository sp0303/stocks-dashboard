"""Excel tradebook parser: Zerodha + Groww layouts, rejects (R13), fingerprints match v1."""
from __future__ import annotations

import hashlib
import io
from datetime import date

import openpyxl
from pi_workers.tradebook_store import fingerprint
from pi_workers.tradebook_xlsx import is_xlsx, parse_tradebook_xlsx

ZHEAD = ["Symbol", "ISIN", "Trade Date", "Exchange", "Segment", "Series", "Trade Type",
         "Auction", "Quantity", "Price", "Trade ID", "Order ID", "Order Execution Time"]


def _book(rows: list[list], banner: list[list] | None = None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in banner or []:
        ws.append(r)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zerodha(*trades: list) -> bytes:
    banner = [[None, "Client ID", "ab1234"], [None, "Tradebook for Equity from 2025-04-01 to 2026-03-31"], []]
    return _book([ZHEAD, *trades], banner)


def test_zerodha_rows_and_account_banner():
    data = _zerodha(
        ["abc", "INE000A01010", "2025-05-02", "nse", "", "EQ", "buy", False, 10, 100.5, "T1", "O1", "2025-05-02T09:30:01"],
        ["XYZ", "INE000B01010", "2025-05-03", "BSE", "EQ", "A", "sell", False, 5, 50, "T2", "O2", "2025-05-03T10:00:00"],
    )
    out = parse_tradebook_xlsx(data)
    assert out.layout == "ZERODHA" and out.file_client_code == "AB1234"
    assert (out.date_from, out.date_to) == ("2025-04-01", "2026-03-31")
    assert len(out.rows) == 2 and not out.rejects
    a, b = out.rows
    assert a["symbol"] == "ABC" and a["exchange"] == "NSE" and a["segment"] == "EQ"  # blank segment = equity (R9)
    assert a["trade_date"] == date(2025, 5, 2) and a["trade_value"] == 1005.0
    assert a["executed_at"].utcoffset().total_seconds() == 19800  # IST
    assert b["trade_type"] == "sell" and b["series"] == "A"
    assert "charges" not in a  # unknown, not 0 (R15)
    assert a["extra"]["Symbol".lower()] == "abc"


def test_rejected_rows_keep_reason_and_row_number():
    data = _zerodha(
        ["ABC", "", "2025-05-02", "NSE", "EQ", "EQ", "buy", False, 0, 100, "T1", "O1", ""],
        ["ABC", "", "not-a-date", "NSE", "EQ", "EQ", "buy", False, 1, 100, "T2", "O2", ""],
        ["ABC", "", "2025-05-02", "NSE", "EQ", "EQ", "hold", False, 1, 100, "T3", "O3", ""],
        ["ABC", "", "2025-05-02", "NSE", "EQ", "EQ", "buy", False, 1, 0, "T4", "O4", ""],
        ["OK", "", "2025-05-02", "NSE", "EQ", "EQ", "buy", False, 1, 10, "T5", "O5", ""],
    )
    out = parse_tradebook_xlsx(data)
    assert [r["symbol"] for r in out.rows] == ["OK"]
    reasons = {n: why for n, why, _ in out.rejects}
    assert len(reasons) == 4 and all(n >= 5 for n in reasons)
    assert any("quantity" in w for w in reasons.values()) and any("date" in w for w in reasons.values())
    assert any("trade_type" in w for w in reasons.values()) and any("price" in w for w in reasons.values())


def test_groww_executed_rows_only_and_price_from_value():
    head = ["Stock name", "Symbol", "ISIN", "Type", "Quantity", "Value", "Exchange",
            "Exchange Order ID", "Execution date and time", "Order status"]
    data = _book([
        head,
        ["A", "AAA", "INE1", "BUY", 4, 400, "NSE", "G1", "03-09-2026 03:30 PM", "Executed"],
        ["B", "BBB", "INE2", "BUY", 1, 10, "NSE", "G2", "03-09-2026 03:31 PM", "Cancelled"],
    ])
    out = parse_tradebook_xlsx(data)
    assert out.layout == "GROWW" and len(out.rows) == 1 and not out.rejects
    r = out.rows[0]
    assert r["price"] == 100.0 and r["trade_date"] == date(2026, 9, 3) and r["broker_trade_id"] == "G1"


def test_not_a_tradebook_and_corrupt_and_upstox_are_rejected_not_crashed():
    assert parse_tradebook_xlsx(b"PK\x03\x04garbage").rejects[0][1].startswith("Cannot open workbook")
    assert "Header row not found" in parse_tradebook_xlsx(_book([["a", "b"], [1, 2]])).rejects[0][1]
    up = parse_tradebook_xlsx(_book([["Date", "Company", "Side", "Quantity", "Price"], ["2025-01-01", "X", "Buy", 1, 1]]))
    assert up.layout == "UPSTOX" and not up.rows and "Upstox" in up.rejects[0][1]


def test_is_xlsx_by_magic_or_name():
    assert is_xlsx("a.csv", b"PK\x03\x04...") and is_xlsx("A.XLSX", b"") and not is_xlsx("a.csv", b"symbol,")


def test_fingerprint_is_the_v1_recipe():
    row = {"trade_date": date(2025, 5, 2), "symbol": "ABC", "trade_type": "buy",
           "quantity": 10.0, "price": 100.5, "broker_trade_id": "T1"}
    expected = hashlib.sha1(b"AB1234|2025-05-02|ABC|buy|10.0|100.5|T1").hexdigest()
    assert fingerprint("AB1234", row) == expected
    assert fingerprint("OTHER", row) != expected
