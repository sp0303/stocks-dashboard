"""Phase 3 trade-planning calculator. These pin the arithmetic that must never be wrong:
the ATR stop, R-multiple targets, reward-to-risk to a real level, and position size that
respects the user's risk-per-trade and every cap. Pure: no Mongo, no network.
"""
from app.services import screener_plan as P
from app.services import screener_setups as S
from app.services.orb.config import OrbConfig


def series(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    vols = vols or [100000] * n
    return [{"date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "o": int(closes[i] * 100), "h": int(highs[i] * 100),
             "l": int(lows[i] * 100), "c": int(closes[i] * 100), "v": vols[i]}
            for i in range(n)]


def test_stop_is_atr_based_and_risk_is_the_gap():
    plan = P.plan_swing_trade(series([100.0] * 60), label=S.NEAR_BREAKOUT)
    geo = S.SETUP_GEOMETRY[S.NEAR_BREAKOUT]
    assert abs(plan.stop - (plan.entry - geo["stop_atr"] * plan.atr)) < 1e-6
    assert abs(plan.risk_per_share - (plan.entry - plan.stop)) < 1e-6


def test_targets_are_multiples_of_the_users_R():
    plan = P.plan_swing_trade(series([100.0] * 60), label=S.PULLBACK)
    geo = S.SETUP_GEOMETRY[S.PULLBACK]
    assert plan.t1_r == P.T1_R
    assert abs(plan.t2_r - geo["target_atr"] / geo["stop_atr"]) < 1e-6
    assert abs(plan.t1 - (plan.entry + plan.t1_r * plan.risk_per_share)) < 1e-6
    assert abs(plan.t2 - (plan.entry + plan.t2_r * plan.risk_per_share)) < 1e-6


def test_reward_to_risk_uses_a_real_overhead_level():
    # Range-bound: a clear prior high ~110 sits above a current price ~100.
    closes = [100.0, 105.0, 110.0, 106.0, 102.0] * 11 + [100.0] * 5
    plan = P.plan_swing_trade(series(closes))
    assert plan.next_resistance is not None and plan.next_resistance > plan.entry
    assert abs(plan.rr_to_resistance
               - (plan.next_resistance - plan.entry) / plan.risk_per_share) < 1e-6


def test_new_highs_have_no_overhead_resistance():
    plan = P.plan_swing_trade(series([100.0 + i * 0.5 for i in range(60)]))
    assert plan.next_resistance is None and plan.rr_to_resistance is None
    assert any("new highs" in n for n in plan.notes)


def test_position_size_respects_risk_per_trade_when_uncapped():
    # Loosen caps and give deep liquidity so pure risk sizing governs.
    cfg = OrbConfig(max_notional_pct=100.0, max_qty_pct_of_median_vol=100.0)
    plan = P.plan_swing_trade(series([100.0] * 60, vols=[10_000_000] * 60),
                              label=S.NEAR_BREAKOUT, cfg=cfg,
                              capital=1_000_000.0, risk_per_trade_pct=0.75)
    # never risk more than the intended rupees; match it to within one share's risk
    assert plan.risk_amount <= 1_000_000 * 0.75 / 100 + 1e-6
    assert plan.risk_amount >= 1_000_000 * 0.75 / 100 - plan.risk_per_share


def test_notional_cap_binds_for_low_priced_names():
    cfg = OrbConfig(max_notional_pct=15.0, max_qty_pct_of_median_vol=100.0)
    plan = P.plan_swing_trade(series([50.0] * 60, vols=[10_000_000] * 60),
                              cfg=cfg, capital=1_000_000.0, risk_per_trade_pct=5.0)
    assert plan.notional <= 1_000_000 * 0.15 + plan.entry     # within one share
    assert any("notional" in n for n in plan.notes)


def test_liquidity_cap_binds_for_thin_names():
    cfg = OrbConfig(max_notional_pct=100.0, max_qty_pct_of_median_vol=1.0)
    plan = P.plan_swing_trade(series([100.0] * 60, vols=[500] * 60),
                              cfg=cfg, capital=10_000_000.0, risk_per_trade_pct=5.0)
    assert plan.qty <= int(500 * 1.0 / 100.0)
    assert any("liquidity" in n for n in plan.notes)


def test_cost_is_a_fraction_of_R():
    plan = P.plan_swing_trade(series([100.0] * 60), label=S.NEAR_BREAKOUT)
    assert plan.est_cost > 0 and 0 < plan.cost_in_r < 1     # cost should be a slice of 1R


def test_fragile_setups_are_flagged_not_sold():
    plan = P.plan_swing_trade(series([100.0] * 60), label=S.NEAR_BREAKOUT)
    assert plan.setup_fragile is True
    assert any("FRAGILE" in n for n in plan.notes)
    # the plan carries a context label, never a buy/sell action
    assert plan.label in S.ALL_LABELS


def test_too_little_data_returns_none():
    assert P.plan_swing_trade(series([100.0] * 10)) is None


def test_expected_hold_comes_from_measured_stats():
    plan = P.plan_swing_trade(series([100.0] * 60), label=S.OVERSOLD_REVERSAL)
    assert plan.expected_hold_days == S.SETUP_STATS[S.OVERSOLD_REVERSAL]["median_hold"]
