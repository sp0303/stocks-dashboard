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
    isin: str | None = None          # reconciliation key when known (nets renames/demergers)
    quantity: float = 0.0
    avg_cost: float = 0.0             # weighted avg cost of open lots
    invested_value: float = 0.0      # sum(open lot qty * unit_cost)
    realized_pnl: float = 0.0        # cumulative realized for this symbol (matched qty only)
    total_bought_qty: float = 0.0
    total_sold_qty: float = 0.0
    total_bought_value: float = 0.0  # cash out on buys (incl charges)
    total_sold_value: float = 0.0    # cash in on sells (net charges)
    # Quantity sold with no matching buy lot (tradebook gap / IPO allotment / bonus
    # / demat transfer-in). Its cost basis is unknown, so it is *excluded* from
    # realized_pnl rather than booked as 100% profit; surfaced as a warning instead.
    unmatched_sell_qty: float = 0.0
    unmatched_sell_value: float = 0.0
    first_buy_date: str | None = None
    last_buy_date: str | None = None
    last_sell_date: str | None = None
    # split/bonus events applied to this position's open lots, for display/audit:
    # [{ex_date, type, multiplier}]
    applied_actions: list[dict] = field(default_factory=list)
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


def _rkey_of(t: dict, sym_isin: dict[str, str]) -> str:
    """Reconciliation key: the security's ISIN when known, else its raw symbol.

    Grouping by ISIN nets a *rename* (HBLPOWER→HBLENGINE, same ISIN) and the parent
    leg of a *demerger* that keeps the parent ISIN (TATAMOTORS+TMPV) into one position,
    instead of leaving an orphaned open lot under the old ticker.
    """
    return sym_isin.get(t.get("symbol")) or str(t.get("symbol"))


def _prep(trades: Iterable[dict]) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    """Shared pre-pass for both FIFO passes. Returns (sorted_trades, sym_isin, display).

    Two corrections happen here, before any lot matching:

    1. Same-day netting — trades are ordered by (date, BUY-before-SELL, time) rather than
       strict execution time. On a day with a morning sell and an afternoon buy of the
       same scrip (intraday square-off / sell-and-rebuy), processing the buy first lets
       the sell consume it, so the pair nets out instead of stranding a phantom open lot
       plus an equal "unmatched sell".
    2. ISIN reconciliation — a symbol is grouped under its ISIN (first non-empty seen), so
       renames/demergers that share an ISIN collapse into one position. The display symbol
       for the group is the most recently traded ticker (so pricing uses the live name).
    """
    trades = list(trades)
    sym_isin: dict[str, str] = {}
    # Earliest trade first, so the choice doesn't depend on the order the store returned
    # the rows in. A split that changes the ISIN (NUVAMA INE531F01015 -> ...023) otherwise
    # grouped the symbol under whichever ISIN came first in the list, and when that was
    # the new one the split (filed under the old ISIN) was never applied: 5 shares shown
    # for 25 held.
    for t in sorted(trades, key=lambda t: (str(t.get("trade_date", "")), str(t.get("order_execution_time", "")))):
        s = t.get("symbol")
        i = (t.get("isin") or "").strip()
        if s and i and s not in sym_isin:
            sym_isin[s] = i

    display: dict[str, str] = {}
    latest: dict[str, tuple[str, str]] = {}
    for t in trades:
        k = _rkey_of(t, sym_isin)
        stamp = (str(t.get("trade_date", "")), str(t.get("order_execution_time", "")))
        if k not in latest or stamp >= latest[k]:
            latest[k] = stamp
            display[k] = str(t.get("symbol"))

    trades.sort(
        key=lambda t: (
            str(t.get("trade_date", "")),
            0 if str(t.get("trade_type", "")).lower() == "buy" else 1,
            str(t.get("order_execution_time", "")),
        )
    )
    return trades, sym_isin, display


def _adjustment_events(actions: Iterable[dict] | None,
                       sym_isin: dict[str, str] | None = None) -> list[tuple[str, str, float, str]]:
    """Build (ex_date, key, multiplier, type) events from split/bonus corporate actions.

    Only SPLIT and BONUS change share count, so only those become events. Each event is
    registered under BOTH the security's ISIN and its symbol, so it matches a position
    however the engine keyed it (ISIN when the tradebook carried one, else symbol).
    """
    events: list[tuple[str, str, float, str]] = []
    for a in actions or []:
        if a.get("type") not in ("SPLIT", "BONUS"):
            continue
        mult = float(a.get("qty_multiplier") or 1.0)
        ex = a.get("ex_date")
        if not ex or mult == 1.0:
            continue
        sym = (a.get("symbol") or "").strip()
        # ...and under the key the engine grouped that symbol by, which differs from the
        # action's own ISIN when the split itself changed the ISIN.
        for key in {(a.get("isin") or "").strip(), sym, (sym_isin or {}).get(sym, "")}:
            if key:
                events.append((ex, key, mult, a["type"]))
    return events


