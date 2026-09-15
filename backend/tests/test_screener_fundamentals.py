"""Value & quality factors (live-only). Pins the value direction (cheaper = higher), the
bank margin carve-out, and graceful handling of missing data. Pure."""
from app.services import screener_fundamentals as VQ


def test_earnings_yield_is_inverse_pe_and_guards_nonpositive():
    assert VQ.earnings_yield({"pe": 20.0}) == 5.0
    assert VQ.earnings_yield({"pe": 0}) is None
    assert VQ.earnings_yield({"pe": -8.0}) is None          # loss-maker: undefined, not cheap
    assert VQ.earnings_yield({}) is None


def test_banks_drop_operating_margin():
    assert VQ.quality_components({"is_banking": True, "opm": 40, "pat_yoy": 12})["opm"] is None
    assert VQ.quality_components({"opm": 25, "pat_yoy": 12})["opm"] == 25


def test_score_universe_ranks_value_and_quality():
    kpis = {
        "CHEAP": {"pe": 8.0, "opm": 20, "pat_yoy": 25, "rev_yoy": 15},
        "MID":   {"pe": 20.0, "opm": 15, "pat_yoy": 10, "rev_yoy": 8},
        "RICH":  {"pe": 60.0, "opm": 5, "pat_yoy": -5, "rev_yoy": 2},
    }
    out = VQ.score_universe(kpis)
    # cheapest P/E → highest value z; strongest fundamentals → highest quality z
    assert out["CHEAP"]["value_score"] > out["MID"]["value_score"] > out["RICH"]["value_score"]
    assert out["CHEAP"]["quality_score"] > out["RICH"]["quality_score"]


def test_missing_fundamentals_stay_none_not_zero():
    kpis = {"A": {"pe": 10, "opm": 20, "pat_yoy": 10, "rev_yoy": 5},
            "B": {"pe": 15, "opm": 18, "pat_yoy": 8, "rev_yoy": 4},
            "NODATA": {}}                                    # no pe, no quality inputs
    out = VQ.score_universe(kpis)
    assert out["NODATA"]["value_score"] is None
    assert out["NODATA"]["quality_score"] is None
