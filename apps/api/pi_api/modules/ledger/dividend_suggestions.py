"""'Find missing dividends' (v1 parity): proposals from stored DIVIDEND corporate actions.

Pure functions, no I/O. Nothing is written here: the user accepts a row and the UI posts
it to the existing POST /ledger/dividends.

Held quantity on an ex-date = delivery-equity net quantity from trades dated strictly
BEFORE the ex-date (a buy on the ex-date does not carry the dividend; v1 used <=, which
over-counted same-day buys), with splits/bonuses dated before the dividend ex-date
applied in date order, ahead of same-day trades (R8). Derivatives never count (R9). An
unmatched sell cannot push the holding below zero (R7).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

DERIVATIVE_SEGMENTS = {"FO", "FUT", "OPT", "NRML", "NFO", "BFO", "DERIVATIVE"}
_EPS = 1e-9


def _is_equity(t: Mapping[str, Any]) -> bool:
    return str(t.get("segment") or "EQ").upper() not in DERIVATIVE_SEGMENTS


def held_before(
    trades: Iterable[Mapping[str, Any]],
    qty_actions: Iterable[Mapping[str, Any]],
    ex_date: date,
) -> float:
    """Quantity held at the close of the session before ``ex_date`` (one symbol)."""
    events: list[tuple[date, int, Mapping[str, Any]]] = []
    for t in trades:
        if _is_equity(t) and t["trade_date"] < ex_date:
            events.append((t["trade_date"], 1, t))
    for a in qty_actions:
        if a["ex_date"] < ex_date and (a.get("qty_multiplier") or 0) > 0:
            events.append((a["ex_date"], 0, a))  # action applies before same-day trades
    qty = 0.0
    for _, kind, ev in sorted(events, key=lambda e: (e[0], e[1])):
        if kind == 0:
            qty *= float(ev["qty_multiplier"])
        elif str(ev["trade_type"]).lower() == "buy":
            qty += float(ev["quantity"])
        else:
            qty = max(0.0, qty - float(ev["quantity"]))
    return qty if qty > _EPS else 0.0


def suggest(
    trades: list[Mapping[str, Any]],
    actions: list[Mapping[str, Any]],
    existing: Iterable[tuple[str, date]],
) -> list[dict[str, Any]]:
    """One proposal per (symbol, ex_date) DIVIDEND held on its ex-date and not yet recorded."""
    have = {(s.upper(), d) for s, d in existing}
    by_sym: dict[str, list[Mapping[str, Any]]] = {}
    for t in trades:
        by_sym.setdefault(str(t["symbol"]).upper(), []).append(t)
    qty_acts: dict[str, list[Mapping[str, Any]]] = {}
    for a in actions:
        if str(a["type"]).upper() in ("SPLIT", "BONUS"):
            qty_acts.setdefault(str(a["symbol"]).upper(), []).append(a)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, date]] = set()
    for a in actions:
        sym = str(a["symbol"]).upper()
        key = (sym, a["ex_date"])
        if str(a["type"]).upper() != "DIVIDEND" or key in have or key in seen:
            continue
        aps = a.get("amount_per_share")
        if aps is None or float(aps) <= 0:
            continue  # unknown amount is not a proposal (R15: unknown is not 0)
        qty = held_before(by_sym.get(sym, []), qty_acts.get(sym, []), a["ex_date"])
        if qty <= 0:
            continue
        seen.add(key)
        out.append({
            "symbol": sym,
            "ex_date": a["ex_date"],
            "amount_per_share": float(aps),
            "estimated_quantity": qty,
            "estimated_total": round(float(aps) * qty, 2),
            "subject": a.get("subject"),
            "source": a.get("source"),
        })
    out.sort(key=lambda s: (s["ex_date"], s["symbol"]), reverse=True)
    return out
