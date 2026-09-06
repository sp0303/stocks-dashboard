"""Simple in-memory cache for expensive API endpoints."""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable

class SimpleCache:
    def __init__(self):
        self.cache = {}
        self.expiry = {}

    async def get_or_compute(self, key: str, fn: Callable, ttl_seconds: int = 30) -> Any:
        """Get cached value or compute and cache it."""
        now = datetime.now()
        
        # Return cached value if fresh
        if key in self.cache:
            if self.expiry[key] > now:
                return self.cache[key]
            else:
                del self.cache[key]
                del self.expiry[key]

        # Compute and cache
        result = await fn() if asyncio.iscoroutinefunction(fn) else fn()
        self.cache[key] = result
        self.expiry[key] = now + timedelta(seconds=ttl_seconds)
        return result

    def clear(self):
        """Clear all cached values."""
        self.cache.clear()
        self.expiry.clear()

# Global cache instance
request_cache = SimpleCache()
