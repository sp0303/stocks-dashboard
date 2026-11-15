"""Tradebook download: the inverse of the upload parser, and it must round-trip exactly."""
import io

from openpyxl import load_workbook

from app.services import ingestion


def _trade(**kw):
    t = {
        "symbol": "NUVAMA", "isin": "INE531F01023", "trade_date": "2026-02-16", "exchange": "BSE",
        "segment": "EQ", "series": "A", "trade_type": "buy", "auction": False, "quantity": 10.0,
        "price": 1271.85, "trade_id": "2379900", "order_id": "1771217052588013223",
        "order_execution_time": "2026-02-16T10:18:12", "charges": 0.0, "trade_value": 12718.5,
    }
    t.update(kw)
    t["fingerprint"] = ingestion._fingerprint("ZT1234", t)
    return t


def _export(trades, code="ZT1234"):
    return ingestion.build_tradebook_xlsx(trades, code, "Test Client")


def _sheet(blob):
    return load_workbook(io.BytesIO(blob)).active


def test_layout_matches_the_broker_file():
    ws = _sheet(_export([_trade()]))
    assert (ws["A1"].value, ws["B1"].value) == ("Client ID", "ZT1234")
    assert ws["A4"].value == "Tradebook for Equity from 2026-02-16 to 2026-02-16"
    header = [c.value for c in ws[6]][:13]
    assert header == ["Symbol", "ISIN", "Trade Date", "Exchange", "Segment", "Series", "Trade Type",
                      "Auction", "Quantity", "Price", "Trade ID", "Order ID", "Order Execution Time"]
    assert ws["A7"].value == "NUVAMA"


def test_order_id_survives_as_text_not_a_corrupted_number():
    """19 digits: Excel keeps only 15 significant digits of a number, so this must be text."""
    ws = _sheet(_export([_trade()]))
    cell = ws["L7"]
    assert cell.value == "1771217052588013223"
    assert isinstance(cell.value, str)


def test_auction_is_lowercase_text_the_parser_understands():
    """The parser only treats 'false'/'False' as false; 'FALSE' would import as an auction trade."""
    ws = _sheet(_export([_trade(auction=False)]))
    assert ws["H7"].value == "false"


def test_round_trip_reproduces_every_fingerprint_and_field():
    trades = [
        _trade(),
        _trade(trade_id="2379901", quantity=25.0, price=99.05, trade_type="sell", auction=True,
               order_execution_time="2026-02-17T09:30:00"),
        _trade(symbol="HDFCLIFE", isin="INE795G01014", exchange="NSE", trade_id="55", order_id="9"),
    ]
    parsed = ingestion.parse_tradebook(io.BytesIO(_export(trades)), client_id_hint="ZT1234")

    assert parsed.errors == []
    assert {t["fingerprint"] for t in parsed.trades} == {t["fingerprint"] for t in trades}
    by_fp = {t["fingerprint"]: t for t in parsed.trades}
    for t in trades:
        got = by_fp[t["fingerprint"]]
        for k in ("symbol", "isin", "trade_date", "exchange", "segment", "series", "trade_type",
                  "auction", "quantity", "price", "trade_id", "order_id", "order_execution_time"):
            assert got[k] == t[k], k


def test_rows_are_sorted_by_date_then_time():
    late = _trade(trade_date="2026-03-01", trade_id="2")
    early = _trade(trade_date="2026-01-05", trade_id="1")
    ws = _sheet(_export([late, early]))
    assert [ws["C7"].value, ws["C8"].value] == ["2026-01-05", "2026-03-01"]


def test_manual_and_intraday_trades_are_included_with_their_note():
    manual = _trade(symbol="NSDL", isin="", trade_id="", order_id="", segment="", series="",
                    price=800.0, source="manual", note="IPO allotment (issue price 800)")
    ws = _sheet(_export([manual]))
    header = [c.value for c in ws[6]]
    row = [c.value for c in ws[7]]
    assert row[header.index("Source")] == "manual"
    assert row[header.index("Note")] == "IPO allotment (issue price 800)"


def test_zero_price_manual_row_is_kept_in_the_file_but_not_re_imported():
    """A manual bonus credit at Rs 0 is part of the ledger and belongs in the download, but
    the upload parser deliberately rejects a Rs 0 price (a blank price must not import as
    free shares). It reports an error instead of importing it, which is the safe direction."""
    bonus = _trade(symbol="NUVAMA", price=0.0, quantity=24.0, trade_id="", order_id="",
                   source="manual", note="bonus shares (3:4)")
    ws = _sheet(_export([bonus]))
    assert ws["J7"].value == 0.0                                    # present in the export

    parsed = ingestion.parse_tradebook(io.BytesIO(_export([bonus])), client_id_hint="ZT1234")
    assert parsed.trades == []
    assert any("price must be positive" in e for e in parsed.errors)


def test_empty_book_still_produces_a_valid_file():
    ws = _sheet(_export([]))
    assert ws["A4"].value == "Tradebook for Equity (no trades)"
    assert [c.value for c in ws[6]][0] == "Symbol"
