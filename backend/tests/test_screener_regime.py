"""Volatility-scaling / crash-protection primitives (Barroso–Santa-Clara). Pure arithmetic;
these pin the de-risking direction and the clamps."""
from app.services import screener_regime as R
from app.services import screener_portfolio as PF


def test_realized_vol_rises_with_dispersion():
    calm = [0.001, -0.001] * 40
    wild = [0.05, -0.05] * 40
    assert R.realized_vol(calm) < R.realized_vol(wild)


def test_realized_vol_needs_history():
    assert R.realized_vol([0.01, 0.02]) is None or R.realized_vol([0.01, 0.02]) >= 0
    assert R.realized_vol([]) is None


def test_vol_scale_derisks_when_vol_is_high():
    target = 0.01
    hi = R.vol_scale(0.02, target)      # vol double target → half exposure
    lo = R.vol_scale(0.005, target)     # vol half target → double exposure (capped)
    assert abs(hi - 0.5) < 1e-9
    assert lo > 1.0
    assert R.vol_scale(0.02, target) < R.vol_scale(0.01, target)   # higher vol → less exposure


def test_vol_scale_is_clamped_and_safe():
    assert R.vol_scale(0.0001, 0.01, cap=2.5) == 2.5     # tiny vol → capped, not infinite
    assert R.vol_scale(None, 0.01) == 1.0                # unknown → neutral
    assert R.vol_scale(0.0, 0.01, cap=2.0) == 2.0        # zero vol → cap


def test_ewma_vol_reacts_faster_than_flat_window():
    # a calm history then a fresh vol burst: EWMA (recent-weighted) should read higher than
    # the flat trailing mean over a long window.
    rets = [0.001, -0.001] * 60 + [0.05, -0.05, 0.05, -0.05]
    assert R.ewma_vol(rets, span=10) > R.realized_vol(rets, lookback=120)


def test_drawdown_from_peak_and_scale():
    assert R.drawdown_from_peak([100, 110, 99]) == (99 - 110) / 110      # ~-10%
    assert R.drawdown_from_peak([100, 110, 110]) == 0.0                  # at the high
    assert R.drawdown_scale(0.0) == 1.0                                  # no drawdown → full
    assert R.drawdown_scale(-0.10, knee=-0.10, floor=0.0) == 0.0         # at knee → floor
    assert 0.0 < R.drawdown_scale(-0.05, knee=-0.10, floor=0.0) < 1.0    # partial


def test_calibrate_target_is_the_median():
    assert R.calibrate_target([0.01, 0.02, 0.03]) == 0.02
    assert R.calibrate_target([]) is None


def test_exposure_multiplier_neutral_without_target():
    assert R.exposure_multiplier([0.01, -0.02] * 40) == 1.0       # no target → neutral 1.0


def test_exposure_scale_shrinks_the_portfolio_budget():
    # Same candidates, but a 0.5 exposure scale should admit strictly fewer / less risk.
    cfg = PF.PortfolioConfig(capital=1_000_000, max_total_open_risk_pct=6.0,
                             max_sector_risk_pct=100, max_positions=99)
    cands = [PF.Candidate(f"S{i}", f"Sec{i}", 7500, 10_000) for i in range(10)]
    full = PF.assess(cands, cfg, exposure_scale=1.0)
    half = PF.assess(cands, cfg, exposure_scale=0.5)
    assert len(half.admitted) < len(full.admitted)
    assert half.open_risk_pct <= full.open_risk_pct
