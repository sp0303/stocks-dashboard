"""Single-pass O(N) FIFO Portfolio Engine adhering to Rules R1, R6, R7, R8, R16.

Matching pool: delivery shares sit in one demat account whatever exchange they were
bought on, so a sell on NSE closes the oldest lot of that symbol even if it was bought
on BSE. Keying the FIFO queue by (symbol, exchange) left a phantom open BSE lot and an
"unmatched" NSE sell for every cross-exchange round trip. Each lot keeps the exchange it
was bought on, and is **priced** strictly on that (symbol, exchange) (R6.1).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from pi_core.engine.corporate_actions import apply_corporate_actions
from pi_core.models import (
    CorporateAction,
    DailySnapshot,
    Lot,
    MatchedTrade,
    PositionMark,
    Side,
    Trade,
    UnmatchedSell,
)

EPS = 1e-6
Key = tuple[str, str]
PriceLookup = Callable[[str, str, date], float | None]


@dataclass
class EngineResult:
    """Complete immutable output of running the single-pass FIFO engine."""

    snapshots: list[DailySnapshot]
    matched_trades: list[MatchedTrade]
    unmatched_sells: list[UnmatchedSell]
    open_lots: dict[tuple[str, str], list[Lot]]  # keyed (symbol, exchange of the lot)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_realized_pnl(self) -> float:
        return sum(m.realized_pnl for m in self.matched_trades)

    @property
    def latest_snapshot(self) -> DailySnapshot | None:
        return self.snapshots[-1] if self.snapshots else None


@dataclass
class _Leg:
    """One day's activity on a (symbol, exchange) key."""

    flow: float = 0.0
    buys: list[tuple[float, float]] = field(default_factory=list)
    sells: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class _State:
    pools: dict[Key, deque] = field(default_factory=lambda: defaultdict(deque))
    matched: list[MatchedTrade] = field(default_factory=list)
    unmatched: list[UnmatchedSell] = field(default_factory=list)
    realized: float = 0.0
    net_cash: float = 0.0
    peak: float = 0.0


def _pool_key(t: Trade) -> Key:
    # One FIFO queue per symbol and segment; the exchange is a pricing attribute.
    # (symbol, x) tuples keep apply_corporate_actions' (sym, _) iteration valid.
    return (t.symbol, t.segment.value)


def _buy(st: _State, t: Trade, legs: dict[Key, _Leg]) -> float:
    chg = t.charges if t.charges is not None else 0.0
    per_unit = chg / t.quantity if t.quantity > 0 else 0.0
    leg = legs.setdefault((t.symbol, t.exchange), _Leg())
    leg.flow += t.quantity * t.price + chg
    leg.buys.append((t.quantity, t.price))
    st.pools[_pool_key(t)].append(
        Lot(
            t.trade_id,
            t.trade_date,
            t.symbol,
            t.exchange,
            t.quantity,
            t.quantity,
            t.price,
            per_unit,
        )
    )
    return t.quantity * t.price + chg


def _sell(st: _State, t: Trade, legs: dict[Key, _Leg]) -> float:
    chg = t.charges if t.charges is not None else 0.0
    per_unit = chg / t.quantity if t.quantity > 0 else 0.0
    queue = st.pools[_pool_key(t)]
    remaining, proceeds = t.quantity, 0.0
    while remaining > EPS and queue:
        lot = queue[0]
        qty = min(lot.quantity, remaining)
        m = MatchedTrade(
            t.trade_id,
            lot.lot_id,
            t.symbol,
            t.exchange,
            lot.buy_date,
            t.trade_date,
            qty,
            lot.price,
            t.price,
            qty * lot.charges_per_unit,
            qty * per_unit,
        )
        st.matched.append(m)
        st.realized += m.realized_pnl
        lot.quantity -= qty
        remaining -= qty
        if lot.quantity <= EPS:
            queue.popleft()
        slice_proceeds = qty * t.price - qty * per_unit
        proceeds += slice_proceeds
        # The cash leaves the key the shares were held under (the lot's exchange).
        leg = legs.setdefault((t.symbol, lot.exchange), _Leg())
        leg.flow -= slice_proceeds
        leg.sells.append((qty, t.price))
    if remaining > EPS:  # Rule R7: unknown cost basis, excluded and reported
        st.unmatched.append(
            UnmatchedSell(
                t.trade_id,
                t.trade_date,
                t.symbol,
                t.exchange,
                remaining,
                t.price,
                remaining * t.price,
            )
        )
    return -proceeds


