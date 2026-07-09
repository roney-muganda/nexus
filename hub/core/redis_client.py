import json
import logging
from typing import Any, Optional
import redis.asyncio as redis

from hub.config import settings

logger = logging.getLogger(__name__)

_redis_client = None

async def get_redis() -> redis.Redis:
    """Lazily initialize and return the global Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    return _redis_client

async def check_redis_health():
    """Ping Redis on startup to ensure the connection is alive."""
    try:
        r = await get_redis()
        await r.ping()
        logger.info("✅ Successfully connected to Upstash Redis")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")

async def close_redis():
    """Close the Redis connection pool cleanly on shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        logger.info("Redis connection closed.")

async def cache_set(key: str, value: Any, ttl_seconds: int = 300):
    """Serialize and store a value in Redis with an expiration."""
    try:
        r = await get_redis()
        await r.setex(key, ttl_seconds, json.dumps(value))
    except Exception as e:
        logger.warning(f"Redis cache_set failed for {key}: {e}")

async def cache_get(key: str) -> Optional[Any]:
    """Retrieve and deserialize a value from Redis."""
    try:
        r = await get_redis()
        data = await r.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Redis cache_get failed for {key}: {e}")
    return None

async def cache_delete(key: str):
    """Delete a specific key from Redis."""
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as e:
        logger.warning(f"Redis cache_delete failed for {key}: {e}")

async def cache_delete_pattern(pattern: str):
    """Delete all keys matching a specific pattern (e.g., 'session:*')."""
    try:
        r = await get_redis()
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception as e:
        logger.warning(f"Redis cache_delete_pattern failed for {pattern}: {e}")