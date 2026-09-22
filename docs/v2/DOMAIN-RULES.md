# Portfolio Intelligence v2 — Domain Rules (R1–R18)

**Status:** draft for approval · 21 Sep 2026
**Role:** the equivalent of quest-mf's "spec v2 + rules Q1–Q16". These rules are **binding**: a violation is a blocking review finding. Each rule exists because the metrics audit found a real defect; the evidence is cited.
**Enforced by:** `pi_core` unit, property and golden tests (LLD-backend §8). See also [AGENTS.md](../../AGENTS.md).

> Conventions: ratios are **decimals** everywhere except the UI formatter. `V` = market value of open positions, `F` = net cash flow into the portfolio (buys − sells) on a day, `NAV` is indexed to 100.

---

## R1 — Two investment figures; return is measured on capital deployed

| Figure | Definition | Where shown |
|---|---|---|
| **Capital deployed** (the real investment) | `max over days of cumulative(buys − sells)`, with each day's flows **netted before accumulating** (a same-day sell funds a same-day buy) | headline "Invested", manager and client |
| **Current invested** | cost basis of the positions still held | holdings view, beside capital deployed |
| **Return on capital** | `total P&L ÷ capital deployed` | the return % on every card |

**Never** use `buys − sells` (ending net cash: it shrinks as money is taken out and went to −₹5.7 L on a profitable recycling book), **gross bought** (recycled capital is counted again: ₹1 L recycled five times reads as ₹6.7 L, understating a 101 % return as 15 %), or open-holdings cost as the denominator (a ₹50 k gain over a ₹10 k open position read as 500 %).
Reinvested profit is **not** new investment (user requirement). *Real example:* one client shows capital deployed ₹2,10,960 vs current invested ₹2,38,129; the gap is reinvested gains.
Book level: **sum of each client's own peak**, never a peak over merged trades.

## R2 — Risk metrics come from a time-weighted daily NAV, not from portfolio value

Deposits, withdrawals, purchases and sales are **flows**, not performance.

```text
r_t  = (V_t − V_{t−1} − F_t) / B_t                       B_t = capital base actually at work on day t
B_t  = V_{t−1} + Σ_buys q·p·(1 − m) − Σ_sells q·c_{t−1}·(1 − m)
m    = share of the day's price move already done when the trade executed
     = clamp((p − c_{t−1}) / (c_t − c_{t−1}), 0, 1);  0.5 if |c_t/c_{t−1} − 1| < 0.5 %
NAV_t = NAV_{t−1} · (1 + r_t)
```

Weighting each tranche by the **execution price the tradebook records** means a tranche bought at the close adds nothing to the base and one bought at the open adds all of it. Consequence (property tests): *staged deployment and a lump sum on the same price path give the same NAV*; *a full exit is not a loss*; *a deposit is never a gain*.
This is the same NAV-unit idea Zerodha Console uses for its performance curve.
*Evidence:* v1's series treated a full sale as ≈ −90 % and fed volatility, drawdown and beta. The **first draft of this fix** divided by the pre-flow value and, on one real book, a top-up of a near-empty portfolio (₹434 then ₹3,514) produced −403 % and left NAV negative for 746 days (max drawdown −1084 %) while its unit tests passed. The base definition above and R16 exist because of that.

## R3 — Annualise only what has a year behind it

| Metric | Definition | Rule |
|---|---|---|
| Total return | `NAV_end / NAV_start − 1` | always available |
| CAGR | `(NAV_end/NAV_start)^(365.25/days) − 1` | **`None` if `days < 365`** (GIPS forbids annualising a partial year; Console suppresses XIRR for the same reason). The UI shows total return instead. |
| Volatility | `stdev(r) · √252` | needs ≥ 2 daily observations |
| Sharpe | `mean(r − rf/252) / stdev(r) · √252` | one `RISK_FREE_RATE` constant (6.5 %, versioned setting); not `(CAGR − rf)/vol` |
| Max drawdown | worst `(NAV − runningPeak)/runningPeak` | ≤ 0 and **≥ −100 %** |
| Beta | `cov(r_p, r_b)/var(r_b)` | **matched by date**, never by list position |
| Alpha | Jensen: `R_p − [rf + β(R_b − rf)]` | annualised vs annualised, or total vs total when CAGR is withheld |

## R4 — XIRR is money-weighted and policy-suppressed

Cash flows = matched trades (∓ charges when known) + dividends; terminal flow = market value of **priced** holdings on `as_of`. Return `None` if the span is under 365 days or the solver does not converge (never a made-up number). Always labelled "money-weighted": it weights by how much capital was invested when, so a client can show CAGR −12 % (time-weighted) beside XIRR +22 % and profit +₹7.75 L. Both are correct; the UI explains the difference.

## R5 — One definition, one code path

A figure that appears in more than one place is computed by **one function**, and the other places read its output.

