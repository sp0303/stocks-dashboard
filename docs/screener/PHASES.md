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

## Phase 1 — Replace the ranking ✅ GATE PASSED (branch `claude/screener-phase1`)

> **Landed:** `app/services/screener_factors.py` (factors + normalisation + composite,
> 13 unit tests) and `scripts/screener_phase1_backtest.py` (composite IC net of costs,
> ADV floor, macro-regime split, membership hook, 4 wiring tests).
>
> **GATE RESULT (live Mongo, 233 rebalance dates, `--every 5 --cost 0.30 --min-adv 5e6
> --regime-breadth 40`):** @+10d composite IC **+0.0199**, top-decile net edge
> **+0.565pp**, t **+4.13** → **PASS**. Edge builds with horizon (+3d noise → +20d
> +1.13pp, t+5.6); D10 is the clear top decile at every horizon. `mom_6m`, `from_52w`,
> `atr_pct` carry the signal; `atr_contraction` is ~0 IC (drop candidate).
> **Caveat:** survivorship-optimistic — see below.
>
> **Phase 1.1 (2026-09-15) — Frog-in-the-Pan momentum quality added.** New `fip` factor =
> information discreteness `sign(PRET)·(%neg−%pos)` over the 6m/skip-5 window (Da, Gurun &
> Warachka 2014). Standalone IC positive at every horizon (+0.008/+0.004/+0.007/+0.009);
> added to the composite at weight 0.13 (trimming near-zero `atr_contraction` to 0.05). The
> composite **improved across the board**: @+10d IC +0.0199→**+0.0217**, net edge
> +0.57→**+0.68pp**, t +4.13→**+4.91**; @+20d t +5.6→+6.3. Note: raw `fip` tested +IC here —
> the *opposite* of the pure long-only FIP intuition, because ID is direction-symmetric and
> the decliner side flips the cross-sectional sign; kept because the harness, not the
> intuition, is the arbiter. Downstream: composite-gated Pullback rose to +0.11R (still
> robust); breakout stayed fragile (its decay is the momentum-crash gap, not quality).
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
      **Status (2026-09-15):** attempted to source a PIT membership file — NSE serves only
      the *current* list, and the Wayback Machine has ~1 archived snapshot of it in the
      whole 2021–2026 window, so no trustworthy history is reachable from the build
      environment. Not fabricated (a synthetic file would produce a falsely clean gate).
      Two blockers remain: (a) no historical reconstitution feed reachable here; (b) even a
      perfect file only removes *forward-inclusion* bias — dropped/delisted names need their
      own candles, which are not in the store. Both gate results above therefore stand as
      **optimistic**; a paid PIT feed or parsed NSE semi-annual circulars would close it.

> **GATE:** composite IC positive and stable across sub-periods, **net of costs**, and the
> top decile beats the equal-weight universe out of sample. If not — stop, do not build
> Phase 2. This phase is the whole ballgame.

## Phase 2 — Setup classification ⚠️ FRAGILE (branch `claude/screener-phase1`)
Replace one blended rank with labelled, independently-validated setups, each carrying its
own historical expectancy.

> **Landed:** `app/services/screener_setups.py` (pure classifier + geometry, 9 unit tests)
> and `scripts/screener_phase2_backtest.py` (first-touch R expectancy path-simulated on
> daily highs/lows, per-setup, with sub-period + sector breakdown and a per-setup gate).

- [x] **Trend continuation / breakout** (`Near breakout`) — near 52w high, ADV/ATR floor,
      above DMA20/50, **%-based** volatility contraction (absolute ATR-contraction is
      trend-biased, so the classifier uses ATR%-now ÷ ATR%-ago).
- [x] **Pullback in an uptrend** (`Pullback setup`) — above DMA200, price back in the
      DMA20/50 zone, RSI(2) oversold *within* the uptrend.
- [x] **Short-horizon mean reversion** (`Oversold reversal`) — deep RSI(2) capitulation,
      trend-agnostic; fast target, short hold.
- [x] Context labels: `Extended — avoid chasing`, `No setup`.

**Firm-up (2026-09-15).** After the first pass showed second-half decay, the bar was
raised and the setups tightened — principled changes, not curve-fitting:
- classifier now requires genuine up-structure (**DMA50 > DMA200**, not just price above a
  lagging DMA200) for breakout and pullback;
- the harness gained Phase 1's **breadth regime gate** (`--regime-breadth 40`, skips long
  setups on risk-off dates — 58 of 233 skipped);
- the gate now demands **both sub-periods positive**, not just the full-sample mean.

