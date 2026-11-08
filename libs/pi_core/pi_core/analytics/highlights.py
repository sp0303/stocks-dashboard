"""Deterministic "holding highlights" (no LLM): best / worst / longest held / win rate.

Returns structured items; the UI turns them into sentences with the shared
formatters (R12: ratios stay decimals here). ``today`` is a parameter. Pure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from pi_core.analytics.closed_trades import EPS, ClosedTrade
from pi_core.analytics.exposure import HoldingValue

Key = tuple[str, str]


def _open_rows(
    holdings: Sequence[HoldingValue], entry_dates: Mapping[Key, date], today: date
) -> list[dict[str, Any]]:
    rows = []
    for h in holdings:
        ret = None
        if h.market_value is not None and h.open_cost > EPS:
            ret = (h.market_value - h.open_cost) / h.open_cost
        entry = entry_dates.get((h.symbol, h.exchange))
        rows.append(
            {"symbol": h.symbol, "return": ret, "days": (today - entry).days if entry else None}
        )
    return rows


def _item(kind: str, symbol: str | None, value: float | None, unit: str, basis: str) -> dict:
    return {"kind": kind, "symbol": symbol, "value": value, "unit": unit, "basis": basis}


def holding_highlights(
    holdings: Sequence[HoldingValue],
    entry_dates: Mapping[Key, date],
    closed: Sequence[ClosedTrade],
    today: date,
) -> list[dict[str, Any]]:
    """Up to six items. ``unit`` is 'ratio' (decimal), 'days' or 'inr'."""
    out: list[dict[str, Any]] = []
    rows = _open_rows(holdings, entry_dates, today)
    priced = [r for r in rows if r["return"] is not None]
    if priced:
        best = max(priced, key=lambda r: (r["return"], r["symbol"]))
        worst = min(priced, key=lambda r: (r["return"], r["symbol"]))
        out.append(_item("best_open", best["symbol"], best["return"], "ratio", "unrealised"))
        if worst["symbol"] != best["symbol"]:
            out.append(_item("worst_open", worst["symbol"], worst["return"], "ratio", "unrealised"))
    dated = [r for r in rows if r["days"] is not None]
    if dated:
        longest = max(dated, key=lambda r: (r["days"], r["symbol"]))
        out.append(_item("longest_held", longest["symbol"], float(longest["days"]), "days", "open"))
    if closed:
        top = max(closed, key=lambda t: (t.pnl, t.symbol))
        bottom = min(closed, key=lambda t: (t.pnl, t.symbol))
        if top.is_win:
            out.append(_item("best_closed", top.symbol, top.pnl, "inr", "realised"))
        if bottom.is_loss:
            out.append(_item("worst_closed", bottom.symbol, bottom.pnl, "inr", "realised"))
        wins = sum(1 for t in closed if t.is_win)
        out.append(_item("win_rate", None, wins / len(closed), "ratio", "realised"))
    return out
