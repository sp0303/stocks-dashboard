# Swing Screener — research review & gap analysis

Written 2026-09-15, after Phases 1–4 landed. Purpose: step back from the code and ask *what
are we missing* — measured against the published evidence and how practitioners actually run
cross-sectional swing systems. Every claim below is either something our own harness showed
or something from a cited source; nothing here is folklore.

## 1. Where we actually stand
| Phase | State | One-line |
|---|---|---|
| 1 · ranking | ✅ passed | composite IC +0.020 @+10d, net edge +0.57pp, t 4.1 |
| 2 · setups | ⚠️ fragile → 1 robust | only **composite-gated Pullback** clears the both-halves bar |
| 3 · trade plan | ✅ landed | factual ATR stop / R:R / sizing, wired into the screen |
| 4 · portfolio | ✅ landed | aggregate risk/sector/correlation caps; blackout hook |

The honest headline: **we have a validated *ranking* and a solid *workbench*, but only one
setup that survives execution + a strict robustness bar.** The second-half decay (2024→26)
is the central problem, and the literature names it exactly.

## 2. What the decay is — and why it isn't a surprise
- **Momentum crashes are a known, violent feature, not a bug.** India's own Nifty 200
  Momentum 30 delivered ~14% CAGR vs ~10% for the Nifty but through a **−70% drawdown with a
  65-month recovery** ([BacktestIndia](https://backtestindia.com/blog/momentum-investing-india-backtest)).
  Our −0.05R second half is a mild version of the same thing: momentum pays for years, then
  hands a chunk back fast. A single full-sample number always flatters it.
- **The academic fix is risk-managing momentum, which we don't do.** Barroso & Santa-Clara,
  *Momentum Has Its Moments* (2015) and Daniel & Moskowitz, *Momentum Crashes* (2016) show
  that **scaling exposure by recent realized volatility** roughly doubles momentum's Sharpe
  and removes the worst crashes. Our regime gate (breadth < 40% → cash) is a crude, binary
  cousin; a continuous vol-scaling overlay is the missing piece and directly targets our
  fragility.
- **Factors decay after publication** ([Ehsani & Linnainmaa, NBER w25551](https://www.nber.org/system/files/working_papers/w25551/w25551.pdf)).
  Expect attenuation, and *monitor* for it — which is exactly what Phase 5 is for and why it
  should not be skipped.

## 3. The three factors we're missing (highest-value gaps)

### (a) Frog-in-the-Pan — momentum *quality* — **cheap, price-only, do first**
Da, Gurun & Warachka (2014) and the Alpha Architect / Wesley Gray *Quantitative Momentum*
program show momentum's edge is almost entirely in **smooth, continuous** movers: stocks that
rose via many small up-days ("high quality") keep going (+5.94%), while stocks that jumped in
a few discrete lurches **reverse** (−2.07%)
([Alpha Architect](https://alphaarchitect.com/what-explains-the-momentum-factor-frog-in-the-pan-is-still-the-king/)).
- Our `trend_persistence` (% of days above DMA50) is a *crude proxy*. True FIP = the
  information-discreteness measure (sign and consistency of daily returns over the formation
  window).
- **Why it matters here:** fragile 2nd-half breakouts are very likely the *discrete* movers.
  A real FIP factor should separate the durable breakouts from the ones that reverse — the
  single most promising lever for the fragility problem, and it needs **only price data we
  already have** (no look-ahead, no new feed).

### (b) Value — **negatively correlated with momentum, the classic drawdown smoother**
Asness, Moskowitz & Pedersen, *Value and Momentum Everywhere* (2013): value and momentum are
**~−0.49 correlated**, so combining them cuts portfolio volatility and tames momentum
crashes ([NYU/Pederson PDF](https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf)).
- We compute **zero** value factors, yet `nifty500_kpis.json` already carries `pe`, `mcap_cr`,
  `rev_yoy`, `pat_yoy`.
- **Caveat that gates this:** those KPIs are *current FY26* snapshots. Using them in the
  backtest would be look-ahead / point-in-time-fundamentals bias — so value can go into the
  **live screen now**, but **cannot be validated historically** until we have PIT
  fundamentals. Treat as live-only until then.

### (c) Quality / profitability — **the third leg of the robust triad**
Novy-Marx (2013, gross profitability) and Research Affiliates, *Why Value, Quality and
Momentum Belong Together*
([RAFI PDF](https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1110-why-value-quality-and-momentum-belong-together.pdf)):
quality overlaid on value+momentum improves risk-adjusted return and, crucially, **reduces
the value trap and the momentum crash**. We have `opm`, `pat_yoy`, `ebitda_cr` to build a
quality score — same PIT caveat as value.

## 4. Structural / method gaps
- **Survivorship** (tracked): today's Nifty-500 membership only; no PIT membership, no
  delisted names. All backtest numbers are optimistic. Blocked on data (see PHASES.md).
- **Point-in-time fundamentals**: prerequisite before value/quality can be *validated*, not
  just displayed.
- **No time-series (absolute) momentum / trend filter on the name itself.** We gate on market
  breadth but not on each stock's own trend health beyond DMAs. Clenow, *Stocks on the Move*,
  pairs cross-sectional ranking with a per-stock trend filter and an index regime filter —
  close to our design but with the vol-scaling we lack.
- **Event/earnings blackout**: Phase 4 has the hook, no data feed.
- **Cost realism at size**: the statutory model is good; market-impact/slippage for larger
  positions isn't modelled (fine at retail size, matters if capital scales).

## 5. Researchers & strategies worth tracking (the shortlist)
| Who | Contribution | Use to us |
|---|---|---|
| Jegadeesh & Titman (1993) | momentum, skip-a-month | already the backbone |
| George & Hwang (2004) | 52-week-high anchor | already in composite |
| Da, Gurun & Warachka (2014) | Frog-in-the-Pan | **add as momentum-quality factor** |
| Asness / Moskowitz / Pedersen (2013) | value+momentum everywhere | **add value leg** |
| Daniel & Moskowitz (2016); Barroso & Santa-Clara (2015) | momentum crashes / vol-scaling | **add crash protection** |
| Novy-Marx (2013); Research Affiliates | quality / profitability | **add quality leg** |
| Wesley Gray & Jack Vogel — *Quantitative Momentum* | practitioner FIP ruleset | implementation recipe |
| Andreas Clenow — *Stocks on the Move* | CS momentum + regime + vol-parity sizing | closest full-system template |
| Minervini (VCP), Connors (RSI-2) | practitioner setups | already reflected in Phase 2 |

## 6. Recommended order of work (highest ROI first)
1. **Frog-in-the-Pan momentum-quality factor** — price-only, no data blockers, aimed straight
   at the fragility. Add to the composite behind the usual IC gate; re-run Phase 1 + the
   composite-gated Phase 2.
2. **Momentum crash protection** — replace/augment the binary breadth gate with continuous
   volatility-scaling of exposure (Barroso–Santa-Clara). Re-validate.
3. **Ship composite-gated Pullback** as the one honest tradable book today; breakout/oversold
   stay as context labels.
4. **Value + Quality on the live screen** (display + optional live ranking), clearly marked
   "not historically validated" until PIT fundamentals exist.
5. **Phase 5 monitoring loop** — snapshot every scan, record realised outcomes, watch IC/
   expectancy decay in real time. Non-optional given point 2.4 on factor decay.
6. **Data acquisition** (unblocks the rest): PIT index membership, PIT fundamentals, an
   earnings/corporate-actions calendar.

> Bottom line: the ranking works, the workbench is real, and the honest product *today* is a
> research-grade swing workbench with one validated setup — not a fire-and-forget signal.
> The clearest single experiment left is the Frog-in-the-Pan factor; the clearest single
> upgrade is vol-scaled crash protection. Both are price-only and unblocked.
