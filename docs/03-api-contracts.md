# 03 — API Contracts

Base: `/api`. Auth: `Authorization: Bearer <JWT>`. JWT carries `sub` (user id) and `role`.

## Auth & RBAC model

```
SUPER_ADMIN        → everything
PORTFOLIO_MANAGER  → only clients where client.portfolio_manager_id == sub
CLIENT (Phase 4)   → only own portfolio, read-only
```

**Ownership rule (enforced server-side on every client-scoped route):**
before touching `client_id`, verify the manager owns it. Never trust the path id.

```python
async def require_client_access(client_id, user):
    client = await clients.find_one({"_id": client_id})
    if not client: raise 404
    if user.role == "PORTFOLIO_MANAGER" and client["portfolio_manager_id"] != user.id:
        raise 403
    return client
```

## Endpoints

### Auth
```
POST   /api/auth/login            {email, password} → {access_token, refresh_token, role}
POST   /api/auth/refresh          {refresh_token}   → {access_token}
POST   /api/auth/logout
```

### Admin (SUPER_ADMIN only)
```
GET    /api/admin/managers                 list managers (+status, client counts)
POST   /api/admin/managers                 {email, name, password} → create manager
PATCH  /api/admin/managers/:id             {name?, status?}  activate/deactivate/edit
GET    /api/admin/managers/:id/clients     clients under a manager
GET    /api/admin/audit                    activity feed
POST   /api/admin/securities               upsert security master entry
```

### Clients (PORTFOLIO_MANAGER, own clients)
```
GET    /api/manager/clients                list own clients
POST   /api/manager/clients                {name, email?, phone?, onboarded_at} → create
GET    /api/manager/clients/:id            client profile
PATCH  /api/manager/clients/:id            update
DELETE /api/manager/clients/:id            soft-deactivate (status=INACTIVE)
```

### Tradebooks
```
POST   /api/clients/:id/tradebooks         multipart file → {upload_id, version, row_count,
                                             imported_count, duplicate_count, error_count}
GET    /api/clients/:id/tradebooks         version history
GET    /api/clients/:id/tradebooks/:uid    upload detail + row-level errors
```

### Portfolio (reads served from derived collections)
```
GET    /api/clients/:id/portfolio          overview cards: value, invested, realized,
                                             unrealized, total_pnl, return_pct
GET    /api/clients/:id/holdings           positions + live price + pnl + portfolio_pct + sector
GET    /api/clients/:id/trades             ?symbol&from&to&type  paginated ledger
GET    /api/clients/:id/allocation         ?by=sector|asset|stock  → [{key, value, pct}]
GET    /api/clients/:id/performance        ?from&to&interval  snapshot time series
GET    /api/clients/:id/concentration      top5_pct, largest_stock_pct, largest_sector_pct
GET    /api/clients/:id/stocks/:symbol     stock journey: first/last buy, last sell,
                                             total bought/sold, realized+unrealized, timeline
```

### Watchlist
```
GET    /api/clients/:id/watchlist
POST   /api/clients/:id/watchlist          {symbol}  add
DELETE /api/clients/:id/watchlist/:symbol  remove
GET    /api/manager/watchlist              manager-level
POST   /api/manager/watchlist              {symbol}
```

### Market data (server-side only)
```
GET    /api/market/quote/:symbol           cached quote (+stale flag)
GET    /api/market/history/:symbol         ?from&to
```

### Phase 2
```
GET    /api/clients/:id/news               portfolio-relevant, AI-summarized
```

## Standard response envelope
```jsonc
{ "data": <payload>, "error": null, "meta": { "page": 1, "total": 143 } }
```
Money returned in paise as integers; the frontend formats to ₹/lakh. Every response that
depends on market prices includes `priced_at` and `stale: bool`.