def compute_positions(trades: Iterable[dict],
                      actions: Iterable[dict] | None = None) -> tuple[list[Position], float]:
    """Run FIFO matching over chronologically-ordered trades.

    Returns (positions_with_open_qty_or_history, total_realized_pnl).
    A position is returned for every security ever traded (keyed by ISIN when known, so
    renames/demergers net rather than double-count); quantity may be 0.

    ``actions`` (optional) are corporate actions from corporate_actions.py. Split/bonus
    events are applied to open lots on their ex-date — scaling quantity up and per-share
    cost down — so held quantities track the broker's after a split/bonus, without a trade.
    """
    trades, sym_isin, display = _prep(trades)

    # Merge trades and split/bonus events into one date-ordered stream. An adjustment sorts
    # BEFORE same-day trades (priority -1), so it scales the pre-ex-date holding while a
    # buy/sell executed on the ex-date itself is already in post-event terms and untouched.
    stream: list[tuple] = []
    for t in trades:
        prio = 0 if str(t.get("trade_type", "")).lower() == "buy" else 1
        stream.append((str(t.get("trade_date", "")), prio, str(t.get("order_execution_time", "")), "T", t))
    for ex, key, mult, atype in _adjustment_events(actions, sym_isin):
        stream.append((ex, -1, "", "A", (key, mult, atype)))
    stream.sort(key=lambda x: (x[0], x[1], x[2]))

    lots: dict[str, deque[Lot]] = defaultdict(deque)
    pos: dict[str, Position] = {}
    total_realized = 0.0

    for _d, _p, _tm, kind, payload in stream:
        if kind == "A":
            key, mult, atype = payload
            dq = lots.get(key)
            if dq:  # only a currently-held position is affected
                for lot in dq:
                    lot.qty *= mult
                    lot.unit_cost /= mult
                p = pos.get(key)
                if p:
                    p.applied_actions.append({"ex_date": _d, "type": atype, "multiplier": mult})
            continue

        t = payload
        key = _rkey_of(t, sym_isin)
        p = pos.setdefault(key, Position(symbol=display.get(key, str(t.get("symbol"))),
                                         isin=sym_isin.get(t.get("symbol"))))
        qty = _num(t.get("quantity"))
        price = _num(t.get("price"))
        charges = _num(t.get("charges"))
        ttype = str(t.get("trade_type", "")).lower()
        date = str(t.get("trade_date", ""))
        if qty <= 0:
            continue

        if ttype == "buy":
            unit_cost = (price * qty + charges) / qty
            lots[key].append(Lot(qty=qty, unit_cost=unit_cost, trade_date=date, fingerprint=t.get("fingerprint")))
            p.total_bought_qty += qty
            p.total_bought_value += price * qty + charges
            if p.first_buy_date is None:
                p.first_buy_date = date
            p.last_buy_date = date

        elif ttype == "sell":
            proceeds = price * qty - charges
            remaining = qty
            matched_cost = 0.0
            dq = lots[key]
            while remaining > 1e-9 and dq:
                lot = dq[0]
                take = min(remaining, lot.qty)
                matched_cost += take * lot.unit_cost
                lot.qty -= take
                remaining -= take
                if lot.qty <= 1e-9:
                    dq.popleft()
            # `remaining` is quantity sold beyond what we hold (short / tradebook gap).
            # Realize P&L only on the matched quantity — booking the unmatched portion's
            # proceeds against a zero cost basis would fabricate profit (e.g. an IPO
            # allotment or bonus share whose buy leg isn't in the equity tradebook).
            matched_qty = qty - remaining
            charge_matched = charges * (matched_qty / qty) if qty else 0.0
            matched_proceeds = price * matched_qty - charge_matched
            realized = matched_proceeds - matched_cost
            p.realized_pnl += realized
            total_realized += realized
            p.total_sold_qty += qty
            p.total_sold_value += proceeds
            p.last_sell_date = date
            if remaining > 1e-9:
                p.unmatched_sell_qty += remaining
                p.unmatched_sell_value += price * remaining - charges * (remaining / qty if qty else 0.0)

    # finalize open positions
    for key, p in pos.items():
        open_lots = [lot for lot in lots[key] if lot.qty > 1e-9]
        p.open_lots = open_lots
        p.quantity = round(sum(lot.qty for lot in open_lots), 6)
        p.invested_value = sum(lot.qty * lot.unit_cost for lot in open_lots)
        p.avg_cost = (p.invested_value / p.quantity) if p.quantity > 1e-9 else 0.0

    return list(pos.values()), round(total_realized, 4)


