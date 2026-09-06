# Database Caching Strategy for External API Calls

## Problem
External API calls (market data, quotes, historical prices) are made repeatedly, causing:
- Slow performance (2-3 seconds per request)
- Rate limiting risk
- Unnecessary network overhead

## Solution
Cache external data in MongoDB with TTL-based expiration.

## Implementation

### 1. Market Data Cache (DONE)
**File**: `app/services/market_data_cache.py`
- Caches quotes (5-minute TTL)
- Caches historical data (24-hour TTL)
- Auto-cleanup of expired entries

### 2. Integrate with Market Data Service
**File**: `app/services/market_data.py`

Update `get_quotes()` function:
```python
async def get_quotes(symbols, exchanges):
    from app.services.market_data_cache import market_cache
    
    # Check cache first
    quotes = {}
    uncached = []
    for sym in symbols:
        cached = await market_cache.get_quote(sym, exchanges.get(sym, "NSE"))
        if cached:
            quotes[sym] = cached
        else:
            uncached.append(sym)
    
    # Fetch only uncached
    if uncached:
        new_data = fetch_from_angel_or_kite(uncached)
        for sym, data in new_data.items():
            await market_cache.cache_quote(sym, exchanges.get(sym, "NSE"), data)
            quotes[sym] = data
    
    return quotes
```

### 3. Initialize Cache in MongoDB
Add indexes on startup:
```python
await db.market_cache.create_index([("symbol", 1), ("exchange", 1), ("type", 1)])
await db.market_cache.create_index([("expires_at", 1)], expireAfterSeconds=0)
```

### 4. Cache Classification Data (Permanent)
Store stock classifications in MongoDB, never expire.

### 5. Background Cleanup Job
Run daily to remove expired cache entries:
```python
await market_cache.cleanup_expired()
```

## Expected Performance Improvement
- Quote lookups: 2.3s → ~50ms (cached)
- Historical data: 1.5s → ~100ms (cached)
- Overall dashboard load: 10-15s → 3-5s

## TTL Configuration
| Data Type | TTL | Reason |
|-----------|-----|--------|
| Quotes | 5-15 min | Intraday changes |
| Historical | 24 hours | Daily data |
| Classifications | Forever | Rarely changes |
| Corporate Actions | 7 days | Already cached |
