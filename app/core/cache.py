# app/core/cache.py
"""
Redis cache implementation for Fintellic API
Provides caching functionality for filings, companies, and statistics
"""

import json
import redis
from typing import Optional, Any, List, Dict
from datetime import timedelta
from functools import wraps
import hashlib
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache wrapper with JSON serialization"""
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
        self.default_ttl = 300  # 5 minutes default
        
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL"""
        try:
            ttl = ttl or self.default_ttl
            serialized = json.dumps(value, default=str)
            return self.redis_client.setex(key, ttl, serialized)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter"""
        try:
            return self.redis_client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Cache increment error: {e}")
            return None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for key"""
        try:
            ttl = self.redis_client.ttl(key)
            return ttl if ttl > 0 else None
        except Exception as e:
            logger.error(f"Cache get TTL error: {e}")
            return None


# Initialize cache instance
cache = RedisCache()


# Cache key generators
def make_cache_key(*args, **kwargs) -> str:
    """Generate cache key from arguments"""
    key_parts = [str(arg) for arg in args]
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")
    
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


# Cache decorators
def cache_result(ttl: int = 300, prefix: str = "api"):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{prefix}:{func.__name__}:{make_cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            logger.debug(f"Cache miss, stored: {cache_key}")
            
            return result
        return wrapper
    return decorator


# Specific cache functions for Fintellic

class FilingCache:
    """Cache operations for filings"""
    
    @staticmethod
    def get_filing_list_key(
        skip: int = 0,
        limit: int = 20,
        filing_type: Optional[str] = None,
        company_cik: Optional[str] = None
    ) -> str:
        """Generate cache key for filing list"""
        return f"filings:list:{make_cache_key(skip=skip, limit=limit, filing_type=filing_type, company_cik=company_cik)}"
    
    @staticmethod
    def get_filing_detail_key(filing_id: str) -> str:
        """Generate cache key for filing detail"""
        return f"filings:detail:{filing_id}"
    
    @staticmethod
    def invalidate_filing_list():
        """Invalidate all filing list caches"""
        return cache.delete_pattern("filings:list:*")


class CompanyCache:
    """Cache operations for companies"""
    
    @staticmethod
    def get_company_key(company_id: str) -> str:
        """Generate cache key for company"""
        return f"companies:detail:{company_id}"
    
    @staticmethod
    def get_company_list_key() -> str:
        """Generate cache key for company list"""
        return f"companies:list:all"


class StatsCache:
    """Cache operations for statistics"""
    
    @staticmethod
    def get_popular_filings_key(period: str = "day") -> str:
        """Generate cache key for popular filings"""
        return f"stats:popular:{period}"
    
    @staticmethod
    def increment_view_count(filing_id: str) -> int:
        """Increment filing view count"""
        key = f"stats:views:{filing_id}"
        count = cache.increment(key)
        # Set expiry to 30 days if new key
        if count == 1:
            cache.redis_client.expire(key, 30 * 24 * 60 * 60)
        return count
    
    @staticmethod
    def get_view_count(filing_id: str) -> int:
        """Get filing view count"""
        key = f"stats:views:{filing_id}"
        count = cache.get(key)
        return int(count) if count else 0
    
    @staticmethod
    def record_vote(filing_id: str, user_id: str, vote_type: str) -> bool:
        """Record user vote (bullish/bearish)"""
        key = f"stats:votes:{filing_id}:{vote_type}"
        user_key = f"stats:user_votes:{user_id}:{filing_id}"
        
        # Check if user already voted
        existing_vote = cache.get(user_key)
        if existing_vote:
            # Remove previous vote
            old_key = f"stats:votes:{filing_id}:{existing_vote}"
            cache.increment(old_key, -1)
        
        # Record new vote
        cache.set(user_key, vote_type, ttl=30 * 24 * 60 * 60)  # 30 days
        cache.increment(key)
        return True
    
    @staticmethod
    def get_vote_counts(filing_id: str) -> Dict[str, int]:
        """Get vote counts for filing"""
        bullish_key = f"stats:votes:{filing_id}:bullish"
        bearish_key = f"stats:votes:{filing_id}:bearish"
        
        bullish = cache.get(bullish_key) or 0
        bearish = cache.get(bearish_key) or 0
        
        return {
            "bullish": int(bullish),
            "bearish": int(bearish)
        }


# Cache TTL constants
CACHE_TTL = {
    "filing_list": 5 * 60,        # 5 minutes
    "filing_detail": 60 * 60,     # 1 hour
    "company_list": 60 * 60,      # 1 hour
    "company_detail": 60 * 60,    # 1 hour
    "popular_filings": 10 * 60,   # 10 minutes
    "earnings_calendar": 60 * 60, # 1 hour
}