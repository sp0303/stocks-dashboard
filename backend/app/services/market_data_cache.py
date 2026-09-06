"""Market data caching layer to reduce external API calls."""
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import asyncio

class MarketDataCache:
    """Cache for market quotes and historical data."""
    
    def __init__(self, mongo_db=None):
        self.db = mongo_db
    
    async def get_quote(self, symbol: str, exchange: str = "NSE", ttl_minutes: int = 5):
        """Get cached quote or fetch from API."""
        if not self.db:
            return None
        
        # Check cache first
        cached = await self.db.market_cache.find_one({
            "symbol": symbol,
            "exchange": exchange,
            "type": "quote",
            "expires_at": {"$gt": datetime.now()}
        })
        
        if cached:
            return cached.get("data")
        
        # Cache miss - will be fetched and stored by caller
        return None
    
    async def cache_quote(self, symbol: str, exchange: str, data: dict, ttl_minutes: int = 5):
        """Store quote in cache."""
        if not self.db:
            return
        
        await self.db.market_cache.update_one(
            {
                "symbol": symbol,
                "exchange": exchange,
                "type": "quote"
            },
            {
                "$set": {
                    "symbol": symbol,
                    "exchange": exchange,
                    "type": "quote",
                    "data": data,
                    "cached_at": datetime.now(),
                    "expires_at": datetime.now() + timedelta(minutes=ttl_minutes)
                }
            },
            upsert=True
        )
    
    async def get_history(self, symbol: str, from_date: str, exchange: str = "NSE"):
        """Get cached history or mark as needing refresh."""
        if not self.db:
            return None
        
        # Cache historical data for 24 hours (daily data doesn't change within day)
        cached = await self.db.market_cache.find_one({
            "symbol": symbol,
            "type": "history",
            "expires_at": {"$gt": datetime.now()}
        })
        
        if cached:
            return cached.get("data", [])
        
        return None
    
    async def cache_history(self, symbol: str, from_date: str, data: list, exchange: str = "NSE"):
        """Store historical data in cache (24-hour TTL)."""
        if not self.db:
            return
        
        await self.db.market_cache.update_one(
            {
                "symbol": symbol,
                "type": "history",
                "from_date": from_date
            },
            {
                "$set": {
                    "symbol": symbol,
                    "type": "history",
                    "from_date": from_date,
                    "exchange": exchange,
                    "data": data,
                    "cached_at": datetime.now(),
                    "expires_at": datetime.now() + timedelta(hours=24)
                }
            },
            upsert=True
        )
    
    async def cleanup_expired(self):
        """Remove expired cache entries."""
        if not self.db:
            return
        
        result = await self.db.market_cache.delete_many({
            "expires_at": {"$lt": datetime.now()}
        })
        return result.deleted_count


# Global cache instance
market_cache = MarketDataCache()
