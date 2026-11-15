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

#: Groww "Order history for stocks" export: one row per order, no price column (Value is
#: quantity × average fill price), dates as "03-09-2026 03:30 PM", and cancelled/rejected
#: orders included — only "Executed" rows are trades.
GROWW_HEADER_MAP = {
    "symbol": "symbol",
    "isin": "isin",
    "type": "trade_type",
    "quantity": "quantity",
    "value": "trade_value",
    "exchange": "exchange",
    "exchange order id": "order_id",
    "execution date and time": "groww_executed_at",
    "order status": "order_status",
}


def _groww_row(rec: dict) -> dict | None:
    """Map a Groww order row onto the Zerodha-shaped fields the loop below expects.
    Returns None for orders that did not execute."""
    from datetime import datetime as dt

    if _norm(rec.get("order_status")).lower() != "executed":
        return None
    ts = dt.strptime(_norm(rec.get("groww_executed_at")), "%d-%m-%Y %I:%M %p")
    qty = float(rec.get("quantity") or 0)
    value = float(rec.get("trade_value") or 0)
    rec["trade_date"] = ts.strftime("%Y-%m-%d")
    rec["order_execution_time"] = ts.strftime("%Y-%m-%d %H:%M:%S")
    rec["price"] = round(value / qty, 4) if qty else 0
    rec["trade_id"] = rec.get("order_id")          # Groww gives no trade id; one row per order
    rec["segment"] = rec.get("segment") or "EQ"
    return rec


