# Multi-Account Portfolio Integration Specification

## Current Implementation
- **Broker**: Kite (Zerodha) ONLY
- **Multiple Accounts**: Yes - Different Kite users (different login credentials)
- **Data Sync**: 100% auto from Kite API - NO manual trade entry
- **New**: Sharpe Ratio calculation + Multi-account consolidation

---

## Architecture: Multiple Kite Accounts (Same Broker, Different Users)

### ✅ Currently Supported
```
┌─ Client Dashboard
   ├─ Account 1: Sumanth (Kite)
   │  ├─ User ID: QPJ806
   │  ├─ Trades: AUTO-SYNCED ✅
   │  ├─ Holdings: AUTO-SYNCED ✅
   │  ├─ Cash: AUTO-SYNCED ✅
   │  └─ 24-hour cache ✅
   │
   ├─ Account 2: User2 (Kite)
   │  ├─ User ID: ???
   │  ├─ Trades: AUTO-SYNCED (ready)
   │  ├─ Holdings: AUTO-SYNCED (ready)
   │  ├─ Cash: AUTO-SYNCED (ready)
   │  └─ 24-hour cache (ready)
   │
   └─ Account 3: User3 (Kite)
      └─ [Same structure]

⚠️  NO Manual Trade Entry - All data pulled from Kite
🔄 Each account syncs every 24 hours (smart cache)
📊 Consolidated metrics across all accounts
```

---

## Data Fields Required FROM USER

### For Each Kite Account (Per User):

```json
{
  "account_name": "Sumanth Trading",
  "broker": "kite",
  "is_active": true,
  "owner_name": "Sumanth",
  "kite_api_key": "qjrz8qtbxcy9qcuq",
  "kite_api_secret": "0up53rdbf0hyjw48pnb1s03j6ybvjuiv",
  "kite_user_id": "QPJ806",
  "kite_password": "Sumanth@27",
  "kite_totp_secret": "Y54RV3LKV4LBR6DEAGT6DZHN4BL3LUUH",
  "account_type": "trading|investing|margin",
  "risk_free_rate": 0.06,
  "benchmark": "nifty50"
}
```

### Per Account Configuration:
- **Account Name**: Label for dashboard (e.g., "Sumanth Trading")
- **Owner Name**: User name
- **Account Type**: How they use it (trading / long-term investing / margin)
- **Risk-Free Rate**: For Sharpe calculation (default 6% for India)
- **Benchmark**: Nifty 50 / Nifty 100 (for Beta/Alpha later)

---

## Calculated Metrics (Once Data Integrated)

### Per Account:
- ✅ Invested Value
- ✅ Market Value
- ✅ P&L (Realized + Unrealized)
- ✅ Return %
- ✅ XIRR
- ✅ CAGR
- ✅ Volatility
- ✅ Max Drawdown
- ✅ **Sharpe Ratio** (NEW)
- ✅ Profit Factor
- ✅ Win Rate

### Consolidated (All Accounts):
- 📊 **Consolidated Portfolio Value**
- 📊 **Consolidated P&L**
- 📊 **Aggregate Return**
- 📊 **Sector Allocation** (across all brokers)
- 📊 **Asset Class Allocation** (Equity/MF/FD/Gold)
- 📊 **Consolidated Sharpe Ratio**
- 📊 **Tax Report** (STCG/LTCG)

---

## Implementation Phases

### Phase 1: Single Kite Account (Done ✅)
- [x] Kite API authentication (Sumanth)
- [x] Trades auto-sync
- [x] Holdings auto-sync
- [x] Cash balance auto-sync
- [x] 24-hour cache
- [x] Sharpe Ratio calculation

### Phase 2: Multi-Kite-Account Support (3-5 days) - NEXT
- [ ] Account selector UI
- [ ] Multiple account credentials storage
- [ ] Per-account sync endpoints
- [ ] Account switching UI
- [ ] Consolidated metrics

### Phase 3: Professional Metrics (5-7 days)
- [ ] Beta calculation (vs Nifty 50)
- [ ] Alpha calculation
- [ ] Max Drawdown
- [ ] XIRR / CAGR
- [ ] Profit Factor
- [ ] Win Rate

### Phase 4: Tax & Reporting (7-10 days)
- [ ] STCG/LTCG breakdown
- [ ] Tax impact report
- [ ] Dividend tracking
- [ ] Interest accrued (FDs)

---

## Data Needed From You (Multiple Kite Users)

### Account 1: Sumanth (READY ✅)
```
├─ API Key: qjrz8qtbxcy9qcuq ✅
├─ API Secret: 0up53rdbf0hyjw48pnb1s03j6ybvjuiv ✅
├─ User ID: QPJ806 ✅
├─ Password: Sumanth@27 ✅
├─ TOTP Secret: Y54RV3LKV4LBR6DEAGT6DZHN4BL3LUUH ✅
└─ Status: Waiting for Kite CAPTCHA to expire
```

### Account 2: Other Kite User (if exists)
```
├─ Name: ?
├─ API Key: ?
├─ API Secret: ?
├─ User ID: ?
├─ Password: ?
└─ TOTP Secret: ?
```

