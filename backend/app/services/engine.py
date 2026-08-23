"""Pure FIFO portfolio engine.

No database, no FastAPI, no network. Input = list of trade dicts (chronological),
output = positions + realized P&L. This is the most-tested unit in the system and the
reason a future broker (Kite) is a provider swap, not a rewrite.

Money is handled in rupees as float here for readability; callers round for display.
Cost basis is FIFO. Charges are optional (Zerodha tradebooks don't include them) — if a
trade carries a `charges` value it is folded in (buy cost += charges, sell proceeds -= charges).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Iterable


@dataclass
class Lot:
    qty: float
    unit_cost: float          # per-share cost incl. allocated charges
    trade_date: str
    fingerprint: str | None = None


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0             # weighted avg cost of open lots
    invested_value: float = 0.0      # sum(open lot qty * unit_cost)
    realized_pnl: float = 0.0        # cumulative realized for this symbol
    total_bought_qty: float = 0.0
    total_sold_qty: float = 0.0
    total_bought_value: float = 0.0  # cash out on buys (incl charges)
    total_sold_value: float = 0.0    # cash in on sells (net charges)
    first_buy_date: str | None = None
    last_buy_date: str | None = None
    last_sell_date: str | None = None
    open_lots: list[Lot] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["open_lots"] = [lot.__dict__ for lot in self.open_lots]
        return d


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    return float(v)


def _days_between(start: str, end: str) -> int | None:
    try:
        d1 = _date.fromisoformat(start[:10])
        d2 = _date.fromisoformat(end[:10])
        return (d2 - d1).days
    except (ValueError, TypeError):
        return None


def compute_positions(trades: Iterable[dict]) -> tuple[list[Position], float]:
    """Run FIFO matching over chronologically-ordered trades.

    Returns (positions_with_open_qty_or_history, total_realized_pnl).
    A position is returned for every symbol ever traded (so realized-only symbols
    still show their realized P&L); quantity may be 0.
    """
    trades = sorted(
        trades,
        key=lambda t: (str(t.get("trade_date", "")), str(t.get("order_execution_time", ""))),
    )

    lots: dict[str, deque[Lot]] = defaultdict(deque)
    pos: dict[str, Position] = {}
    total_realized = 0.0

    for t in trades:
        symbol = t["symbol"]
        p = pos.setdefault(symbol, Position(symbol=symbol))
        qty = _num(t.get("quantity"))
        price = _num(t.get("price"))
        charges = _num(t.get("charges"))
        ttype = str(t.get("trade_type", "")).lower()
        date = str(t.get("trade_date", ""))
        if qty <= 0:
            continue

        if ttype == "buy":
            unit_cost = (price * qty + charges) / qty
            lots[symbol].append(Lot(qty=qty, unit_cost=unit_cost, trade_date=date, fingerprint=t.get("fingerprint")))
            p.total_bought_qty += qty
            p.total_bought_value += price * qty + charges
            if p.first_buy_date is None:
                p.first_buy_date = date
            p.last_buy_date = date

        elif ttype == "sell":
            proceeds = price * qty - charges
            remaining = qty
            matched_cost = 0.0
            dq = lots[symbol]
            while remaining > 1e-9 and dq:
                lot = dq[0]
                take = min(remaining, lot.qty)
                matched_cost += take * lot.unit_cost
                lot.qty -= take
                remaining -= take
                if lot.qty <= 1e-9:
                    dq.popleft()
            # If selling more than held (short / data gap), match what we can.
            p.realized_pnl += proceeds - matched_cost
            total_realized += proceeds - matched_cost
            p.total_sold_qty += qty
            p.total_sold_value += proceeds
            p.last_sell_date = date

    # finalize open positions
    for symbol, p in pos.items():
        open_lots = [lot for lot in lots[symbol] if lot.qty > 1e-9]
        p.open_lots = open_lots
        p.quantity = round(sum(lot.qty for lot in open_lots), 6)
        p.invested_value = sum(lot.qty * lot.unit_cost for lot in open_lots)
        p.avg_cost = (p.invested_value / p.quantity) if p.quantity > 1e-9 else 0.0

    return list(pos.values()), round(total_realized, 4)


def compute_round_trips(trades: Iterable[dict]) -> list[dict]:
    """FIFO-matched closed round trips ("playbook" rows): each row is one buy-lot
    slice matched against a sell. A sell spanning multiple buy lots produces one row
    per lot consumed; a buy sold off in pieces produces one row per piece sold.
    Only closed (bought-and-sold) quantity is returned — open positions have no row.
    """
    trades = sorted(
        trades,
        key=lambda t: (str(t.get("trade_date", "")), str(t.get("order_execution_time", ""))),
    )

    lots: dict[str, deque[Lot]] = defaultdict(deque)
    round_trips: list[dict] = []

    for t in trades:
        symbol = t["symbol"]
        qty = _num(t.get("quantity"))
        price = _num(t.get("price"))
        charges = _num(t.get("charges"))
        ttype = str(t.get("trade_type", "")).lower()
        date = str(t.get("trade_date", ""))
        if qty <= 0:
            continue

        if ttype == "buy":
            unit_cost = (price * qty + charges) / qty
            lots[symbol].append(Lot(qty=qty, unit_cost=unit_cost, trade_date=date, fingerprint=t.get("fingerprint")))

        elif ttype == "sell":
            remaining = qty
            sell_charge_per_unit = charges / qty
            dq = lots[symbol]
            while remaining > 1e-9 and dq:
                lot = dq[0]
                take = min(remaining, lot.qty)
                buy_price = lot.unit_cost
                sell_price = price - sell_charge_per_unit
                pnl = (sell_price - buy_price) * take
                round_trips.append(
                    {
                        "symbol": symbol,
                        "quantity": round(take, 6),
                        "buy_price": round(buy_price, 4),
                        "buy_date": lot.trade_date,
                        "sell_price": round(sell_price, 4),
                        "sell_date": date,
                        "days": _days_between(lot.trade_date, date),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round((sell_price - buy_price) / buy_price * 100, 2) if buy_price else 0.0,
                        "buy_fingerprint": lot.fingerprint,
                        "sell_fingerprint": t.get("fingerprint"),
                    }
                )
                lot.qty -= take
                remaining -= take
                if lot.qty <= 1e-9:
                    dq.popleft()

    return round_trips