@dataclass
class ParsedTradebook:
    client_id: str | None
    date_from: str | None
    date_to: str | None
    trades: list[dict]
    errors: list[str]
    # The account code printed in the file itself (None when the export carries none),
    # kept apart from client_id, which falls back to the caller's hint.
    file_client_id: str | None = None


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

    Supports Zerodha and Upstox equity tradebook exports and Groww's stock order
    history (detected from the header row). Loaded fully (not read_only) since some Upstox exports carry a
    stale <dimension> tag that truncates read_only iteration to a single row.
    """
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    client_id = client_id_hint
    file_client_id = None
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
            if c in ("client id", "ucc", "unique client code") and j + 1 < len(cells) and cells[j + 1]:
                client_id = file_client_id = cells[j + 1]
            if c.startswith("tradebook for"):
                m = re.search(r"from\s+([\d-]+)\s+to\s+([\d-]+)", cells[j])
                if m:
                    date_from, date_to = m.group(1), m.group(2)
        if "execution date and time" in lower and "symbol" in lower:
            header_idx, header_cols, header_map = i, lower, GROWW_HEADER_MAP
            break
        if "symbol" in lower and "isin" in lower:
            header_idx, header_cols, header_map = i, lower, ZERODHA_HEADER_MAP
            break
        if "company" in lower and "side" in lower:
            header_idx, header_cols, header_map = i, lower, UPSTOX_HEADER_MAP
            break

    if header_idx is None:
        return ParsedTradebook(client_id, date_from, date_to, [], ["Header row not found"], file_client_id)

    is_upstox = header_map is UPSTOX_HEADER_MAP
    is_groww = header_map is GROWW_HEADER_MAP
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
            if is_groww and _groww_row(rec) is None:
                continue                          # cancelled / rejected order, not a trade
            trade_date = _norm(rec.get("trade_date"))[:10]
            # Validate trade_date format
            from datetime import datetime as dt
            try:
                dt.strptime(trade_date, "%Y-%m-%d")
            except ValueError:
                errors.append(f"row {r_i}: invalid date format '{trade_date}', expected YYYY-MM-DD")
                continue

            order_execution_time = _norm(rec.get("order_execution_time"))
            if not order_execution_time and rec.get("trade_time"):
                order_execution_time = f"{trade_date} {_norm(rec.get('trade_time'))}"
            symbol = _norm(rec.get("symbol")).upper()
            if is_upstox:
                symbol = company_lookup.resolve_symbol(symbol)

            quantity = float(rec.get("quantity") or 0)
            price = float(rec.get("price") or 0)

            # Validate quantity and price
            if quantity <= 0:
                errors.append(f"row {r_i}: quantity must be positive, got {quantity}")
                continue
            if price <= 0:
                errors.append(f"row {r_i}: price must be positive, got {price}")
                continue

            trade = {
                "symbol": symbol,
                "isin": _norm(rec.get("isin")),
                "trade_date": trade_date,
                "exchange": _norm(rec.get("exchange")).upper(),
                "segment": _norm(rec.get("segment")),
                "series": _norm(rec.get("series")),
                "trade_type": _norm(rec.get("trade_type")).lower(),
                "auction": _norm(rec.get("auction")) not in ("", "0", "false", "False"),
                "quantity": quantity,
                "price": price,
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

    return ParsedTradebook(client_id, date_from, date_to, trades, errors, file_client_id)


# ── export: the inverse of parse_tradebook ──────────────────────────────────────

#: Zerodha's 13 tradebook columns in their original order, then four we add. The parser only
#: reads the first thirteen (it ignores headers it does not know), so an exported file can be
#: re-uploaded as-is — and, because the fingerprint is rebuilt from the same fields, every
#: row is recognised as a duplicate rather than imported twice.
EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("Symbol", "symbol"), ("ISIN", "isin"), ("Trade Date", "trade_date"),
    ("Exchange", "exchange"), ("Segment", "segment"), ("Series", "series"),
    ("Trade Type", "trade_type"), ("Auction", "auction"), ("Quantity", "quantity"),
    ("Price", "price"), ("Trade ID", "trade_id"), ("Order ID", "order_id"),
    ("Order Execution Time", "order_execution_time"),
    # extras, beyond what the broker's own file carries
    ("Trade Value", "trade_value"), ("Charges", "charges"), ("Source", "source"), ("Note", "note"),
]
_TEXT_COLUMNS = {"trade_date", "trade_id", "order_id", "order_execution_time", "isin"}


def build_tradebook_xlsx(trades: list[dict], client_code: str = "", client_name: str = "") -> bytes:
    """Every stored trade as a Zerodha-layout .xlsx.

    Layout matches the broker export (Client ID in row 1, the "Tradebook for Equity from … to …"
    banner in row 4, headers in row 6, data from row 7) so other tools that read Zerodha
    tradebooks accept it too.

    Ids are written as TEXT, never numbers: an order id is 19 digits and Excel keeps only 15
    significant digits of a numeric cell, so a numeric column would silently corrupt every
    order id on the first open-and-save. Auction is written as lowercase "true"/"false" text
    because the parser treats only "false"/"False" as false, and "FALSE" would import as true.
    """
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    rows = sorted(
        trades,
        key=lambda t: (str(t.get("trade_date", "")), str(t.get("order_execution_time", "")),
                       str(t.get("trade_id", ""))),
    )
    dates = [str(t.get("trade_date", ""))[:10] for t in rows if t.get("trade_date")]
    span = f"from {dates[0]} to {dates[-1]}" if dates else "(no trades)"

    wb = Workbook()
    ws = wb.active
    ws.title = "Tradebook"
    ws["A1"], ws["B1"] = "Client ID", client_code or ""
    if client_name:
        ws["A2"], ws["B2"] = "Client Name", client_name
    ws["A4"] = f"Tradebook for Equity {span}"
    ws["A4"].font = Font(bold=True)

    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F5597")
    for ci, (label, _key) in enumerate(EXPORT_COLUMNS, 1):
        c = ws.cell(6, ci, label)
        c.font, c.fill, c.alignment = head_font, head_fill, Alignment(horizontal="center")

    for ri, t in enumerate(rows, 7):
        for ci, (_label, key) in enumerate(EXPORT_COLUMNS, 1):
            v = t.get(key)
            if key == "auction":
                v = "true" if v else "false"
            elif key in _TEXT_COLUMNS:
                v = "" if v is None else str(v)
            elif key in ("quantity", "price", "trade_value", "charges"):
                v = float(v) if v not in (None, "") else 0.0
                if key == "quantity" and v.is_integer():
                    v = int(v)
            else:
                v = "" if v is None else v
            c = ws.cell(ri, ci, v)
            if key in _TEXT_COLUMNS:
                c.number_format = "@"

    ws.freeze_panes = "A7"
    for ci, (label, key) in enumerate(EXPORT_COLUMNS, 1):
        longest = max([len(label)] + [len(str(t.get(key, ""))) for t in rows[:500]])
        ws.column_dimensions[get_column_letter(ci)].width = min(longest + 2, 32)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
