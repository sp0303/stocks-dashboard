# Swing Screener — build tracker

Evidence-led rebuild of the Nifty-500 swing screener. The shipped ranking score was
backtested (233 rebalance dates, 2023–2026) and has **no edge**: Rank IC negative at
every horizon, and at +3d the lowest-scoring decile beats the highest. The detail of
*how* it fails sets the plan — see the artifact
(`claude.ai/code/artifact/90b200f6-4054-4166-af66-fdfafea9efb5`).

## The diagnosis, in one line
Every factor we score is short-horizon momentum (`w1` 0.45, `rel` 0.30 — both 1-week),
and 1-week returns **mean-revert** (Jegadeesh 1990, Lehmann 1990). The only two factors
with positive IC — `from_52w`, `atr_pct` — are the two we don't score. So the ranking is
**replaced, not tuned.**

## The research the rebuild stands on
| Pillar | Factor | Source |
|---|---|---|
| Nearness to 52-week high | `from_52w` | George & Hwang (2004), *J. Finance* |
| Proper-horizon momentum, skip recent | 3M/6M return, skip ~1mo | Jegadeesh & Titman (1993) |
| Residual momentum (stretch) | momentum on residual/idio returns | Blitz, Huij & Martens (2011) |
| Volatility to travel + contraction | `atr_pct`, ATR-now ÷ ATR-60d | Minervini VCP |

## Rules the build runs on
1. **No factor ships without a positive, out-of-sample IC** measured on the harness.
2. **Each layer is gated by the one below.** If discovery has no edge, setups and trade
   planning are decoration.
3. **3–5 genuinely different drivers, not fifteen indicators.**

---

## Phase 0 — Foundation ✅ (on `main`)
- Test suite green; E4/B6 floor regressions fixed; alignment test pinned.
- `scripts/screener_backtest.py` — point-in-time replay, decile + IC + per-factor IC,
  significance. Live and backtest share `score_for()` so they cannot drift.
- **This harness is the asset.** Everything below is judged by it.

## Phase 1 — Replace the ranking (IN PROGRESS · branch `claude/screener-phase1`)

> **Landed so far:** `app/services/screener_factors.py` (factors + normalisation +
> composite, 13 unit tests) and `scripts/screener_phase1_backtest.py` (composite IC net
> of costs, ADV floor, macro-regime split, membership hook, 4 wiring tests). Not yet run
> against the live Mongo store — that is the next step and produces the GATE verdict.
Build a small factor library where each candidate is measured before it is combined.

**Remove from the composite:** `w1`, `rel`, the RSI point-bonus (kept as *displayed
context* only).

**Add, each behind a positive-IC gate:**
- [x] `from_52w` — distance below the 52-week high
- [x] `atr_pct` — ATR(14) ÷ price
- [x] `mom_3m` / `mom_6m` — cumulative return, **skipping the most recent ~5 sessions**
- [x] `trend_persistence` — % of last 50 sessions closed above DMA50
- [x] `atr_contraction` — ATR(14) now ÷ ATR(14) ~60 sessions ago (VCP proxy)
- [x] `adv` — median daily traded value (liquidity; a gate, not a return signal)

**Mechanics:**
- [x] **Normalise** every factor to a cross-sectional z-score / percentile (z / winsor /
      percentile methods, missing stays missing, never 0).
- [x] Composite = weighted sum of *normalised* factors; weight renormalised over present
      factors; weights provisional until the IC gate confirms them.
- [x] **Point-in-time membership** hook (`--membership`) — needs a constituents file to use.

**The four execution-realism additions (folded in here):**
- [x] **Transaction-cost + turnover model** — round-trip cost charged on per-rebalance
      top-decile turnover (`--cost`).
- [x] **Macro regime filter** — self-contained breadth gate (% of universe above its
      200-DMA); risk-off dates put the long book in cash (`--regime-breadth`).
- [x] **Liquidity hard floor (ADV gate)** — drop names below a minimum median daily
      traded value *before* scoring (`--min-adv`).
- [ ] **Survivorship** — point-in-time membership handles index churn; true precision
      needs delisted/bankrupt names in the window (data-acquisition task, tracked).

> **GATE:** composite IC positive and stable across sub-periods, **net of costs**, and the
> top decile beats the equal-weight universe out of sample. If not — stop, do not build
> Phase 2. This phase is the whole ballgame.

## Phase 2 — Setup classification (max three modes)
Replace one blended rank with labelled, independently-validated setups, each carrying its
own historical expectancy shown in the UI.
- [ ] **Trend continuation / breakout** — near 52w high, adequate ATR, above DMA20/50,
      contraction resolving (VCP).
- [ ] **Pullback in an uptrend** — above DMA200, retrace to DMA20/50, contraction on the
      pullback (short-term oversold *within* an uptrend, e.g. RSI(2)).
- [ ] **Short-horizon mean reversion** — the measured +3d effect (most beaten-down decile
      outperformed); different hold, different exit, its own test.
- [ ] Labels: `Near breakout` · `Pullback setup` · `Oversold reversal` ·
      `Extended — avoid chasing` · `No setup`.

> **GATE:** each setup validated separately — sample size, expectancy in R, sub-period
> and sector breakdown. A setup that doesn't clear its own bar never ships.

## Phase 3 — Trade-planning calculator
Objective arithmetic on chart facts — not a recommendation.
- [ ] ATR-based invalidation → stop; R:R to the next resistance.
- [ ] Target 1/2 as multiples of the user's own R.
- [ ] Expected holding period from the setup's measured distribution.
- [ ] Position size from user risk-per-trade and the ATR stop.
- [ ] **Reuse the ORB risk layer** — `plan_trade()`, ATR stop logic, full cost model.

> **GATE:** factual levels + user-parameterised maths only. No buy/sell calls, no house
> price targets.

## Phase 4 — Portfolio-level risk
- [ ] Max risk per trade and max total open risk.
- [ ] Sector concentration and correlation limits.
- [ ] Liquidity capacity (position vs median traded value); gap-risk awareness.
- [ ] Event blackout — wire corporate-actions/results data in as an entry gate.

> **GATE:** reuse ORB's sizing/caps rather than writing a second risk engine.

## Phase 5 — Forward-performance loop (permanent)
- [ ] Snapshot every scan: date, symbol, setup label, score, factor values.
- [ ] Record outcome: MFE/MAE, return at +3/+5/+10/+20, stop-vs-target-first, net of costs.
- [ ] Report rolling realised IC and setup expectancy — a decaying factor shows up here
      before it costs money.

---

## Honest downside
If a normalised, IC-screened composite still can't beat equal-weight out of sample *net
of costs*, the conclusion is that this universe/horizon doesn't support a simple
cross-sectional ranking — and the product becomes an excellent research and
trade-planning workbench (Phases 3–5 stand alone) rather than a signal generator. That
is a legitimate outcome, and far better than shipping a confident-looking negative-IC rank.

## Standing caveats
- Survivorship unfixed until point-in-time membership + delisted names land.
- The +20d top-decile "significant" result (t≈3.96) has ~4× window overlap → read t≈2.
- None of this is investment advice; it is the measured behaviour of a ranking function.
