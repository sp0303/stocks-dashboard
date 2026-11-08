"""Excel (.xlsx) tradebook parser: Zerodha Console and Groww order history. Pure: bytes in, rows out.

Port of v1 ``backend/app/services/ingestion.parse_tradebook`` (v1 stays the reference, it is
not imported). Differences that follow the v2 rules:
  * every rejected row is returned with its sheet row number and a reason (R13), never dropped;
  * the full source row is kept in ``extra`` (R13);
  * charges are not in these files, so they are left unknown (R15) rather than written as 0;
  * a blank segment means equity (R9).
Upstox workbooks need v1's company-name lookup, so they are refused with a clear reason.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import openpyxl

IST = ZoneInfo("Asia/Kolkata")
MAX_ROWS = 200_000
XLSX_MAGIC = b"PK\x03\x04"

ZERODHA_MAP = {
    "symbol": "symbol", "isin": "isin", "trade date": "trade_date", "exchange": "exchange",
    "segment": "segment", "series": "series", "trade type": "trade_type", "auction": "auction",
    "quantity": "quantity", "price": "price", "trade id": "trade_id", "order id": "order_id",
    "order execution time": "order_execution_time",
}
GROWW_MAP = {
    "symbol": "symbol", "isin": "isin", "type": "trade_type", "quantity": "quantity",
    "value": "trade_value", "exchange": "exchange", "exchange order id": "order_id",
    "execution date and time": "groww_executed_at", "order status": "order_status",
}
Reject = tuple[int, str, dict]


@dataclass
class ParsedXlsx:
    rows: list[dict] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)
    file_client_code: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    layout: str | None = None


def is_xlsx(file_name: str | None, data: bytes) -> bool:
    return data[:4] == XLSX_MAGIC or (file_name or "").lower().endswith(".xlsx")


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _find_header(rows: list[tuple], out: ParsedXlsx) -> tuple[int, list[str], dict] | None:
    """Scan every cell (exports can start with a blank column) for the header + account banner."""
    for i, row in enumerate(rows):
        if not row:
            continue
        cells = [_s(c) for c in row]
        lower = [c.lower() for c in cells]
        for j, c in enumerate(lower):
            if c in ("client id", "ucc", "unique client code") and j + 1 < len(cells) and cells[j + 1]:
                out.file_client_code = cells[j + 1].upper()
            if c.startswith("tradebook for"):
                m = re.search(r"from\s+([\d-]+)\s+to\s+([\d-]+)", cells[j])
                if m:
                    out.date_from, out.date_to = m.group(1), m.group(2)
        if "execution date and time" in lower and "symbol" in lower:
            out.layout = "GROWW"
            return i, lower, GROWW_MAP
        if "symbol" in lower and "isin" in lower:
            out.layout = "ZERODHA"
            return i, lower, ZERODHA_MAP
        if "company" in lower and "side" in lower:
            out.layout = "UPSTOX"
            return i, lower, {}
    return None


def _groww(rec: dict) -> dict | None:
    """Groww has one row per order and no price: Value / Quantity. Only Executed rows are trades."""
    if _s(rec.get("order_status")).lower() != "executed":
        return None
    ts = datetime.strptime(_s(rec.get("groww_executed_at")), "%d-%m-%Y %I:%M %p")  # noqa: DTZ007 (formatted to text only)
    qty = float(rec.get("quantity") or 0)
    value = float(rec.get("trade_value") or 0)
    rec["trade_date"] = ts.strftime("%Y-%m-%d")
    rec["order_execution_time"] = ts.strftime("%Y-%m-%d %H:%M:%S")
    rec["price"] = round(value / qty, 4) if qty else 0
    rec["trade_id"] = rec.get("order_id")
    rec["segment"] = rec.get("segment") or "EQ"
    return rec


def _executed_at(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _row_to_trade(rec: dict) -> dict:
    """Validate one mapped record; raises ValueError with the reason."""
    trade_date_s = _s(rec.get("trade_date"))[:10]
    try:
        trade_date = date.fromisoformat(trade_date_s)
    except ValueError:
        raise ValueError(f"invalid date '{trade_date_s}', expected YYYY-MM-DD") from None
    quantity = float(rec.get("quantity") or 0)
    price = float(rec.get("price") or 0)
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    side = _s(rec.get("trade_type")).lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"bad trade_type '{side}'")
    exchange = _s(rec.get("exchange")).upper() or "NSE"
    if exchange not in ("NSE", "BSE"):
        raise ValueError(f"unsupported exchange '{exchange}'")
    return {
        "symbol": _s(rec.get("symbol")).upper(),
        "isin": _s(rec.get("isin")) or None,
        "trade_date": trade_date,
        "exchange": exchange,
        "segment": (_s(rec.get("segment")) or "EQ").upper(),
        "series": _s(rec.get("series")) or None,
        "auction": _s(rec.get("auction")) not in ("", "0", "false", "False"),
        "trade_type": side,
        "quantity": quantity,
        "price": price,
        "trade_value": round(quantity * price, 4),
        "broker_trade_id": _s(rec.get("trade_id")),
        "broker_order_id": _s(rec.get("order_id")),
        "executed_at": _executed_at(_s(rec.get("order_execution_time"))),
    }


def parse_tradebook_xlsx(data: bytes) -> ParsedXlsx:
    out = ParsedXlsx()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, keep_links=False)
    except Exception as exc:  # noqa: BLE001  any parse failure of an untrusted file becomes a reject
        out.rejects.append((0, f"Cannot open workbook: {exc}", {}))
        return out
    # Loaded fully, not read_only: some exports carry a wrong <dimension> tag that makes
    # read_only iteration stop after the first row (observed on the real Zerodha files).
    rows = list(wb.active.iter_rows(values_only=True))
    if len(rows) > MAX_ROWS:
        out.rejects.append((0, f"Sheet has {len(rows)} rows, limit is {MAX_ROWS}", {}))
        return out
    found = _find_header(rows, out)
    if found is None:
        out.rejects.append((0, "Header row not found (expected a Zerodha or Groww tradebook)", {}))
        return out
    idx, header, hmap = found
    if out.layout == "UPSTOX":
        out.rejects.append((idx + 1, "Upstox .xlsx needs company-name mapping, not supported in v2 yet; upload its CSV", {}))
        return out
    fields = [hmap.get(h) for h in header]
    for n, row in enumerate(rows[idx + 1:], start=idx + 2):
        if not row or all(_s(c) == "" for c in row):
            continue
        rec = {f: row[c] for c, f in enumerate(fields) if f and c < len(row)}
        if not rec.get("symbol"):
            continue
        raw = {k: _s(v) for k, v in rec.items()}
        try:
            if out.layout == "GROWW" and _groww(rec) is None:
                continue  # cancelled / rejected order, not a trade
            trade = _row_to_trade(rec)
        except (ValueError, TypeError) as exc:
            out.rejects.append((n, str(exc), raw))
            continue
        trade["extra"] = {"layout": out.layout, "row": n, **raw}
        out.rows.append(trade)
    return out
