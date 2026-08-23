"""Equity tradebook (.xlsx) parser — Zerodha and Upstox exports.

Zerodha layout:
  row 1 : ["Client ID", "<client>"]
  row 4 : ["Tradebook for Equity from <from> to <to>"]
  row 6 : header  -> Symbol, ISIN, Trade Date, Exchange, Segment, Series,
                     Trade Type, Auction, Quantity, Price, Trade ID, Order ID,
                     Order Execution Time
  row 7+: data rows

Upstox layout:
  row 5 : ["UCC", "<client code>"]
  row 11: header  -> Date, Company, Amount, Exchange, Segment, Scrip Code,
                     Instrument Type, Strike Price, Expiry, Trade Num,
                     Trade Time, Side, Quantity, Price
  row 12+: data rows
  Upstox has no dedicated "Symbol" column — "Company" holds a display name
  (often truncated), resolved to an NSE ticker via company_lookup. It also has
  no ISIN, series, auction flag or order id, so those are left blank.

No charges column exists in either export, so cost basis is price-based (charges = 0).
Dedupe fingerprint is built per row; the store enforces uniqueness on it.

Upstox workbooks sometimes omit a correct <dimension> tag, which makes openpyxl's
read_only mode stop after the first row — so we always load fully (not read_only).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import openpyxl

from . import company_lookup

ZERODHA_HEADER_MAP = {
    "symbol": "symbol",
    "isin": "isin",
    "trade date": "trade_date",
    "exchange": "exchange",
    "segment": "segment",
    "series": "series",
    "trade type": "trade_type",
    "auction": "auction",
    "quantity": "quantity",
    "price": "price",
    "trade id": "trade_id",
    "order id": "order_id",
    "order execution time": "order_execution_time",
}

UPSTOX_HEADER_MAP = {
    "date": "trade_date",
    "company": "symbol",
    "exchange": "exchange",
    "segment": "segment",
    "trade num": "trade_id",
    "trade time": "trade_time",
    "side": "trade_type",
    "quantity": "quantity",
    "price": "price",
}


@dataclass
class ParsedTradebook:
    client_id: str | None
    date_from: str | None
    date_to: str | None
    trades: list[dict]
    errors: list[str]


def _fingerprint(client_id: str, t: dict) -> str:
    key = "|".join(
        str(x)
        for x in (
            client_id,
            t.get("trade_date"),
            t.get("symbol"),
            t.get("trade_type"),
            t.get("quantity"),
            t.get("price"),
            t.get("trade_id"),
        )
    )
    return hashlib.sha1(key.encode()).hexdigest()


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _norm(v):
    return str(v).strip() if v is not None else ""


def parse_tradebook(source, client_id_hint: str | None = None) -> ParsedTradebook:
    """Parse an xlsx path or file-like object into normalized trades.

    Supports both Zerodha and Upstox equity tradebook exports (detected from the
    header row). Loaded fully (not read_only) since some Upstox exports carry a
    stale <dimension> tag that truncates read_only iteration to a single row.
    """
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    client_id = client_id_hint
    date_from = date_to = None
    header_idx = None
    header_cols: list[str] = []
    header_map: dict[str, str] = {}
    errors: list[str] = []

    # Exports may include a leading blank column, so scan every cell in a row
    # rather than assuming a fixed column index.
    for i, row in enumerate(rows):
        if not row:
            continue
        cells = [_norm(c) for c in row]
        lower = [c.lower() for c in cells]
        for j, c in enumerate(lower):
            if c in ("client id", "ucc") and j + 1 < len(cells) and cells[j + 1]:
                client_id = cells[j + 1]
            if c.startswith("tradebook for"):
                m = re.search(r"from\s+([\d-]+)\s+to\s+([\d-]+)", cells[j])
                if m:
                    date_from, date_to = m.group(1), m.group(2)
        if "symbol" in lower and "isin" in lower:
            header_idx, header_cols, header_map = i, lower, ZERODHA_HEADER_MAP
            break
        if "company" in lower and "side" in lower:
            header_idx, header_cols, header_map = i, lower, UPSTOX_HEADER_MAP
            break

    if header_idx is None:
        return ParsedTradebook(client_id, date_from, date_to, [], ["Header row not found"])

    is_upstox = header_map is UPSTOX_HEADER_MAP
    fields = [header_map.get(h) for h in header_cols]
    trades: list[dict] = []
    for r_i, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not row or all(c is None or _norm(c) == "" for c in row):
            continue
        rec: dict = {}
        for col, field in enumerate(fields):
            if field is None or col >= len(row):
                continue
            rec[field] = row[col]
        if not rec.get("symbol"):
            continue
        try:
            trade_date = _norm(rec.get("trade_date"))[:10]
            order_execution_time = _norm(rec.get("order_execution_time"))
            if not order_execution_time and rec.get("trade_time"):
                order_execution_time = f"{trade_date} {_norm(rec.get('trade_time'))}"
            symbol = _norm(rec.get("symbol")).upper()
            if is_upstox:
                symbol = company_lookup.resolve_symbol(symbol)
            trade = {
                "symbol": symbol,
                "isin": _norm(rec.get("isin")),
                "trade_date": trade_date,
                "exchange": _norm(rec.get("exchange")).upper(),
                "segment": _norm(rec.get("segment")),
                "series": _norm(rec.get("series")),
                "trade_type": _norm(rec.get("trade_type")).lower(),
                "auction": _norm(rec.get("auction")) not in ("", "0", "false", "False"),
                "quantity": float(rec.get("quantity") or 0),
                "price": float(rec.get("price") or 0),
                "trade_id": _norm(rec.get("trade_id")),
                "order_id": _norm(rec.get("order_id")),
                "order_execution_time": order_execution_time,
                "charges": 0.0,
            }
            trade["trade_value"] = round(trade["quantity"] * trade["price"], 4)
            if trade["trade_type"] not in ("buy", "sell"):
                errors.append(f"row {r_i}: bad trade_type '{trade['trade_type']}'")
                continue
            trade["fingerprint"] = _fingerprint(client_id or "", trade)
            trades.append(trade)
        except (ValueError, TypeError) as e:
            errors.append(f"row {r_i}: {e}")

    return ParsedTradebook(client_id, date_from, date_to, trades, errors)
