# 04 — Ingestion Pipeline & Calculation Engine

## Upload sequence

```
Manager        FastAPI (tradebooks)        Mongo                 Engine (worker)
  │  POST file        │                       │                      │
  ├──────────────────▶│                       │                      │
  │              parse xlsx/csv               │                      │
  │              map columns (Zerodha profile)│                      │
  │              validate rows                │                      │
  │              compute file_hash            │                      │
  │                   │  find file_hash ──────▶│                      │
  │                   │◀── exists? reject 409  │                      │
  │                   │  insert upload(vN,PENDING)                    │
  │                   │──────────────────────▶│                      │
  │              for each row: build fingerprint                     │
  │                   │  insertMany trades (ordered:false)           │
  │                   │──────────────────────▶│                      │
  │                   │◀── dup-key errors = duplicate_count          │
  │                   │  update upload → IMPORTED/PARTIAL             │
  │                   │──────────────────────▶│                      │
  │◀── 200 summary    │                       │  trigger recompute ─▶│
  │                   │                       │◀─ positions+snapshot ┤
```

### Column mapping (Zerodha profile)
A named mapping config, not hardcoded scattershot. Example:
```yaml
zerodha:
  trade_date: "Trade Date"
  symbol: "Symbol"
  exchange: "Exchange"
  trade_type: "Trade Type"     # buy/sell → BUY/SELL
  quantity: "Quantity"
  price: "Price"
  order_id: "Order ID"
  trade_id: "Trade ID"
```
New broker = new profile, no engine changes.

### Dedupe (the "uploaded twice" guarantee)
- **Exact file** re-upload → blocked by `file_hash`.
- **Overlapping range** (Jan–Jun then Jan–Aug) → per-row `fingerprint` +
  `{client_id, fingerprint}` unique index. `insertMany(ordered:false)` lets the new
  (August) rows insert while the overlapping (Jan–Jun) rows fail as duplicates and are
  counted, not doubled.
- `external_trade_id` (Zerodha Trade ID) is the strongest fingerprint component when present.

## FIFO calculation engine (pure Python)

Input: all trades for a client, ascending by `(trade_date, trade_time)`.
Output: `positions[]`, `realized_pnl`.

```
open_lots: deque per symbol   # each lot = {qty, unit_cost}

on BUY:
    unit_cost = (price*qty + charges.total) / qty        # charges INCLUDED
    push lot {qty, unit_cost}

on SELL:
    proceeds = price*qty - charges.total                  # charges INCLUDED
    remaining = qty
    matched_cost = 0
    while remaining > 0:
        lot = open_lots[0]
        take = min(remaining, lot.qty)
        matched_cost += take * lot.unit_cost
        lot.qty -= take; remaining -= take
        if lot.qty == 0: open_lots.popleft()
    realized_pnl += proceeds - matched_cost

after all trades:
    quantity      = sum(lot.qty for open lots)
    invested_value= sum(lot.qty * lot.unit_cost)
    avg_cost      = invested_value / quantity
```

Worked example (INFY):
```
BUY 100 @ ₹1400  (+charges)
BUY  50 @ ₹1450
SELL 70 @ ₹1550   → matches 70 from the 100-lot
────────────────────────────────────────────
remaining: 30 @ ~1400 lot  +  50 @ ~1450 lot  = 80 shares
realized_pnl = 70*1550_proceeds − 70*1400_cost  (net of charges)
```

## Valuation (market enrichment)

```
unrealized_pnl(symbol) = quantity * (market_price - avg_cost)
market_value(symbol)   = quantity * market_price
portfolio_value        = Σ market_value + cash(if modeled)
total_pnl              = realized_pnl + unrealized_pnl
return_pct             = total_pnl / invested_value
```
`market_price` comes from `market_quotes_cache`. If stale/missing → return last price with
`stale:true`; quantity/holdings are **never** hidden due to a quote failure.

## Allocation

```
sector_alloc[s]  = Σ market_value where security.sector == s   / portfolio_value
asset_alloc[a]   = Σ market_value where security.asset_class==a / portfolio_value
stock_alloc[sym] = market_value(sym) / portfolio_value
```

## Concentration (Phase-1 extra)
```
top5_pct          = Σ top-5 holdings market_value / portfolio_value
largest_stock_pct = max stock_alloc
largest_sector_pct= max sector_alloc
```

## Snapshotting
- After each recompute: upsert today's `portfolio_daily_snapshots`.
- Scheduled `eod-snapshot` timer: write end-of-day snapshot for every active client so the
  performance chart has a continuous series even on no-trade days.
