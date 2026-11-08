"""Time-Weighted Return (TWR) daily NAV series adhering to Rules R2, R6, R16, R17.

    r_t  = (V_t − V_{t−1} − F_t) / B_t
    B_t  = V_{t−1} + Σ_buys q·p·(1 − m) − Σ_sells q·c_{t−1}·(1 − m)
    m    = clamp((p − c_{t−1}) / (c_t − c_{t−1}), 0, 1);  0.5 if |c_t/c_{t−1} − 1| < 0.5 %

When the engine supplies per-holding marks (``DailySnapshot.marks``) the sums run per
(symbol, exchange) key, and a key contributes to day t only when its value is *measured*
on both t−1 and t. That keeps V and F describing the same shares:

* R6: an unpriced holding is outside V, so its trades are outside F too. A holding that
  gains or loses its price is a transfer into/out of the measured book, never a return
  (holding it at cost and then pricing it booked the whole unrealised gain in one day).
* R17: a trade whose execution price is far from that day's close (outside 0.8×–1.25×),
  or a held position whose value jumps beyond 0.5×–2× with no trade, is a price-basis
  break (adjusted history, a split the feed never reported, a bad tick). The key is
  left out of that day and a warning is raised, rather than compounding it into NAV.

Snapshots without marks (hand-built series) fall back to the book-level formula.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from itertools import pairwise

from pi_core.models import DailySnapshot, NAVPoint, PositionMark, Side, Trade

PriceLookup = Callable[[str, str, date], float | None]
EPS = 1e-6
BASIS_BAND = (0.8, 1.25)  # trade price / same-day close; v1's tolerance (R17)
JUMP_BAND = (0.5, 2.0)  # held value t / t−1 with no trade


def _moved_before(p: float, c_prev: float | None, c_curr: float | None) -> float:
    """m: share of the day's price move already done when the trade executed (R2)."""
    if c_prev is None or c_curr is None or c_prev <= 0 or abs(c_curr / c_prev - 1.0) < 0.005:
        return 0.5
    return max(0.0, min(1.0, (p - c_prev) / (c_curr - c_prev)))


def _base_delta(
    buys: list[tuple[float, float]],
    sells: list[tuple[float, float]],
    c_prev: float | None,
    c_curr: float | None,
) -> float:
    add = sum(q * p * (1.0 - _moved_before(p, c_prev, c_curr)) for q, p in buys)
    ref = c_prev if c_prev is not None and c_prev > 0 else None
    sub = sum(q * (ref or p) * (1.0 - _moved_before(p, c_prev, c_curr)) for q, p in sells)
    return add - sub


def _key_day(
    key: tuple[str, str], mk: PositionMark, prev: PositionMark | None, d: date
) -> tuple[tuple[float, float] | None, str | None]:
    """(pnl, base) for one key on one day, or (None, warning|None) if it is not measured."""
    prev_open = prev is not None and prev.is_open
    if (prev_open and not prev.priced) or (mk.is_open and not mk.priced):  # type: ignore[union-attr]
        return None, None  # R6: enters/leaves the measured book; a transfer, not a return
    v_prev = prev.value if prev_open else 0.0  # type: ignore[union-attr]
    legs = mk.buys + mk.sells
    if mk.priced and any(not (BASIS_BAND[0] < p / mk.price < BASIS_BAND[1]) for _, p in legs):  # type: ignore[operator]
        return (
            None,
            f"Price basis mismatch on {d} for {key[0]}/{key[1]}: trade price vs close {mk.price}; day excluded (R17).",
        )
    if not legs and v_prev > 0 and not (JUMP_BAND[0] < mk.value / v_prev < JUMP_BAND[1]):
        return (
            None,
            f"Price jump on {d} for {key[0]}/{key[1]} ({v_prev:.2f} -> {mk.value:.2f}) with no trade; day excluded (R16/R17).",
        )
    c_prev = prev.price if prev_open else mk.prev_price  # type: ignore[union-attr]
    base = v_prev + _base_delta(list(mk.buys), list(mk.sells), c_prev, mk.price)
    return (mk.value - v_prev - mk.flow, base), None


def _day_from_marks(
    snap: DailySnapshot, prev_snap: DailySnapshot, warnings: list[str]
) -> tuple[float, float, float, float]:
    """Returns (gain, base, measured_value, measured_flow) summed over measured keys."""
    gain = base = value = flow = 0.0
    for key, mk in snap.marks.items():
        res, warn = _key_day(key, mk, prev_snap.marks.get(key), snap.snapshot_date)
        if warn:
            warnings.append(warn)
        if res is None:
            continue
        gain += res[0]
        base += res[1]
        value += mk.value
        flow += mk.flow
    return gain, base, value, flow


def _day_from_aggregate(
    snap: DailySnapshot,
    prev_snap: DailySnapshot,
    day_trades: list[Trade],
    lookup: PriceLookup | None,
) -> tuple[float, float]:
    """Book-level fallback for snapshots without marks: (gain, base)."""
    v_prev = max(prev_snap.market_value, 0.0)
    base = v_prev
    for t in day_trades:
        c_prev = lookup(t.symbol, t.exchange, prev_snap.snapshot_date) if lookup else None
        c_curr = lookup(t.symbol, t.exchange, snap.snapshot_date) if lookup else None
        leg = [(t.quantity, t.price)]
        base += _base_delta(
            leg if t.side == Side.BUY else [], leg if t.side == Side.SELL else [], c_prev, c_curr
        )
    gain = max(snap.market_value, 0.0) - v_prev - snap.net_cash_flow
    return gain, base


def calculate_twr_series(
    snapshots: list[DailySnapshot],
    trades: list[Trade],
    close_price_lookup: PriceLookup | None = None,
    initial_nav: float = 100.0,
) -> tuple[list[NAVPoint], list[str]]:
    """Daily time-weighted NAV indexed to ``initial_nav``. Returns (nav_points, warnings).

    R16: B_t < ₹1 → r_t = 0; r_t ≤ −100 % is a data error (NAV held flat, warning).
    """
    if not snapshots:
        return [], []
    trades_by_date: dict[date, list[Trade]] = defaultdict(list)
    for t in trades:
        trades_by_date[t.trade_date].append(t)

    nav, warnings = initial_nav, []
    first = snapshots[0]
    points = [
        NAVPoint(
            first.snapshot_date,
            nav,
            0.0,
            max(first.market_value, 0.0),
            max(first.market_value, 0.0),
            first.net_cash_flow,
        )
    ]
    for prev_snap, snap in pairwise(snapshots):
        d = snap.snapshot_date
        if snap.marks:
            gain, b_t, _, _ = _day_from_marks(snap, prev_snap, warnings)
        else:
            gain, b_t = _day_from_aggregate(
                snap, prev_snap, trades_by_date.get(d, []), close_price_lookup
            )
        r_t = gain / b_t if b_t >= 1.0 else 0.0
        if r_t <= -1.0:
            warnings.append(
                f"Data error guard triggered on {d}: daily return {r_t:.2%} <= -100%. "
                f"Holding NAV flat at {nav:.2f}."
            )
            r_t = 0.0
        nav = max(0.01, nav * (1.0 + r_t))
        points.append(NAVPoint(d, nav, r_t, b_t, max(snap.market_value, 0.0), snap.net_cash_flow))
    return points, warnings