> **FIRMED-UP GATE RESULT (live Mongo, 233 dates, `--cost 0.30 --min-adv 5e6 --min-n 60
> --regime-breadth 40`):**
> | setup | n | win% | expR | 1st-half | 2nd-half | verdict |
> |---|---|---|---|---|---|---|
> | Near breakout | 12,610 | 42% | +0.09 | +0.26 | −0.06 | **FRAGILE** |
> | Pullback setup | 4,724 | 48% | +0.05 | +0.17 | −0.05 | **FRAGILE** |
> | Oversold reversal | 13,542 | 49% | −0.02 | +0.04 | −0.07 | **NO EDGE** |
> | Extended (chase) | 451 | 43% | +0.07 | — | — | confirmed inferior |
>
> **Verdict: PHASE 2 NOT YET.** The regime gate did *not* rescue the second half — the
> edge weakened in 2024-04 → 2026 on risk-on dates too, so the decay is real time-variation,
> not just market beta. First-half edge is genuine (breakout +0.26R) but does not persist.
> No setup clears the both-halves bar. Not overfitted to force a pass — recorded as-is.
>
> **Consequence (per "Honest downside" below):** the setups are *not* reliable
> signal-generators, so the product leans on the **trade-planning workbench** (Phase 3),
> which stands alone as objective arithmetic on chart facts. The labels ship as *context*
> ("this looks like a breakout / pullback / extended"), never as a buy call, and the UI must
> show the fragile, sub-period expectancy honestly rather than a single flattering number.
**Composite-gate lever (2026-09-15, `--composite-top 30`).** Tried the tracked lever — only
take setups on names already in the top 30% of the Phase-1 composite. It *helps*:
> | setup | n | expR | 1st-half | 2nd-half | verdict |
> |---|---|---|---|---|---|
> | Near breakout | 8,849 | +0.09 | +0.27 | −0.05 | still FRAGILE |
> | **Pullback** | 1,562 | +0.09 | **+0.20** | **+0.03** | **PASS (robust both halves)** |
> | Oversold reversal | 1,963 | +0.02 | +0.07 | −0.01 | ~flat |
>
> So the validated ranking rescues one setup: **composite-gated Pullback clears the strict
> bar**. Breakout stays fragile even gated (its second half is the real momentum-crash
> casualty). Net: ship **Pullback on top-composite names** as the one honest tradable book;
> keep breakout/oversold as context labels. (Caveat: composite-gating shrinks n and the
> `Extended` label goes non-inferior at small n — watch it.) This is the current
> recommendation pending the factor additions in `RESEARCH_GAPS.md`.

- [x] **Wired into the screener** — `screener_daily.compute()` attaches `setup` + a
      capital-independent `plan` to every stock; `GET /api/screener/plan/{ticker}?capital=&risk_pct=`
      returns the full user-sized plan.

## Phase 3 — Trade-planning calculator ✅ LANDED (branch `claude/screener-phase1`)
Objective arithmetic on chart facts — not a recommendation. `app/services/screener_plan.py`
(`plan_swing_trade`), 11 unit tests, sanity-checked live against Mongo.
- [x] ATR-based invalidation → stop; R:R to the next *prior* overhead level (≥0.5 ATR
      above entry; None when at new highs, stated as such).
- [x] Target 1/2 as multiples of the user's own R (T1 = 1R rung; T2 = the setup's measured
      target in R).
- [x] Expected holding period from the setup's measured distribution (`SETUP_STATS`).
- [x] Position size from user risk-per-trade and the ATR stop, with notional and liquidity
      caps; every binding cap is reported as a note.
- [x] **Reuses the ORB risk layer** — the same sizing math as `plan_trade()` and the exact
      `OrbConfig` statutory cost model (mirrored to avoid an app→scripts import).

> **GATE:** factual levels + user-parameterised maths only. No buy/sell calls, no house
> price targets. ✅ Met — the plan returns levels, R-multiples, size and cost; the setup
> label rides along as *context* and is stamped FRAGILE, never as a signal. Given Phase 2's
> result, this workbench is the product's honest core.

## Phase 4 — Portfolio-level risk ✅ LANDED (branch `claude/screener-phase1`)
`app/services/screener_portfolio.py` (`assess`), 7 unit tests. Greedy admission in priority
order, each rejection stamped with the binding cap.
- [x] Max risk per trade (Phase 3) and max total open risk (aggregate cap).
- [x] Sector concentration cap; correlation limit (pairwise Pearson on supplied returns).
- [x] Liquidity capacity via per-position notional cap (reuses the Phase 3 / OrbConfig cap).
- [ ] Event blackout — **hook present** (`blackout` set rejects those names), but the
      corporate-actions / earnings-calendar feed that would populate it is **not wired**
      (data-acquisition task, same class as survivorship). Gap-risk awareness (overnight gap
      distribution) also still TODO.

> **GATE:** reuse ORB's sizing/caps rather than writing a second risk engine. ✅ Met —
> per-trade risk/notional come from `screener_plan`/`OrbConfig`; Phase 4 only adds the
> aggregate limits on top.

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
