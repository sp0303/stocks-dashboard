"""Playbook: closed trades collapsed to one row per stock, plus a CSV rendering.

Weighted (not simple) average prices, since lots differ in size. Matched shares only
(R7). Ratios are decimals (R12). Pure: no I/O, no clock.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from pi_core.analytics.closed_trades import EPS, ClosedTrade

CSV_COLUMNS = (
    ("pool", "Pool"),
    ("symbol", "Symbol"),
    ("exchange", "Exchange"),
    ("trades", "Trades"),
    ("quantity", "Quantity"),
    ("avg_buy_price", "Avg buy price"),
    ("avg_sell_price", "Avg sell price"),
    ("avg_days", "Avg days held"),
    ("pnl", "P&L (INR)"),
    ("pnl_pct", "P&L (decimal of cost)"),
    ("first_buy_date", "First buy"),
    ("last_sell_date", "Last sell"),
    ("reason", "Reason / notes"),
)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _reason(trades: Sequence[ClosedTrade], notes: Mapping[str, str]) -> str:
    seen: list[str] = []
    for t in trades:
        for tid in t.buy_trade_ids:
            note = (notes.get(tid) or "").strip()
            if note and note not in seen:
                seen.append(note)
    return "; ".join(seen)


def _row(pool: str, trades: Sequence[ClosedTrade], notes: Mapping[str, str]) -> dict[str, Any]:
    first = trades[0]
    qty = sum(t.quantity for t in trades)
    buy_value = sum(t.buy_value for t in trades)
    cost = sum(t.cost_basis for t in trades)
    pnl = sum(t.pnl for t in trades)
    return {
        "pool": pool,
        "symbol": first.symbol,
        "exchange": first.exchange,
        "trades": len(trades),
        "quantity": qty,
        "avg_buy_price": buy_value / qty if qty > 0 else None,
        "avg_sell_price": sum(t.sell_value for t in trades) / qty if qty > 0 else None,
        "avg_days": sum(t.holding_days * t.quantity for t in trades) / qty if qty > 0 else None,
        "pnl": pnl,
        "pnl_pct": pnl / cost if cost > EPS else None,
        "first_buy_date": min(t.first_buy_date for t in trades).isoformat(),
        "last_sell_date": max(t.sell_date for t in trades).isoformat(),
        "reason": _reason(trades, notes),
    }


def playbook_by_stock(
    trades: Sequence[ClosedTrade], notes: Mapping[str, str], pool: str
) -> list[dict[str, Any]]:
    """One row per (symbol, exchange); ``notes`` maps buy trade_id -> note. Sorted by P&L desc."""
    groups: dict[tuple[str, str], list[ClosedTrade]] = defaultdict(list)
    for t in trades:
        groups[(t.symbol, t.exchange)].append(t)
    rows = [_row(pool, ts, notes) for ts in groups.values()]
    rows.sort(key=lambda r: (-r["pnl"], r["symbol"]))
    return rows


def _cell(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES):
        return "'" + v  # spreadsheet formula-injection guard
    return v


def playbook_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    """Full-precision CSV (no rounding); empty cells for unknown values."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([label for _, label in CSV_COLUMNS])
    for r in rows:
        w.writerow([_cell(r.get(k)) for k, _ in CSV_COLUMNS])
    return buf.getvalue()
