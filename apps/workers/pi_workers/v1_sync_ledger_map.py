"""Pure v1 (Mongo) document -> v2 row mappers for the ledger resync.

No I/O, no clock (``today`` is a parameter). Each mapper returns ``(row, None)`` or
``(None, reason)``; the caller stores the reason with the raw document (R13.3).

v1 shapes (backend/app/store.py, routers/*.py, services/ingestion.py; read-only reference):
  managers  {id, name, email, firm, status}
  clients   {id, name, portfolio_manager_id, client_code, status, [broker]}
  trades    {id, client_id, fingerprint, symbol, isin, trade_date, exchange, segment, series,
             trade_type, auction, quantity, price, trade_id, order_id, order_execution_time,
             charges, [source='manual', note]}   (Groww rows: trade_id == order_id)
  uploads   {id, client_id, version, file_name, file_hash, date_from, date_to, row_count,
             imported_count, duplicate_count, error_count, status, uploaded_at}
  corporate_actions {key, isin, symbol, ex_date, type, qty_multiplier, amount_per_share, subject, source}
  dividends {id, client_id, symbol, ex_date, amount_per_share, quantity, source}
  thesis    {client_id, symbol, ...free fields}
  watchlists {owner_type, owner_id, lists:[{id, name, entries:[...]}]} | legacy entries/symbols
  boards    {owner_type, owner_id, items:[{id, symbol, entry_price, exit_price, why, status}]}
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
CLIENT_BROKERS = {"ZERODHA", "UPSTOX", "ANGEL", "OTHER"}
CA_TYPES = {"SPLIT", "BONUS", "DIVIDEND", "DEMERGER", "MERGER", "BUYBACK", "RIGHTS", "DELISTING", "OTHER"}
TRADE_SOURCES = {"upload", "manual", "kite", "angel"}
BOARD_LANES = {"watching": "watching", "holding": "holding", "entered": "holding", "exit": "exit", "exited": "exit"}
Result = tuple[dict[str, Any] | None, str | None]


def jsonable(doc: Any) -> Any:
    """A JSON-safe deep copy of a Mongo document (ObjectId/datetime/Decimal -> str)."""
    return json.loads(json.dumps(doc, default=str, sort_keys=True))


def legacy_id(doc: dict) -> str:
    """The v1 id the app uses (`id`), else the Mongo `_id`."""
    v = doc.get("id") or doc.get("_id")
    return str(v) if v is not None else ""


def text(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def dec(v: Any, places: str) -> Decimal | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v)).quantize(Decimal(places))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def parse_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST).date()
        except ValueError:
            continue
    return None


def parse_ts(v: Any) -> datetime | None:
    """v1 execution times are naive IST strings ('YYYY-MM-DD HH:MM:SS' or with 'T')."""
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=IST)
    s = str(v or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


# ── core ──────────────────────────────────────────────────────────────────────


def map_manager(doc: dict) -> Result:
    lid, name, email = legacy_id(doc), text(doc.get("name")), text(doc.get("email"))
    if not lid:
        return None, "missing_id"
    if not name:
        return None, "missing_name"
    if not email:
        return None, "missing_email"  # core.managers.email is NOT NULL UNIQUE (login identity)
    status = str(doc.get("status") or "ACTIVE").upper()
    return {
        "legacy_id": lid,
        "name": name,
        "firm": text(doc.get("firm")),
        "email": email,
        "is_active": status != "INACTIVE",
    }, None


def map_client(doc: dict) -> Result:
    lid, name = legacy_id(doc), text(doc.get("name"))
    if not lid:
        return None, "missing_id"
    if not name:
        return None, "missing_name"
    mid = text(doc.get("portfolio_manager_id") or doc.get("manager_id"))
    if not mid:
        return None, "missing_manager"
    broker = (text(doc.get("broker")) or "").upper() or None
    if broker and broker not in CLIENT_BROKERS:
        broker = "OTHER"  # e.g. GROWW: no enum value in core.clients.broker
    status = str(doc.get("status") or "ACTIVE").upper()
    return {
        "legacy_id": lid,
        "v1_manager_id": mid,
        "name": name,
        "client_code": text(doc.get("client_code")),
        "broker": broker,
        "status": "INACTIVE" if status == "INACTIVE" else "ACTIVE",
    }, None


# ── ledger ────────────────────────────────────────────────────────────────────


def _trade_source(doc: dict) -> str:
    s = str(doc.get("source") or "upload").strip().lower()
    return s if s in TRADE_SOURCES else "upload"


def map_trade(doc: dict, client_id: Any) -> Result:
    """One v1 trade -> ledger.trades row. The v1 fingerprint is kept verbatim (it already
    includes the broker trade id, R13.4); the whole raw doc goes to extra.v1 (R13.2)."""
    fp = text(doc.get("fingerprint"))
    if not fp:
        return None, "missing_fingerprint"
    symbol = (text(doc.get("symbol")) or "").upper()
    if not symbol:
        return None, "missing_symbol"
    td = parse_date(doc.get("trade_date"))
    if td is None:
        return None, "bad_trade_date"
    side = str(doc.get("trade_type") or doc.get("action") or "").strip().lower()
    side = {"b": "buy", "s": "sell"}.get(side, side)
    if side not in ("buy", "sell"):
        return None, "bad_trade_type"
    qty, price = dec(doc.get("quantity"), "0.000001"), dec(doc.get("price"), "0.0001")
    source = _trade_source(doc)
    if qty is None or qty <= 0:
        return None, "bad_quantity"
    if price is None or price < 0 or (price == 0 and source != "manual"):
        return None, "bad_price"
    extra: dict[str, Any] = {"v1": jsonable(doc), "v1_sync": 1}
    exch = (text(doc.get("exchange")) or "").upper()
    if not exch:
        exch, extra["exchange_defaulted"] = "NSE", True
    if exch not in ("NSE", "BSE"):
        return None, f"unsupported_exchange:{exch[:12]}"
    charges = dec(doc.get("charges"), "0.0001")
    known = charges is not None and charges != 0  # v1 always wrote a 0.0 placeholder (R15)
    return {
        "client_id": client_id,
        "legacy_id": legacy_id(doc) or None,
        "fingerprint": fp,
        "symbol": symbol,
        "isin": text(doc.get("isin")),
        "trade_date": td,
        "exchange": exch,
        "segment": (text(doc.get("segment")) or "EQ").upper(),  # R9: missing segment => equity
        "series": text(doc.get("series")),
        "trade_type": side,
        "auction": bool(doc.get("auction")) and str(doc.get("auction")).lower() not in ("0", "false"),
        "quantity": qty,
        "price": price,
        "broker_trade_id": text(doc.get("trade_id")),
        "broker_order_id": text(doc.get("order_id")),
        "executed_at": parse_ts(doc.get("order_execution_time")),
        "charges": charges if known else None,
        "charges_known": known,
        "source": source,
        "note": text(doc.get("note")),
        "extra": json.dumps(extra, sort_keys=True),
    }, None


def map_upload(doc: dict, client_id: Any) -> Result:
    h = text(doc.get("file_hash"))
    try:
        sha = bytes.fromhex(h) if h else None
    except ValueError:
        sha = None
    if sha is None:
        return None, "bad_file_hash"
    n = {k: int(doc.get(k) or 0) for k in ("row_count", "imported_count", "duplicate_count", "error_count")}
    status = str(doc.get("status") or "IMPORTED").upper()
    return {
        "legacy_id": legacy_id(doc) or None,
        "client_id": client_id,
        "version": int(doc.get("version") or 0),
        "file_name": text(doc.get("file_name")) or "unknown",
        "file_sha256": sha,
        "broker_format": "OTHER",  # v1 never recorded the format; the raw file is not in Mongo
        "date_from": parse_date(doc.get("date_from")),
        "date_to": parse_date(doc.get("date_to")),
        "rows_total": n["row_count"] + n["error_count"],
        "rows_imported": n["imported_count"],
        "rows_duplicate": n["duplicate_count"],
        "rows_rejected": n["error_count"],
        "status": status if status in ("IMPORTED", "PARTIAL", "FAILED") else "IMPORTED",
    }, None


def map_corporate_action(doc: dict) -> Result:
    key = text(doc.get("key"))
    if not key:
        return None, "missing_key"
    symbol = (text(doc.get("symbol")) or "").upper()
    if not symbol:
        return None, "missing_symbol"
    ex = parse_date(doc.get("ex_date"))
    if ex is None:
        return None, "bad_ex_date"
    typ = str(doc.get("type") or "OTHER").upper()
    return {
        "key": key,
        "isin": text(doc.get("isin")),
        "symbol": symbol,
        "ex_date": ex,
        "type": typ if typ in CA_TYPES else "OTHER",
        "qty_multiplier": dec(doc.get("qty_multiplier"), "0.00000001"),
        "amount_per_share": dec(doc.get("amount_per_share"), "0.0001"),
        "subject": text(doc.get("subject")),
        "source": text(doc.get("source")) or "NSE",
    }, None


def map_dividend(doc: dict, client_id: Any) -> Result:
    symbol = (text(doc.get("symbol")) or "").upper()
    ex = parse_date(doc.get("ex_date"))
    amt, qty = dec(doc.get("amount_per_share"), "0.0001"), dec(doc.get("quantity"), "0.000001")
    if not symbol or ex is None:
        return None, "missing_symbol_or_date"
    if amt is None or qty is None:
        return None, "bad_amount_or_quantity"
    src = str(doc.get("source") or "manual").strip().lower()
    return {
        "client_id": client_id,
        "symbol": symbol,
        "ex_date": ex,
        "amount_per_share": amt,
        "quantity": qty,
        "source": "nse" if src.startswith("nse") or src == "auto" else "manual",
    }, None