def matched_trades(trades: Iterable[dict], actions: Iterable[dict] | None = None) -> list[dict]:
    """The trade list with sell quantity trimmed to what FIFO could actually match.

    A sell with no matching buy in the tradebook has an unknown cost basis — a demerger
    credit (RAYMONDREL), an IPO allotment (HDBFS), a bonus, an off-market transfer-in.
    compute_positions already refuses to book P&L on that quantity. But cash-flow based
    series (net capital deployed, the benchmark's index units) were still counting its
    PROCEEDS as money withdrawn, so on the chart it showed up as pure profit: one real
    account's chart jumped ~60% in a day on a sale of shares it never bought.

    Dropping the unmatched quantity from the sells makes every derived series describe the
    same set of shares the P&L does, so chart P&L equals realized + unrealized exactly.
    Buys are untouched. Sells fully matched are returned unchanged (same dict object).
    """
    trades, sym_isin, _display = _prep(trades)

    stream: list[tuple] = []
    for i, t in enumerate(trades):
        prio = 0 if str(t.get("trade_type", "")).lower() == "buy" else 1
        stream.append((str(t.get("trade_date", "")), prio, str(t.get("order_execution_time", "")), "T", (i, t)))
    for ex, key, mult, atype in _adjustment_events(actions, sym_isin):
        stream.append((ex, -1, "", "A", (key, mult, atype)))
    stream.sort(key=lambda x: (x[0], x[1], x[2]))

    lots: dict[str, deque[Lot]] = defaultdict(deque)
    matched_qty: dict[int, float] = {}

    for _d, _p, _tm, kind, payload in stream:
        if kind == "A":
            key, mult, _atype = payload
            for lot in lots.get(key, ()):
                lot.qty *= mult
                lot.unit_cost /= mult
            continue

        i, t = payload
        key = _rkey_of(t, sym_isin)
        qty = _num(t.get("quantity"))
        if qty <= 0:
            continue
        ttype = str(t.get("trade_type", "")).lower()
        if ttype == "buy":
            lots[key].append(Lot(qty=qty, unit_cost=0.0, trade_date=str(t.get("trade_date", ""))))
        elif ttype == "sell":
            remaining = qty
            dq = lots[key]
            while remaining > 1e-9 and dq:
                lot = dq[0]
                take = min(remaining, lot.qty)
                lot.qty -= take
                remaining -= take
                if lot.qty <= 1e-9:
                    dq.popleft()
            matched_qty[i] = qty - remaining

    out: list[dict] = []
    for i, t in enumerate(trades):
        if str(t.get("trade_type", "")).lower() != "sell":
            out.append(t)
            continue
        qty = _num(t.get("quantity"))
        m = matched_qty.get(i, qty)
        if qty <= 0 or m >= qty - 1e-9:
            out.append(t)
        elif m > 1e-9:
            frac = m / qty
            out.append({**t, "quantity": m, "charges": _num(t.get("charges")) * frac,
                        "trade_value": _num(t.get("trade_value")) * frac})
        # m == 0: the whole sell is unmatched — drop it
    return out


def compute_round_trips(trades: Iterable[dict]) -> list[dict]:
    """FIFO-matched closed round trips ("playbook" rows): each row is one buy-lot
    slice matched against a sell. A sell spanning multiple buy lots produces one row
    per lot consumed; a buy sold off in pieces produces one row per piece sold.
    Only closed (bought-and-sold) quantity is returned — open positions have no row.
    """
    trades, sym_isin, display = _prep(trades)

    lots: dict[str, deque[Lot]] = defaultdict(deque)
    round_trips: list[dict] = []

    for t in trades:
        key = _rkey_of(t, sym_isin)
        symbol = display.get(key, str(t.get("symbol")))
        qty = _num(t.get("quantity"))
        price = _num(t.get("price"))
        charges = _num(t.get("charges"))
        ttype = str(t.get("trade_type", "")).lower()
        date = str(t.get("trade_date", ""))
        if qty <= 0:
            continue

        if ttype == "buy":
            unit_cost = (price * qty + charges) / qty
            lots[key].append(Lot(qty=qty, unit_cost=unit_cost, trade_date=date, fingerprint=t.get("fingerprint")))

        elif ttype == "sell":
            remaining = qty
            sell_charge_per_unit = charges / qty
            dq = lots[key]
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


