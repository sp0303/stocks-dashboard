# 02 — Data Model (MongoDB)

Mongo-only. Relationships are by `ObjectId` reference; integrity is enforced in the
FastAPI layer. All money stored as integer **paise** (or Decimal128) to avoid float drift —
never store rupee amounts as JS floats.

## Collection relationships

```
users (SUPER_ADMIN, PORTFOLIO_MANAGER)
  │  _id
  │
  └──< clients.portfolio_manager_id
             │  _id
             ├──< tradebook_uploads.client_id
             │          │  _id
             │          └──< trades.tradebook_upload_id
             │
             ├──< trades.client_id ──────────┐
             ├──< positions.client_id        │ engine derives
             └──< portfolio_daily_snapshots.client_id
                                              │
   trades.symbol ──▶ securities._id (symbol)  │
   watchlists.owner_id ─▶ users._id | clients._id
```

Managers are simply `users` with `role = PORTFOLIO_MANAGER` (no separate collection).
Clients are **not** users in Phase 1 (no login).

---

## `users`
Auth principals: super admins and portfolio managers.
```jsonc
{
  _id: ObjectId,
  email: "manager@firm.com",      // unique
  password_hash: "argon2...",
  name: "Asha R",
  role: "SUPER_ADMIN" | "PORTFOLIO_MANAGER",
  status: "ACTIVE" | "DISABLED",
  created_by: ObjectId | null,    // super-admin who created this manager
  last_login_at: ISODate | null,
  created_at, updated_at: ISODate
}
```
Indexes: `{email:1}` unique · `{role:1, status:1}`

## `clients`
Owned by exactly one manager. No login in Phase 1.
```jsonc
{
  _id: ObjectId,
  portfolio_manager_id: ObjectId,   // → users._id (role PM)
  name: "Client A",
  email, phone: string | null,
  external_reference: "CRM-1023" | null,
  onboarded_at: ISODate,            // start of the "journey" timeline
  status: "ACTIVE" | "INACTIVE",
  created_at, updated_at: ISODate
}
```
Indexes: `{portfolio_manager_id:1, status:1}` · `{external_reference:1}`

## `tradebook_uploads`
One document per uploaded file. Versioned — never deleted on re-upload.
```jsonc
{
  _id: ObjectId,
  client_id: ObjectId,
  version: 3,                       // per-client incrementing
  file_name: "tradebook_jan_aug.xlsx",
  file_hash: "sha256...",           // reject exact-duplicate file re-upload
  uploaded_by: ObjectId,            // → users._id
  uploaded_at: ISODate,
  trade_date_from, trade_date_to: ISODate,
  status: "PENDING"|"IMPORTED"|"FAILED"|"PARTIAL",
  row_count: 1450,
  imported_count: 1449,
  duplicate_count: 0,
  error_count: 1
}
```
Indexes: `{client_id:1, version:-1}` · `{file_hash:1}`

## `trades`
The ledger. Immutable once imported. **Dedupe is enforced here.**
```jsonc
{
  _id: ObjectId,
  client_id: ObjectId,
  tradebook_upload_id: ObjectId,
  fingerprint: "sha1(client|date|symbol|type|qty|price|ext_id)",
  trade_date: ISODate,
  trade_time: "09:31:05" | null,
  symbol: "INFY",
  exchange: "NSE",
  trade_type: "BUY" | "SELL",
  quantity: 100,
  price: 142000,                    // paise
  gross_value: 14200000,            // paise = price*qty
  charges: { brokerage, taxes, other, total },  // paise
  external_trade_id: "Z-88231" | null,
  created_at: ISODate
}
```
Indexes:
- `{client_id:1, fingerprint:1}` **unique** ← the anti-double-count guarantee
- `{client_id:1, symbol:1, trade_date:1}` ← FIFO scan order
- `{tradebook_upload_id:1}`

## `securities` (security master)
Not fetched from an API at render time — stored and periodically enriched.
```jsonc
{
  _id: "INFY",                      // symbol as _id
  isin: "INE009A01021",
  company_name: "Infosys Ltd",
  exchange: "NSE",
  sector: "Information Technology",
  industry: "IT Services",
  asset_class: "EQUITY",            // EQUITY|ETF|DEBT|GOLD|CASH|OTHER
  updated_at: ISODate
}
```

## `positions` (derived — current holdings)
Rebuilt by the engine after every import. One doc per open holding per client.
```jsonc
{
  _id: ObjectId,
  client_id: ObjectId,
  symbol: "INFY",
  quantity: 80,                     // buys - sells
  avg_cost: 142500,                 // paise, incl. charges, FIFO remaining lots
  invested_value: 11400000,         // paise, sum of open-lot cost
  realized_pnl: 2450000,            // paise, cumulative for this symbol
  open_lots: [ { qty: 80, unit_cost: 142500, trade_date: ISODate } ],
  last_computed_at: ISODate
}
```
Indexes: `{client_id:1, symbol:1}` unique

## `portfolio_daily_snapshots` (derived — time series)
Makes performance charts O(1) to read.
```jsonc
{
  _id: ObjectId,
  client_id: ObjectId,
  date: ISODate,                    // date-only
  portfolio_value, invested_value,
  realized_pnl, unrealized_pnl, total_pnl,   // paise
  created_at: ISODate
}
```
Indexes: `{client_id:1, date:1}` unique

## `market_quotes_cache`
Latest yfinance quote per symbol; decouples reads from provider uptime.
```jsonc
{ _id: "INFY", price: 156000, as_of: ISODate, source: "yfinance", stale: false }
```

## `watchlists`
```jsonc
{ _id: ObjectId, owner_type: "MANAGER"|"CLIENT", owner_id: ObjectId, symbols: ["INFY","TCS"], updated_at }
```
Index: `{owner_type:1, owner_id:1}` unique

## `audit_logs`
```jsonc
{ _id, actor_id, action: "CLIENT_CREATE", entity: "client", entity_id, meta: {}, at: ISODate }
```
Index: `{actor_id:1, at:-1}` · `{entity:1, entity_id:1}`

---

## Phase 2 (Mongo, added later)
`news_articles`, `ai_summaries` — document-shaped, symbol/sector-tagged. Kept fully
separate from the financial collections above.
