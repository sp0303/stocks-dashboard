"""Groww "Order history for stocks" export: detected by header, only executed orders become
trades, price = value / quantity, dates converted from "DD-MM-YYYY HH:MM AM/PM". Synthetic file."""
import io
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import ingestion

HEADER = ["Stock name", "Symbol", "ISIN", "Type", "Quantity", "Value", "Exchange",
          "Exchange Order Id", "Execution date and time", "Order status"]


def _groww_xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Test Person"])
    ws.append(["Unique Client Code", "1234567890"])
    ws.append([])
    ws.append(["Order history for stocks"])
    ws.append([])
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_groww_executed_orders_become_trades():
    f = _groww_xlsx([
        ["ACME LTD", "ACME", "INE000A01010", "BUY", 34, 14586.0, "NSE", "31096698", "03-09-2026 03:30 PM", "Executed"],
        ["ACME LTD", "ACME", "INE000A01010", "SELL", 34, 30885.6, "NSE", "1400000000300109", "04-09-2026 10:09 AM", "Executed"],
        ["ACME LTD", "ACME", "INE000A01010", "BUY", 10, 5000.0, "NSE", "999", "05-09-2026 11:00 AM", "Cancelled"],
    ])
    p = ingestion.parse_tradebook(f)
    assert p.errors == []
    assert p.client_id == "1234567890"
    assert len(p.trades) == 2                                   # cancelled order skipped
    buy, sell = p.trades
    assert (buy["trade_type"], buy["trade_date"], buy["price"]) == ("buy", "2026-09-03", 429.0)
    assert buy["order_execution_time"] == "2026-09-03 15:30:00"
    assert sell["trade_type"] == "sell" and round(sell["price"], 2) == 908.4
    assert buy["exchange"] == "NSE" and buy["segment"] == "EQ"
    assert buy["fingerprint"] != sell["fingerprint"]


def test_groww_reupload_fingerprints_are_stable():
    rows = [["ACME LTD", "ACME", "INE000A01010", "BUY", 34, 14586.0, "NSE", "31096698", "03-09-2026 03:30 PM", "Executed"]]
    a = ingestion.parse_tradebook(_groww_xlsx(rows)).trades[0]["fingerprint"]
    b = ingestion.parse_tradebook(_groww_xlsx(rows)).trades[0]["fingerprint"]
    assert a == b