#: Tradebook `segment` values that represent cash-market equity, i.e. positions that are
#: paid for in full and whose trade value therefore IS capital deployed.
EQUITY_SEGMENTS = {"EQ", "EQUITY", "CASH", "BE", "BSE_EQ", "NSE_EQ"}


def split_segments(trades: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Split cash-equity trades from derivative (F&O / NRML) trades.

    This matters for capital, not just tidiness. A futures or options trade's `trade_value`
    is NOTIONAL — a contract carrying 10L of notional may be held against roughly 1.5L of
    margin. Feeding that notional into the FIFO engine and into peak capital would report
    several times the money the investor actually put up, and would swamp the equity book
    it is averaged with. Derivatives also expire rather than being sold, so a held-to-expiry
    contract leaves a phantom open lot that never clears.

    Until margin data is available there is nothing meaningful to say about a derivative's
    "invested value", so these are separated out and reported on their own P&L terms.

    A missing or blank `segment` is treated as equity: older imported rows predate the field
    and dropping them would silently empty an existing client's portfolio.

    Returns (equity_trades, derivative_trades).
    """
    equity: list[dict] = []
    derivatives: list[dict] = []
    for t in trades:
        seg = str(t.get("segment") or "").strip().upper()
        (equity if not seg or seg in EQUITY_SEGMENTS else derivatives).append(t)
    return equity, derivatives


def split_intraday(trades: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Separate same-day round-trip (intraday/speculative) trades from delivery trades.

    Zerodha's raw tradebook export carries no Product column (MIS vs CNC/NRML) — it's
    just symbol/date/type/qty/price — so there is no direct broker signal for which
    trades were intraday. That isn't a gap this has to work around: Indian tax law
    (Section 43(5)) defines intraday itself this way — a buy and a sell of the SAME stock
    on the SAME day, without taking delivery, IS speculative business income. Same-day
    matching is the legally correct definition, not a heuristic.

    For each (symbol, date) with trades on both sides: the smaller of that day's total
    buy qty and total sell qty is the matched (intraday) quantity, valued at that day's
    buy/sell VWAP (real fills are often several small lots at slightly different prices,
    so VWAP is the fair price to attribute rather than picking one fill arbitrarily).
    Any leftover — buy_qty != sell_qty for the day — genuinely changed the delivery
    position and is kept as ONE synthetic row (at that day's VWAP, carrying isin/exchange/
    series metadata from an actual row that day) so the FIFO engine still sees the right
    net quantity and cash flow for what was actually taken into/out of delivery.

    Returns (delivery_trades, intraday_trades). intraday_trades are summary records
    ({symbol, date, quantity, buy_price, sell_price, pnl}), not raw buy/sell rows — there
    is nothing further for the FIFO engine to do with a same-day round trip.
    """
    trades = list(trades)
    by_day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in trades:
        by_day[(t.get("symbol"), t.get("trade_date"))].append(t)

    delivery: list[dict] = []
    intraday: list[dict] = []

    for (symbol, day), rows in by_day.items():
        buys = [r for r in rows if str(r.get("trade_type", "")).lower() == "buy"]
        sells = [r for r in rows if str(r.get("trade_type", "")).lower() == "sell"]
        buy_qty = sum(r["quantity"] for r in buys)
        sell_qty = sum(r["quantity"] for r in sells)

        if not buys or not sells or min(buy_qty, sell_qty) <= 0:
            delivery.extend(rows)  # only one side traded this day — nothing to match
            continue

        matched = min(buy_qty, sell_qty)
        buy_val = sum(r["quantity"] * r["price"] for r in buys)
        sell_val = sum(r["quantity"] * r["price"] for r in sells)
        vwap_buy = buy_val / buy_qty
        vwap_sell = sell_val / sell_qty

        intraday.append({
            "symbol": symbol, "date": day, "quantity": round(matched, 6),
            "buy_price": round(vwap_buy, 4), "sell_price": round(vwap_sell, 4),
            "pnl": round(matched * (vwap_sell - vwap_buy), 2),
        })

        leftover = buy_qty - sell_qty  # >0: net buy carried to delivery; <0: net sell reduced a prior holding
        if abs(leftover) > 1e-9:
            side_rows = buys if leftover > 0 else sells
            vwap = vwap_buy if leftover > 0 else vwap_sell
            synthetic = {
                **side_rows[0],
                "quantity": round(abs(leftover), 6),
                "price": round(vwap, 4),
                "trade_type": "buy" if leftover > 0 else "sell",
                "trade_id": f"{side_rows[0].get('trade_id', '')}-delivery",
            }
            delivery.append(synthetic)
        # else: fully offset same day — nothing carries to delivery

    return delivery, intraday
