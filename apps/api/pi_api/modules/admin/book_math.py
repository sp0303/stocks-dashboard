"""Pure manager-book aggregation (no I/O, no clock). Ratios are decimals (R12).

* ``book_insights``: per-symbol sums of the clients' own engine positions (R5). A position
  with no price leaves BOTH its cost and its value out (R6), as v1's book page did.
* ``index_units``: R10 benchmark P&L on the book's own ``net_invested`` baseline.
* ``client_returns``: each client's time-weighted NAV rebased to 0 at its first point (R2).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

STALE_SESSIONS = 2  # R10 dead-ticker guard: more than 2 sessions behind = stale


def _top(d: dict[str, float], lowest: bool = False) -> tuple[str, float] | None:
    if not d:
        return None
    items = sorted(d.items())  # deterministic tie-break: alphabetical symbol wins
    pick = min if lowest else max
    return pick(items, key=lambda kv: kv[1])


def book_insights(
    positions: Iterable[dict[str, Any]], trade_counts: dict[str, int]
) -> dict[str, Any]:
    invested: dict[str, float] = defaultdict(float)
    value: dict[str, float] = defaultdict(float)
    held: set = set()
    unpriced: set = set()
    for p in positions:
        sym = p["symbol"]
        held.add(sym)
        if p.get("price") is None:
            unpriced.add(sym)
            continue
        invested[sym] += float(p["invested"])
        value[sym] += float(p["quantity"]) * float(p["price"])
    perf = {s: (value[s] - invested[s]) / invested[s] for s in value if invested[s] > 0}
    most_inv = _top(dict(invested))
    top_hold = _top(dict(value))
    fav = _top({k: float(v) for k, v in trade_counts.items()})
    best = _top(perf)
    worst = _top(perf, lowest=True)
    return {
        "unique_stocks": len(held),
        "unpriced_symbols": sorted(unpriced - set(value)),
        "most_invested": {"symbol": most_inv[0], "value": most_inv[1]}
        if most_inv
        else None,
        "most_traded": {"symbol": fav[0], "value": fav[1]} if fav else None,
        "top_holding": {"symbol": top_hold[0], "value": top_hold[1]}
        if top_hold
        else None,
        "best_performer": {"symbol": best[0], "value": best[1]} if best else None,
        "worst_performer": {"symbol": worst[0], "value": worst[1]} if worst else None,
    }


def book_totals(roster: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """R5: book figures are plain sums of each client's engine overview. R1 return base."""
    keys = (
        "market_value",
        "capital_deployed",
        "current_invested",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
    )
    tot = {k: 0.0 for k in keys}
    n = 0
    for c in roster:
        n += 1
        for k in keys:
            v = c.get(k)
            if v is not None:
                tot[k] += float(v)
    cd = tot["capital_deployed"]
    tot["return_on_capital"] = tot["total_pnl"] / cd if cd > 0 else None
    tot["client_count"] = n
    return tot


def index_units(book: list[dict[str, Any]], bench: dict[date, float]) -> dict[str, Any]:
    """R10 index units on the book's net_invested. Returns pnl points (None where unknown)."""
    if not book:
        return {"points": [], "last_date": None, "sessions_behind": 0, "stale": False}
    last_bench = max(bench) if bench else None
    units = 0.0
    applied = 0.0  # net_invested already converted into units
    price: float | None = None
    points: list[float | None] = []
    for row in book:
        d, net = row["as_of"], float(row["net_invested"])
        if last_bench is None or d > last_bench:
            points.append(None)  # never flatline past the benchmark's last value
            continue
        price = bench.get(
            d, price
        )  # carry across a calendar mismatch, never forward past last
        if price is None or price <= 0:
            points.append(
                None
            )  # index not available yet: flows wait for the first level
            continue
        units += (net - applied) / price
        applied = net
        points.append(units * price - net)
    behind = sum(1 for r in book if last_bench is None or r["as_of"] > last_bench)
    return {
        "points": points,
        "last_date": last_bench,
        "sessions_behind": behind,
        "stale": behind > STALE_SESSIONS,
    }


def client_returns(navs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group NAV rows by client; return = nav / first_nav − 1 (decimal). NAV ≤ 0 is skipped (R16)."""
    out: dict[Any, dict[str, Any]] = {}
    for r in navs:
        nav = r.get("nav")
        if nav is None or float(nav) <= 0:
            continue
        cur = out.setdefault(
            r["client_id"],
            {
                "client_id": r["client_id"],
                "name": r["name"],
                "base": float(nav),
                "series": [],
            },
        )
        cur["series"].append(
            {"as_of": r["as_of"], "value": float(nav) / cur["base"] - 1.0}
        )
    for v in out.values():
        v.pop("base", None)
    return sorted(out.values(), key=lambda c: c["name"])
