"""Phase 3 — the swing trade-planning calculator.

Objective arithmetic on chart facts, parameterised by the user's own risk — **not a
recommendation**. Given a stock's daily rows and (optionally) its Phase 2 setup label, it
returns: an ATR-based invalidation (stop), the reward-to-risk to the next overhead
resistance, targets as multiples of the user's R, a measured expected holding period, and a
position size derived from the user's risk-per-trade and the ATR stop. It makes no buy/sell
call and sets no house price target — every number is either a fact off the chart or a
consequence of the user's own inputs (that is the Phase 3 gate).

The risk layer is deliberately the ORB one: the same position-sizing math (`plan_trade`)
and the same statutory cost model (`OrbConfig`'s charge fields), so swing and intraday size
and cost a trade identically and cannot drift.

Rows are the daily store shape: {"date","o","h","l","c" (paise),"v"}. Prices returned are
rupees.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import screener_factors as F
from . import screener_setups as S
from .orb.config import OrbConfig

# T1 is a partial-profit rung at the user's 1R; T2 rides the setup's measured target (in R).
# A generic profile is used when a stock carries no tradable setup label, so the calculator
# still works as a pure risk tool on any name.
GENERIC_GEOMETRY = {"stop_atr": 1.5, "target_atr": 3.0, "horizon": 15}
T1_R = 1.0


@dataclass
class SwingPlan:
    symbol: str | None
    label: str
    entry: float                 # last close, rupees
    atr: float
    stop: float                  # entry - stop_atr * ATR
    risk_per_share: float        # entry - stop  (= 1R per share)
    t1: float                    # entry + T1_R * R
    t2: float                    # entry + (target_atr/stop_atr) * R
    t1_r: float                  # = T1_R
    t2_r: float                  # target in R units
    next_resistance: float | None
    rr_to_resistance: float | None   # (resistance - entry) / risk_per_share
    qty: int
    notional: float
    risk_amount: float           # qty * risk_per_share (rupees the user risks to the stop)
    est_cost: float              # round-trip statutory + broker charges, rupees
    cost_in_r: float             # est_cost / risk_amount — cost as a fraction of 1R
    expected_hold_days: int | None
    setup_exp_r: float | None    # measured, FRAGILE — context only
    setup_fragile: bool
    notes: list[str]


def plan_levels(rows: list[dict], label: str | None) -> dict | None:
    """The capital-independent half of a plan — entry, ATR stop, R, targets, R:R to
    resistance, expected hold, and the fragility flag. Safe to embed in the shared screener
    snapshot; position size (which needs the user's capital) is a separate call."""
    p = plan_swing_trade(rows, label)
    if p is None:
        return None
    return {
        "label": p.label, "entry": round(p.entry, 2), "stop": round(p.stop, 2),
        "risk_per_share": round(p.risk_per_share, 2),
        "t1": round(p.t1, 2), "t2": round(p.t2, 2), "t2_r": round(p.t2_r, 2),
        "next_resistance": round(p.next_resistance, 2) if p.next_resistance else None,
        "rr_to_resistance": round(p.rr_to_resistance, 2) if p.rr_to_resistance else None,
        "expected_hold_days": p.expected_hold_days,
        "setup_exp_r": p.setup_exp_r, "setup_fragile": p.setup_fragile,
        "notes": p.notes,
    }


def _median_volume(rows: list[dict], days: int = 20) -> float | None:
    vols = sorted(r["v"] for r in rows[-days:] if r.get("v"))
    return vols[len(vols) // 2] if vols else None


def _next_resistance(rows: list[dict], entry: float, atr: float,
                     lookback: int = 120) -> float | None:
    """Nearest *prior* overhead high in the last `lookback` sessions that sits at least half
    an ATR above the entry — a factual level the price has traded to and must clear to make
    progress. The current bar is excluded (its own wick is not resistance), and levels
    within noise of the entry are ignored. None when price is at new highs with clear air
    above."""
    prior = rows[-lookback - 1: -1] if len(rows) > 1 else []
    threshold = entry + 0.5 * atr
    above = [r["h"] / 100 for r in prior if r.get("h") is not None and r["h"] / 100 >= threshold]
    return min(above) if above else None


def plan_swing_trade(rows: list[dict], label: str | None = None, *, symbol: str | None = None,
                     cfg: OrbConfig | None = None, capital: float | None = None,
                     risk_per_trade_pct: float | None = None) -> SwingPlan | None:
    """Build a factual plan for entering at the last close. `label` (a Phase 2 setup) picks
    the stop/target geometry and the measured hold; without one, a generic risk profile is
    used. Returns None only if there is too little data to place an ATR stop."""
    cfg = cfg or OrbConfig()
    capital = capital if capital is not None else cfg.capital
    risk_pct = risk_per_trade_pct if risk_per_trade_pct is not None else cfg.risk_per_trade_pct

    c = F._closes(rows)
    atr = F._atr(rows)
    if len(c) < 20 or not atr:
        return None
    entry = c[-1]
    if entry <= 0:
        return None

    geo = S.SETUP_GEOMETRY.get(label, GENERIC_GEOMETRY) if label else GENERIC_GEOMETRY
    stop = entry - geo["stop_atr"] * atr
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None

    t2_r = geo["target_atr"] / geo["stop_atr"]
    t1 = entry + T1_R * risk_per_share
    t2 = entry + t2_r * risk_per_share
    resistance = _next_resistance(rows, entry, atr)
    rr_res = ((resistance - entry) / risk_per_share) if resistance else None

    # ── position size: the ORB risk layer's math, on a per-share (not per-tick) stop ──
    risk_rupees = capital * risk_pct / 100.0
    qty = int(risk_rupees / risk_per_share)
    cap_notional = int(capital * cfg.max_notional_pct / 100.0 / entry)
    qty = min(qty, cap_notional)
    notes: list[str] = []
    if qty == cap_notional:
        notes.append(f"size capped by max notional ({cfg.max_notional_pct:g}% of capital)")
    med_vol = _median_volume(rows)
    if med_vol:
        cap_liq = int(med_vol * cfg.max_qty_pct_of_median_vol / 100.0)
        if cap_liq < qty:
            qty = cap_liq
            notes.append(f"size capped by liquidity ({cfg.max_qty_pct_of_median_vol:g}% "
                         f"of 20d median volume)")
    if qty <= 0:
        return None

    notional = qty * entry
    risk_amount = qty * risk_per_share
    est_cost = _round_trip_cost(cfg, notional, notional)     # both legs ≈ entry notional
    cost_in_r = est_cost / risk_amount if risk_amount else 0.0

    stats = S.SETUP_STATS.get(label) if label else None
    if resistance is None:
        notes.append("no overhead resistance in ~120 sessions (at/near new highs) — R:R "
                     "to a target is open-ended; T2 shown in R only")
    if stats and stats.get("fragile"):
        notes.append("setup expectancy is FRAGILE (positive first half of the backtest, "
                     "negative second) — treat labels as context, not a signal")

    return SwingPlan(
        symbol=symbol, label=label or S.NO_SETUP, entry=entry, atr=atr, stop=stop,
        risk_per_share=risk_per_share, t1=t1, t2=t2, t1_r=T1_R, t2_r=t2_r,
        next_resistance=resistance, rr_to_resistance=rr_res, qty=qty, notional=notional,
        risk_amount=risk_amount, est_cost=est_cost, cost_in_r=cost_in_r,
        expected_hold_days=(stats or {}).get("median_hold"),
        setup_exp_r=(stats or {}).get("exp_r"),
        setup_fragile=bool(stats and stats.get("fragile")), notes=notes)


def _round_trip_cost(cfg: OrbConfig, buy_val: float, sell_val: float) -> float:
    """All statutory + broker charges for one buy and one sell leg, rupees. Mirrors
    `scripts/orb_backtest._round_trip_cost` exactly (same OrbConfig fields) so swing and
    intraday cost identically — kept here to avoid an app→scripts import."""
    turnover = buy_val + sell_val
    brokerage = (min(cfg.brokerage_pct / 100 * buy_val, cfg.brokerage_cap)
                 + min(cfg.brokerage_pct / 100 * sell_val, cfg.brokerage_cap))
    stt = cfg.stt_sell_pct / 100 * sell_val
    exch = cfg.exchange_txn_pct / 100 * turnover
    stamp = cfg.stamp_buy_pct / 100 * buy_val
    sebi = cfg.sebi_per_crore * turnover / 1e7
    gst = cfg.gst_pct / 100 * (brokerage + exch + sebi)
    return brokerage + stt + exch + stamp + sebi + gst
