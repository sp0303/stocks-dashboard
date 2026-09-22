# 0008. Metric Methodology: Capital Deployed, Time-Weighted Returns, Index-Units Benchmarks

* **Status**: **R1 accepted** (chosen by the project owner, 2026-09-20). R2–R18 proposed, and already implemented and verified on v1's working tree against the real book.
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: Zerodha Console (performance curve = NAV units; portfolio XIRR suppressed when most holdings are under a year); GIPS (no annualising of partial years); Kaplan-Schoar PME (index-units benchmark); `docs/v2/DOMAIN-RULES.md`

---

## 1. Context and Problem Statement

The Sept 2026 audit found the dashboard's headline numbers wrong in ways users could not detect: "Invested" went negative on a profitable book, Sharpe was blank for every portfolio, a full exit read as a −90 % day, benchmark lines flatlined after any sale, and one broker feed served a three-month-old price as live. Indian retail users cross-check against Zerodha Console, so a method that is textbook-defensible but disagrees with Console still reads as a bug.

## 2. Decision

Adopt [DOMAIN-RULES](../v2/DOMAIN-RULES.md) R1–R18 as the binding specification for v2. The load-bearing choices:

| Choice | Decision | Alternatives rejected |
|---|---|---|
| Investment figure | **Capital deployed = peak cumulative net outflow** (same-day netting) beside **Current invested = open cost**; return on capital deployed | `buys − sells` (goes negative); gross bought (double-counts recycled capital); open cost as denominator (500 % for a ₹50 k gain on a ₹10 k position) |
| Risk metrics | **Time-weighted daily NAV**; capital base weighted by the execution price in the tradebook | value-based returns (flows read as performance); simple flow-at-start/end conventions (fail on near-empty re-entry or full exit) |
| Annualisation | **CAGR withheld under 365 days**; total return shown | extrapolating a partial year |
| Money-weighted | XIRR labelled money-weighted, suppressed under a year | one number named just "return" |
| Benchmarks | **Index-units (PME) on the portfolio's own `net_invested` baseline**, TRI where licensed, dead-ticker guard | subtracting open cost; silent flatlines |
| Pools | delivery, intraday, derivatives reported separately; **notional is never capital** | one blended "invested" |
| Ledger | lossless and append-only; charges `NULL` until known | dropping unknown columns; `0.0` for unknown charges |

## 3. Consequences

**Positive:** numbers users can defend against Console; every figure has one definition and one code path; the property tests (staged = lump sum, deposits are not gains, `pnl = mv − net_invested`, manager = Σ clients) prevent the whole class of drift defects.
**Negative / cost:** headline numbers change for users (see DOMAIN-RULES "Intentional differences") and must be communicated before cutover; some figures need data v1 never stored (charges, as-traded prices, raw files).
**Open policy values** (to confirm): risk-free rate 6.5 % (repo-rate proxy); XIRR suppression threshold 365 days; freshness limits per data class.
