"""Phase 4 portfolio-risk gate. Pins the aggregate caps that stop a book from becoming one
big bet: total open risk, per-sector concentration, position count, notional, correlation,
and the event-blackout hook. Pure arithmetic."""
from app.services import screener_portfolio as PF


def cand(sym, sector, risk, notional=10_000, returns=None):
    return PF.Candidate(symbol=sym, sector=sector, risk_amount=risk, notional=notional,
                        returns=returns)


def test_total_open_risk_cap_binds():
    cfg = PF.PortfolioConfig(capital=1_000_000, max_total_open_risk_pct=2.0,
                             max_sector_risk_pct=100, max_positions=99)
    # each risks 0.75% → third would push past the 2% total cap
    cands = [cand(f"S{i}", f"Sec{i}", 7500) for i in range(4)]
    res = PF.assess(cands, cfg)
    assert res.admitted == ["S0", "S1"]
    assert all("total open risk" in r["reason"] for r in res.rejected)
    assert res.open_risk_pct <= 2.0


def test_sector_concentration_cap_binds():
    cfg = PF.PortfolioConfig(capital=1_000_000, max_total_open_risk_pct=100,
                             max_sector_risk_pct=1.5, max_positions=99)
    cands = [cand("A", "Financial", 8000), cand("B", "Financial", 8000),
             cand("C", "Pharma", 8000)]
    res = PF.assess(cands, cfg)
    assert res.admitted == ["A", "C"]                     # B blocked: 2nd Financial breaches 1.5%
    assert res.rejected[0]["symbol"] == "B" and "sector" in res.rejected[0]["reason"]


def test_max_positions_cap():
    cfg = PF.PortfolioConfig(max_total_open_risk_pct=100, max_sector_risk_pct=100,
                             max_positions=2)
    res = PF.assess([cand(f"S{i}", f"Sec{i}", 1000) for i in range(4)], cfg)
    assert len(res.admitted) == 2 and len(res.rejected) == 2


def test_notional_cap_rejects_oversize():
    cfg = PF.PortfolioConfig(capital=1_000_000, max_position_notional_pct=15.0,
                             max_total_open_risk_pct=100, max_sector_risk_pct=100)
    res = PF.assess([cand("BIG", "Auto", 1000, notional=200_000)], cfg)
    assert res.admitted == [] and "notional" in res.rejected[0]["reason"]


def test_event_blackout_hook():
    res = PF.assess([cand("SKIP", "Auto", 1000), cand("OK", "Pharma", 1000)],
                    PF.PortfolioConfig(max_total_open_risk_pct=100, max_sector_risk_pct=100),
                    blackout={"SKIP"})
    assert res.admitted == ["OK"]
    assert res.rejected[0]["symbol"] == "SKIP" and "blackout" in res.rejected[0]["reason"]


def test_correlation_cap_blocks_a_clone():
    base = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, -0.012] * 3
    clone = [x * 1.0 for x in base]                        # perfectly correlated
    cfg = PF.PortfolioConfig(max_total_open_risk_pct=100, max_sector_risk_pct=100,
                             max_correlation=0.8)
    res = PF.assess([cand("A", "Sec1", 1000, returns=base),
                     cand("B", "Sec2", 1000, returns=clone)], cfg)
    assert res.admitted == ["A"]
    assert "correlation" in res.rejected[0]["reason"]


def test_open_positions_consume_budget_first():
    cfg = PF.PortfolioConfig(capital=1_000_000, max_total_open_risk_pct=2.0,
                             max_sector_risk_pct=100, max_positions=99)
    open_pos = [cand("HELD", "Auto", 15000)]              # already 1.5% at risk
    res = PF.assess([cand("NEW", "Pharma", 7500)], cfg, open_positions=open_pos)
    # only 0.5% budget left, NEW wants 0.75% → rejected
    assert res.admitted == [] and "total open risk" in res.rejected[0]["reason"]