def _holdings(st: _State) -> dict[Key, list[float]]:
    """(symbol, lot exchange) -> [quantity, cost] over open lots."""
    out: dict[Key, list[float]] = {}
    for lots in st.pools.values():
        for lot in lots:
            if lot.quantity > EPS:
                acc = out.setdefault((lot.symbol, lot.exchange), [0.0, 0.0])
                acc[0] += lot.quantity
                acc[1] += lot.total_cost
    return out


class FIFOEngine:
    """Single-pass deterministic FIFO engine."""

    def __init__(
        self,
        trades: list[Trade],
        corporate_actions: list[CorporateAction] | None = None,
        price_lookup: PriceLookup | None = None,
    ) -> None:
        self.trades = trades
        self.corporate_actions = corporate_actions or []
        self.price_lookup: PriceLookup = price_lookup or (lambda sym, exch, d: None)

    def _active_days(self, calendar: list[date], as_of: date | None) -> list[date]:
        first = min(t.trade_date for t in self.trades)
        last = as_of or max(
            max(t.trade_date for t in self.trades),
            max((ca.ex_date for ca in self.corporate_actions), default=first),
        )
        days = {d for d in calendar if first <= d <= last}
        days.update(t.trade_date for t in self.trades if first <= t.trade_date <= last)
        return sorted(days)

    def _price(self, key: Key, d: date | None) -> float | None:
        if d is None:
            return None
        p = self.price_lookup(key[0], key[1], d)
        return p if p is not None and p > 0 else None

    def _snapshot(
        self, st: _State, day: date, prev_day: date | None, legs: dict[Key, _Leg], flow: float
    ) -> DailySnapshot:
        held = _holdings(st)
        marks: dict[Key, PositionMark] = {}
        mv = cost = unreal = unpriced_cost = 0.0
        unpriced: list[Key] = []
        for key in sorted(set(held) | set(legs)):
            qty, k_cost = held.get(key, (0.0, 0.0))
            leg = legs.get(key)
            mark = PositionMark(
                quantity=qty,
                cost=k_cost,
                price=self._price(key, day),
                flow=leg.flow if leg else 0.0,
                buys=tuple(leg.buys) if leg else (),
                sells=tuple(leg.sells) if leg else (),
                prev_price=self._price(key, prev_day) if leg else None,
            )
            marks[key] = mark
            if not mark.is_open:
                continue
            if mark.priced:
                mv += mark.value
                cost += k_cost
                unreal += mark.value - k_cost
            else:  # R6.4: excluded from BOTH cost and value, and listed
                unpriced_cost += k_cost
                unpriced.append(key)
        return DailySnapshot(
            snapshot_date=day,
            open_cost=cost,
            market_value=mv,
            realized_pnl_cumulative=st.realized,
            unrealized_pnl=unreal,
            capital_deployed=st.peak,
            net_cash_flow=flow,
            open_positions_count=sum(1 for m in marks.values() if m.is_open),
            unmatched_sells_value=sum(u.proceeds for u in st.unmatched),
            unpriced_cost=unpriced_cost,
            unpriced=tuple(unpriced),
            marks=marks,
        )

    def run(self, trading_calendar: list[date], as_of: date | None = None) -> EngineResult:
        """Executes the single-pass engine over the calendar up to as_of date."""
        if not self.trades:
            return EngineResult([], [], [], {}, ["No trades provided to engine."])
        trades_by_date: dict[date, list[Trade]] = defaultdict(list)
        for t in self.trades:
            trades_by_date[t.trade_date].append(t)
        actions_by_date: dict[date, list[CorporateAction]] = defaultdict(list)
        for ca in self.corporate_actions:
            actions_by_date[ca.ex_date].append(ca)

        st, snapshots, warnings = _State(), [], []
        prev_day: date | None = None
        for day in self._active_days(trading_calendar, as_of):
            if actions_by_date.get(day):  # R8: before same-day trades
                warnings.extend(apply_corporate_actions(st.pools, actions_by_date[day]))
            legs: dict[Key, _Leg] = {}
            flow = 0.0  # buys − sells netted on the day (R1)
            for t in sorted(
                trades_by_date.get(day, []),
                key=lambda t: (0 if t.side == Side.BUY else 1, t.trade_id),
            ):
                flow += _buy(st, t, legs) if t.side == Side.BUY else _sell(st, t, legs)
            st.net_cash += flow
            st.peak = max(st.peak, st.net_cash)
            snapshots.append(self._snapshot(st, day, prev_day, legs, flow))
            prev_day = day

        final: dict[Key, list[Lot]] = defaultdict(list)
        for lots in st.pools.values():
            for lot in lots:
                if lot.quantity > EPS:
                    final[(lot.symbol, lot.exchange)].append(lot)
        return EngineResult(snapshots, st.matched, st.unmatched, dict(final), warnings)