- Manager totals are **sums of client figures** produced by the same engine run. A test asserts `manager row == client page` for every client.
- One CAGR, one return %, one Sharpe. (v1 had two CAGRs giving +10.6 % and −12.1 % for one account, and two `calculate_sharpe_ratio` functions where the later one shadowed the first and returned `None` forever.)
- Sector weight in *Portfolio Health* and in *Concentration* use the same basis (market value).

## R6 — Price integrity

1. Prices are keyed **`(symbol, exchange)`**. A BSE holding is never valued at the NSE price (v1's quote cache was keyed by symbol alone, so whichever exchange loaded first priced every holding of that symbol; illiquid listings can differ materially).
2. Every quote and close carries `as_of` and `source`.
3. A quote whose last exchange trade is older than the freshness limit is **rejected at ingest**, not served (VENUSREM's NSE record stopped 12 Jun 2026 and kept returning ₹1,797.50: +13.6 %, ₹48,658 across the book).
4. A position with no usable price is excluded from **both cost and market value** and listed in a warning. Excluding only one side turns a missing price into a fake loss.

## R7 — Cash-flow series describe only matched shares

A sell with no matching buy (IPO allotment, demerger credit, bonus, transfer-in) has an unknown cost basis. It is excluded from realised P&L **and** from every cash-flow series (net capital, benchmark units), and reported (`unmatched_sell_symbols`, value). Otherwise its proceeds read as pure profit (RAYMONDREL moved a chart ~60 % in a day). A user-supplied `cost_basis_adjustment` makes the shares matched.
Identity that must hold: **chart P&L = realised + unrealised** for every client.

## R8 — Corporate actions are applied wherever quantity is computed

`SPLIT` and `BONUS` scale open lots (`qty × m`, `unit_cost ÷ m`) at the ex-date, **before** same-day trades. This happens inside the one engine, so holdings, allocation, XIRR, risk, series and manager views all agree (v1 applied it in only one of seven code paths). `DEMERGER`, `MERGER`, `RIGHTS`, `BUYBACK` are stored and produce a visible **"cost apportionment needed"** warning; they are never silently ignored.

## R9 — Delivery, intraday and derivatives are separate pools

| Pool | Definition | Reported as |
|---|---|---|
| Delivery equity | `segment ∈ {EQ}` (or blank) after removing same-day round trips | the investment portfolio |
| Intraday | same stock, same day, buy and sell (Section 43(5): speculative income) | trade count, win rate, net P&L. **No "invested" figure**: capital returns the same day and is margin-funded. |
| Derivatives (F&O, NRML) | any other segment | P&L only, until margin data exists. **Notional is never capital**: one futures lot's notional (₹11.5 L) dwarfed a ₹15 k equity book. |

Manager and client pages use the **same** split. (v1's manager routes read raw trades, so one client showed different numbers depending on the page.)

## R10 — Benchmarks: index units, on the same baseline as the portfolio

```text
buy  amt at index level P :  units += amt / P
sell amt at index level P :  units −= amt / P
value_t = units_t · P_t          benchmark_pnl_t = value_t − net_invested_t
portfolio_pnl_t = market_value_t − net_invested_t          (same net_invested, so the two lines are comparable)
```

- v1 subtracted *open cost* from the benchmark, so after any full exit the index showed ₹0 gain against the portfolio's +₹10 k on a trade where the index also rose 10 %.
- Prefer TRI where licensed (quest-mf ADR-0009); otherwise a price index or an index-fund proxy, **labelled honestly** ("Nifty Midcap 150", not "Midcap 100").
- **Dead-ticker guard:** a benchmark whose last value is more than 2 sessions behind the calendar raises a `BLOCK` data-quality issue and a visible banner. It must never flatline silently (`^CRSMID` stopped on 17 Jul 2026; the chart sat flat for two months).

## R11 — The series is daily on the trading calendar

One point per market day from the first trade to today, plus any trade date not in the calendar. Never one point per trade date: a real client had **15 points across 191 days (7.9 %)** with straight lines drawn across gaps of up to 48 days, and √252 annualisation assumes consecutive daily observations. Missing prices are held at the last close (or at cost when there is no history), never dropped.

## R12 — Units, zero, and thresholds

- Storage and API: ratios are **decimals**. The single UI formatter multiplies by 100.
- `0` is a value. Never test `if (value)`; test `value != null` (v1 showed "—" for a genuine beta or alpha of 0).
- Thresholds are written in the metric's own unit. Health-score rules compared a **decimal** volatility (0.14) to `25`, so no alert could ever fire.

| Health score (start 100) | Penalty |
|---|---|
| top-10 concentration > 70 % / > 60 % | −20 / −10 |
| largest sector > 40 % / > 30 % | −15 / −5 |
| volatility > 0.25 / > 0.20 | −10 / −5 |
| max drawdown < −0.30 / < −0.20 | −15 / −10 |
| current drawdown < −0.15 / < −0.10 | −10 / −5 |

## R13 — The ledger is lossless and append-only

1. The **original uploaded file is stored unchanged** (v1 kept only its hash).
2. **Every** column the broker sent is kept: typed columns for the known ones, `extra JSONB` for the rest (Upstox `Amount`, `Scrip Code`, `Instrument Type`, `Strike`, `Expiry` were dropped by v1, and the original company name was replaced by a guessed ticker).
3. Every rejected row is stored with its reason; `imported + duplicate + rejected = total`.
4. The dedupe fingerprint includes the **broker trade id**, so two fills at the same price and time stay separate.
5. Deletes are tombstones. Nothing in the ledger is edited by a worker.

## R14 — Exports are authenticated and round-trip

Downloads use authenticated `fetch` and a blob, never a bare `<a href>` (v1's Playbook export returned HTTP 401). The tradebook export uses the broker's own layout, writes **ids as text** (a 19-digit order id loses digits as an Excel number), writes `auction` as lowercase `true`/`false`, and re-uploads without creating duplicates. A test proves exact fingerprint round-trip on real data.

## R15 — Charges: unknown is not zero

`charges` is `NULL` with `charges_known = false` until a source provides it (Console's P&L report or contract notes). Known charges are folded into cost and proceeds. The UI marks P&L "before charges" while a material share of trades has unknown charges. (v1 hard-codes `0.0`, which overstates realised P&L by brokerage, STT and stamp duty.)

## R16 — Sanity guards (fail visible, never compound an error)

- `NAV > 0` always. A daily return ≤ −100 % is a **data error**: hold the NAV flat and raise a DQ issue.
- If the capital base `B_t < ₹1`, the day's return is 0 (there is nothing to earn a return on).
- Market value is never negative. A day with no price uses the last close.

## R17 — As-traded prices

`market.eod_prices` stores **as-traded (unadjusted) closes**, because R8 scales quantities at the ex-date; adjusted prices plus scaled quantities double-count a split. If a provider returns adjusted history, convert it using `corporate_actions` or set `adjusted = true` and exclude it from valuation. Test: a 1:5 split day must not create a return. **Phase 2 must verify what v1's stored Yahoo history actually is.**

## R18 — Reconcile against the broker

Per client and symbol, compare engine quantity with the broker's holdings (Kite `holdings()`, or a Console holdings export). Drift raises a warning and is the same signal as an unmatched sell. This is the check that catches missing history, transfers and unapplied corporate actions.

---

## Metric glossary

| Metric | Formula / source | Unit | Stored in |
|---|---|---|---|
| Capital deployed | R1 | ₹ | `client_overview.payload.capital_deployed` |
| Current invested | Σ open lot cost | ₹ | `client_daily.open_cost` |
| Realised P&L | FIFO, matched qty only | ₹ | `client_daily.realized_pnl` |
| Unrealised P&L | Σ qty × (price − avg cost) over **priced** positions | ₹ | API: `positions_latest` × live price |
| Return on capital | total P&L ÷ capital deployed | decimal | computed with the above |
| NAV / TWR | R2 | index | `client_daily.nav` |
| CAGR / total return | R3 | decimal | `client_metrics` |
| Volatility, Sharpe, drawdown, beta, alpha | R3 | decimal / ratio | `client_metrics` |
| XIRR | R4 | decimal | `client_metrics` |
| Benchmark P&L | R10 | ₹ | `client_benchmark_daily.pnl` |
| Win rate | wins ÷ **trades** (not FIFO lots); ₹0 P&L is neither a win nor a loss | decimal | `trade_analytics` |

## Golden fixtures (built from real data in Phase 0)

1. Largest book (4,219 trades, 5 years, many round trips): every headline number.
2. The near-empty-portfolio re-entry (₹434 topped up with ₹3,514): the case that broke the first TWR draft with −403 % / −1084 %.
3. A client with unmatched sells (demerger credit, IPO allotment).
4. A client holding the same symbol on NSE and BSE.
5. A frozen-quote case (last trade months old).
6. A split/bonus during a holding period.
7. A full exit followed by re-entry.
8. A recycling book (capital deployed ≪ gross bought).

## Intentional differences from v1's *current* numbers

| Item | v1 today | v2 |
|---|---|---|
| "Invested" | `buys − sells` (or open cost) | capital deployed **and** current invested, both shown |
| Return % | ÷ open cost | ÷ capital deployed |
| CAGR under a year | annualised | withheld; total return shown |
| Sharpe / beta / alpha | blank or misaligned | populated from daily TWR |
| Benchmark lines | open-cost baseline, trade-day points | shared baseline, daily points |
| Midcap benchmark | Midcap 100 (dead since 17 Jul) | Midcap 150, labelled |
| Manager vs client | could disagree | identical by construction |

(Most of these are already implemented on v1's `main` working tree; MIGRATION-PLAN Phase 0 ships them so users see correct numbers during the rewrite.)