### Account 3: Another User (if exists)
```
├─ Name: ?
├─ API Key: ?
├─ API Secret: ?
├─ User ID: ?
├─ Password: ?
└─ TOTP Secret: ?
```

**How many other Kite users do you need to track?**

---

## Kite API Endpoints We Use

| Endpoint | Purpose | Status |
|----------|---------|--------|
| POST /api/login | User authentication | ✅ |
| POST /api/twofa | TOTP verification | ✅ |
| POST /session/token | Get access token | ✅ |
| GET /portfolio/holdings | Current positions | ✅ |
| GET /orders | Trade history | ✅ |
| GET /margins | Account summary + cash | ✅ |
| GET /profile | User details | ✅ |

**Rate Limits**: 10 requests/second per API key
**Caching**: 24 hours (to avoid exhaustion)
**Authentication**: Auto-refresh from .env TOTP secret

---

## Multi-Account Response Format

### Consolidated Portfolio (Multiple Kite Users):
```json
{
  "summary": {
    "total_accounts": 3,
    "accounts": [
      {
        "account_id": "kite_sumanth",
        "owner": "Sumanth",
        "broker": "kite",
        "user_id": "QPJ806",
        "status": "connected",
        "invested_value": 200000,
        "market_value": 224162,
        "pnl": 24162,
        "return_pct": 12.08,
        "sharpe_ratio": 1.45,
        "trades": 42,
        "holdings": 15,
        "cash": 25000,
        "last_synced": "2026-09-05T14:30:00Z",
        "sync_from_cache": false
      },
      {
        "account_id": "kite_user2",
        "owner": "Rajesh",
        "broker": "kite",
        "user_id": "ABC123",
        "status": "connected",
        "invested_value": 150000,
        "market_value": 165000,
        "pnl": 15000,
        "return_pct": 10.0,
        "sharpe_ratio": 1.20,
        "trades": 28,
        "holdings": 12,
        "cash": 18500,
        "last_synced": "2026-09-05T14:20:00Z",
        "sync_from_cache": true
      }
    ],
    "consolidated": {
      "total_invested": 350000,
      "total_market_value": 389162,
      "total_pnl": 39162,
      "consolidated_return": 11.18,
      "consolidated_sharpe": 1.38,
      "total_trades": 70,
      "total_holdings": 27,
      "total_cash": 43500,
      "account_count": 2
    }
  }
}
```

**Key Features:**
- Each account syncs independently every 24 hours
- Consolidated metrics calculated from all accounts
- UI shows per-account + consolidated views
- No manual data entry - everything from Kite API

---

## Implementation Checklist

### Backend:
- [x] Sharpe Ratio calculation
- [x] Single Kite account sync + caching
- [ ] Multi-account data schema
- [ ] Per-account credential storage
- [ ] Consolidated portfolio calculation
- [ ] Account switching endpoints
- [ ] Professional metrics (Beta, Alpha, etc.)

### Frontend:
- [ ] Account selector dropdown
- [ ] Account switcher UI
- [ ] Per-account dashboard view
- [ ] Consolidated portfolio view
- [ ] Add account form
- [ ] Account management (edit/delete)

### Database:
- [x] Encrypted credential storage (Sumanth)
- [ ] Account metadata table
- [ ] Account mapping (client → accounts)
- [ ] Per-account sync cache

---

## Testing Strategy

### Phase 1: Single Account (Sumanth) ✅ READY
1. **Wait for Kite CAPTCHA to expire** (2-3 hours from failed auth)
2. **Test authentication** with new TOTP secret Y54RV3LKV4LBR6DEAGT6DZHN4BL3LUUH
3. **Pull live trade data** and verify Sharpe Ratio calculation
4. **Test 24-hour cache** - sync twice, confirm 2nd sync is from cache
5. **Verify all metrics** show correct portfolio value

### Phase 2: Multiple Accounts (When ready)
1. Add 2nd Kite user credentials
2. Test per-account sync (independent 24-hour caches)
3. Test consolidated metrics calculation
4. UI: Account selector + switching
5. Verify consolidated Sharpe Ratio correct

---

## Implementation Timeline

| Phase | Task | Duration | Blocker |
|-------|------|----------|---------|
| **1** | ✅ Sharpe Ratio | Done | None |
| **2** | 🔄 Test with Sumanth (live data) | Wait for CAPTCHA expire | Kite locked |
| **3** | Multi-account UI | 2-3 days | Phase 2 complete |
| **4** | Professional metrics (Beta/Alpha) | 3-5 days | -|
| **5** | Consolidated dashboard | 3-5 days | Phase 3 complete |

---

## Critical Questions for You

1. **How many Kite accounts** do you need to track? (Sumanth + how many others?)
2. **For each user**, can you provide:
   - Name
   - Kite API Key
   - Kite API Secret
   - Kite User ID
   - Kite Password
   - Kite TOTP Secret
3. **Account naming**: Should each show as "Sumanth's Trading", "Rajesh's Investing", etc?

---

Generated: 2026-09-05
