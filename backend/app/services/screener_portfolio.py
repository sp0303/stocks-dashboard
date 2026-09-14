"""Phase 4 — portfolio-level risk for the swing book.

Phase 3 sizes one trade in isolation; a book blows up from the interactions Phase 3 cannot
see — ten "small" 0.75% risks that are really one bet because they are the same sector or
move together, or a position too large to exit in a day. This layer admits candidates
against portfolio caps, in priority order, and says exactly why each rejected name was
turned away. It reuses the ORB caps philosophy (a single risk engine, not a second one):
per-trade risk and notional come from `screener_plan`/`OrbConfig`; this adds the *aggregate*
limits.

Everything here is arithmetic on facts the caller supplies (each candidate's rupee risk to
its stop, its notional, its sector, optionally its recent return series). No advice, no
signal — it only enforces the user's own limits.

Honest gap: **event blackout** (skip names into results/ex-dates) needs a corporate-actions
/ earnings-calendar feed that is not wired yet — `blackout` is accepted as an explicit set
so the control exists the moment that data lands. See docs/screener/PHASES.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev


@dataclass
class PortfolioConfig:
    capital: float = 1_000_000.0
    max_total_open_risk_pct: float = 6.0     # sum of per-trade rupee risk, % of capital
    max_sector_risk_pct: float = 2.5         # risk concentration in any one sector
    max_positions: int = 8
    max_position_notional_pct: float = 15.0  # mirrors OrbConfig.max_notional_pct
    max_correlation: float = 0.80            # block a candidate this correlated with a held name


@dataclass
class Candidate:
    symbol: str
    sector: str
    risk_amount: float                       # rupees risked to the stop (SwingPlan.risk_amount)
    notional: float                          # position value, rupees
    returns: list[float] | None = None       # recent daily returns, for the correlation check


@dataclass
class Admission:
    admitted: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)     # {symbol, reason}
    open_risk_pct: float = 0.0
    sector_risk_pct: dict = field(default_factory=dict)
    positions: int = 0


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 20:
        return None
    a, b = a[-n:], b[-n:]
    sa, sb = pstdev(a), pstdev(b)
    if sa == 0 or sb == 0:
        return None
    ma, mb = mean(a), mean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n
    return cov / (sa * sb)


def assess(candidates: list[Candidate], cfg: PortfolioConfig | None = None, *,
           open_positions: list[Candidate] | None = None,
           blackout: set[str] | None = None) -> Admission:
    """Admit `candidates` (already in priority order) on top of any `open_positions`, subject
    to the portfolio caps. Greedy: a higher-priority name takes the scarce risk budget first.
    Returns which names were admitted, and for each rejection, the binding cap."""
    cfg = cfg or PortfolioConfig()
    blackout = blackout or set()
    open_positions = open_positions or []

    max_total_risk = cfg.capital * cfg.max_total_open_risk_pct / 100
    max_sector_risk = cfg.capital * cfg.max_sector_risk_pct / 100
    max_notional = cfg.capital * cfg.max_position_notional_pct / 100

    held: list[Candidate] = list(open_positions)
    total_risk = sum(p.risk_amount for p in held)
    sector_risk: dict[str, float] = {}
    for p in held:
        sector_risk[p.sector] = sector_risk.get(p.sector, 0.0) + p.risk_amount

    res = Admission()
    for c in candidates:
        if c.symbol in blackout:
            res.rejected.append({"symbol": c.symbol, "reason": "event blackout (results/ex-date)"})
            continue
        if len(held) >= cfg.max_positions:
            res.rejected.append({"symbol": c.symbol,
                                 "reason": f"max positions reached ({cfg.max_positions})"})
            continue
        if c.notional > max_notional + 1e-6:
            res.rejected.append({"symbol": c.symbol,
                                 "reason": f"notional over {cfg.max_position_notional_pct:g}% cap"})
            continue
        if total_risk + c.risk_amount > max_total_risk + 1e-6:
            res.rejected.append({"symbol": c.symbol,
                                 "reason": f"would breach total open risk "
                                           f"{cfg.max_total_open_risk_pct:g}%"})
            continue
        if sector_risk.get(c.sector, 0.0) + c.risk_amount > max_sector_risk + 1e-6:
            res.rejected.append({"symbol": c.symbol,
                                 "reason": f"sector risk cap {cfg.max_sector_risk_pct:g}% "
                                           f"({c.sector})"})
            continue
        if c.returns is not None and cfg.max_correlation < 1.0:
            clash = None
            for p in held:
                if p.returns is None:
                    continue
                r = _pearson(c.returns, p.returns)
                if r is not None and r > cfg.max_correlation:
                    clash = (p.symbol, r)
                    break
            if clash:
                res.rejected.append({"symbol": c.symbol,
                                     "reason": f"correlation {clash[1]:.2f} with {clash[0]} "
                                               f"> {cfg.max_correlation:g}"})
                continue

        held.append(c)
        total_risk += c.risk_amount
        sector_risk[c.sector] = sector_risk.get(c.sector, 0.0) + c.risk_amount
        res.admitted.append(c.symbol)

    res.positions = len(held)
    res.open_risk_pct = round(total_risk / cfg.capital * 100, 2)
    res.sector_risk_pct = {s: round(v / cfg.capital * 100, 2) for s, v in sector_risk.items()}
    return res
