"""Value & quality factors for the LIVE screen (Phase-4.5 / research gap (b)).

Momentum and value are ~-0.49 correlated (Asness, Moskowitz & Pedersen 2013), and quality
overlaid on the pair reduces both the value trap and the momentum crash (Novy-Marx 2013;
Research Affiliates). Our composite is pure price/trend; adding value and quality is the
diversifying leg the research points to.

**Hard caveat — why this is live-only.** `nifty500_kpis.json` holds *current* (FY26) snapshot
fundamentals. Using them in the historical backtest would be point-in-time-fundamentals /
look-ahead bias, so these factors are **displayed and (optionally) ranked on the live screen
but NOT fed into the validated composite or any gate** until a point-in-time fundamentals feed
exists. They are context, measured today, not a backtested edge.

Pure functions: KPI dict(s) in, scores out. Cross-sectional z-scoring reuses the Phase-1
normaliser so value/quality sit on the same scale as everything else.
"""
from __future__ import annotations

from . import screener_factors as F


def earnings_yield(kpi: dict) -> float | None:
    """Value = earnings yield = 100 / P/E. Higher = cheaper. None for missing or non-positive
    P/E (a loss-maker's negative P/E is not 'expensive', it is undefined here)."""
    pe = kpi.get("pe")
    return (100.0 / pe) if (pe and pe > 0) else None


def quality_components(kpi: dict) -> dict:
    """Raw quality signals: operating margin (profitability), and profit & revenue growth
    (durability). Operating margin is None for banks (`is_banking`) — margin is not
    comparable there — so it drops out and quality leans on growth for those names."""
    opm = None if kpi.get("is_banking") else kpi.get("opm")
    return {"opm": opm, "pat_yoy": kpi.get("pat_yoy"), "rev_yoy": kpi.get("rev_yoy")}


def score_universe(kpis_by_tk: dict[str, dict]) -> dict[str, dict]:
    """{ticker: kpi} → {ticker: {"value_score", "quality_score"}} as cross-sectional z-scores
    (higher = cheaper / higher quality). A missing component stays missing and the quality
    blend averages only the ones present, so a bank with no margin is not pushed to the middle.
    """
    tks = list(kpis_by_tk)
    # winsorized: one stock's +1000% YoY off a low base must not dominate the cross-section.
    ey = F.winsorized_zscores([earnings_yield(kpis_by_tk[t]) for t in tks])

    qcomp = {t: quality_components(kpis_by_tk[t]) for t in tks}
    z_opm = F.winsorized_zscores([qcomp[t]["opm"] for t in tks])
    z_pat = F.winsorized_zscores([qcomp[t]["pat_yoy"] for t in tks])
    z_rev = F.winsorized_zscores([qcomp[t]["rev_yoy"] for t in tks])

    out: dict[str, dict] = {}
    for i, t in enumerate(tks):
        present = [z for z in (z_opm[i], z_pat[i], z_rev[i]) if z is not None]
        out[t] = {
            "value_score": round(ey[i], 2) if ey[i] is not None else None,
            "quality_score": round(sum(present) / len(present), 2) if present else None,
        }
    return out
