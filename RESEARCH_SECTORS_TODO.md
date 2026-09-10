# Research Sectors — Build Status & TODO

Scope: **research side only** (`/screener` + `/sectors`). The managers'/holdings
`securities.classify()` taxonomy is intentionally **untouched**.

## ✅ Done (this build)

- Expanded research sectors **4 → 10**.
  - Existing: `hotels`, `banks`, `it`, `auto`
  - **New:** `pharma`, `fmcg`, `metals`, `energy`, `realty`, `cement`
- **160 stocks** total across sectors (8 "covered" + a roster each).
- Every new ticker **validated against the Angel scrip master** — all price live in the
  screener (no dead symbols like the earlier TATAMOTORS/LTIM problem).
- Each stock tagged with a **domain-specific sub-industry `segment`** (e.g. Pharma →
  Formulations / API / CDMO / Hospitals; Energy → Upstream / Refining / Gas / Power gen).
- New sectors flow through `/screener` automatically (endpoint iterates `SECTORS_REGISTRY`),
  with **live market data** (price, 1D/1W/1M/1Y, RSI, levels, volume) working now.
- KPI schema fields are present but `None` (ready to fill) — screener shows
  "KPIs not researched yet" for these, honestly.

Files: `backend/app/data/{pharma,fmcg,metals,energy,realty,cement}_sector.py`,
`backend/app/data/_sector_scaffold.py`; registered in `backend/app/routers/sectors.py`.

## ⬜ TODO — KPI research phase (do next)

### 1. Fill operational/quarterly KPI values (the main task)
Source decision still open: **(a)** hand-research from earnings filings, or **(b)** a
fundamentals API/data file. Kite MCP does **not** provide fundamentals (confirmed — it's
market-data only), so it can't fill these.

Per-sector KPIs to populate (fields already stubbed in each `*_COVERED` entry):
- **Pharma:** US sales %, R&D % of sales, API vs formulations mix, USFDA plant status,
  domestic (IPM) growth; hospitals → beds, ARPOB, occupancy.
- **FMCG:** underlying volume growth, gross margin, rural vs urban, A&P % of sales, price/mix.
- **Metals:** volume (t), realisation/t, EBITDA/t, capacity utilisation, input costs,
  net-debt/EBITDA, export share.
- **Energy:** by sub-type — Upstream (production, realisation); Refining/OMC (GRM, marketing
  margin, inventory gain/loss); Gas (mmscmd, spread); Power (MW, PLF, merchant/PPA, tariff).
- **Realty:** pre-sales/bookings (₹cr + area), collections, launches, net debt, annuity income.
- **Cement:** volume (mt), realisation/t, EBITDA/t, capacity & utilisation, fuel/freight cost.

### 2. Market-derived fundamentals (market cap, P/E)
`market_cap_cr` and `pe_label` are null. Price is live, but shares-outstanding / EPS aren't in
Kite or the current feed. Need a source (fundamentals API or manual) or compute where possible.

### 3. `screener._fundamentals()` schema work
- Currently special-cases only `banks` and `it`; the 6 new sectors fall through to the
  hotels/auto shape (revenue / EBITDA margin / PAT) — fine as a default, but:
- Add **sector-specific KPI rows** where the default is wrong/weak (Metals EBITDA/tonne,
  Realty pre-sales, Energy sub-type splits).
- **Not yet added:** `finserv` (NBFC/insurance) and its bank-like schema — deferred.

### 4. `/sectors` R&D page (`SectorResearch.jsx`)
Check for hardcoded sector tabs; wire the 6 new sectors in (the `/screener` page is already
dynamic and shows them). Ensure it renders gracefully with null KPIs.

### 5. Industry benchmarks
`INDUSTRY_BENCHMARK` is a stub (`{"note": "to research"}`) in each new sector — fill per
sector (e.g., sector avg growth/margins, index P/E) during the KPI phase.

### 6. More sectors to add later (rosters not yet built)
`capital goods / defence`, `financial services (NBFC)`, `insurance`, `chemicals`,
`consumer durables`, `infrastructure`, `telecom`, `textiles`.

### 7. Optional market-data upgrade (separate)
Consider switching the screener's market data to **Kite MCP** for authoritative NSE OHLC —
gives a *true ATR* (real intraday high/low) vs today's close-only approximation, plus ISIN /
F&O flags / circuit limits. Requires the daily Kite login.
