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
