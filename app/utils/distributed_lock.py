"""
Distributed lock implementation via Redis for multi-instance scaling.
Falls back to single-instance mode if Redis is not available.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional
import uuid

logger = logging.getLogger(__name__)

_redis_client: Optional[any] = None
_redis_available: bool = False
_redis_initialized: bool = False


async def _init_redis() -> bool:
    """Initialize Redis client if REDIS_URL is set."""
    global _redis_client, _redis_available, _redis_initialized
    
    if _redis_initialized:
        return _redis_available
    
    _redis_initialized = True
    redis_url = os.getenv("REDIS_URL", "").strip()
    
    if not redis_url:
        logger.info("[DISTRIBUTED_LOCK] mode=single-instance reason=redis_url_missing")
        _redis_available = False
        return False
    
    try:
        import redis.asyncio as redis
        _redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Test connection
        await _redis_client.ping()
        _redis_available = True
        logger.info("[DISTRIBUTED_LOCK] mode=redis url=%s", redis_url.split("@")[-1] if "@" in redis_url else "configured")
        return True
    except ImportError:
        logger.warning("[DISTRIBUTED_LOCK] mode=single-instance reason=redis_module_missing")
        _redis_available = False
        return False
    except Exception as exc:
        logger.warning("[DISTRIBUTED_LOCK] mode=single-instance reason=redis_connect_failed error=%s", exc)
        _redis_available = False
        return False


@asynccontextmanager
async def distributed_lock(
    key: str,
    ttl_seconds: int = 10,
    wait_seconds: float = 2.0,
    retry_interval: float = 0.1,
):
    """
    Distributed lock using Redis SET NX EX.
    
    Args:
        key: Lock key (will be prefixed with "lock:")
        ttl_seconds: Lock TTL in seconds (auto-expire)
        wait_seconds: Maximum time to wait for lock acquisition
        retry_interval: Interval between acquisition attempts
    
    Yields:
        bool: True if lock acquired, False otherwise
    
    Example:
        async with distributed_lock("user:123:balance", ttl_seconds=15, wait_seconds=3) as acquired:
            if acquired:
                # Critical section - safe to write
                await update_balance(...)
            else:
                # Lock not acquired - skip or retry later
                logger.warning("Failed to acquire lock")
    """
    await _init_redis()
    
    # Fallback mode: single-instance (no Redis)
    if not _redis_available or _redis_client is None:
        yield True
        return
    
    lock_key = f"lock:{key}"
    lock_value = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"
    acquired = False
    start_time = time.monotonic()
    
    try:
        # Try to acquire lock with retries
        while time.monotonic() - start_time < wait_seconds:
            try:
                # SET NX EX: set if not exists with expiration
                result = await _redis_client.set(
                    lock_key,
                    lock_value,
                    nx=True,
                    ex=ttl_seconds,
                )
                if result:
                    acquired = True
                    logger.debug("[LOCK_ACQUIRED] key=%s ttl=%s", key, ttl_seconds)
                    break
            except Exception as exc:
                logger.warning("[LOCK_ACQUIRE_ERROR] key=%s error=%s", key, exc)
                break
            
            # Wait before retry
            await asyncio.sleep(retry_interval)
        
        if not acquired:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning("[LOCK_TIMEOUT] key=%s wait_ms=%s", key, elapsed_ms)
        
        yield acquired
        
    finally:
        # Release lock only if we acquired it
        if acquired:
            try:
                # Use Lua script for atomic check-and-delete
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                await _redis_client.eval(lua_script, 1, lock_key, lock_value)
                logger.debug("[LOCK_RELEASED] key=%s", key)
            except Exception as exc:
                logger.warning("[LOCK_RELEASE_ERROR] key=%s error=%s", key, exc)


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
            logger.info("[DISTRIBUTED_LOCK] redis_connection_closed")
        except Exception as exc:
            logger.warning("[DISTRIBUTED_LOCK] redis_close_error=%s", exc)
        finally:
            _redis_client = None


def get_lock_mode() -> str:
    """Return current lock mode: 'redis' or 'single-instance'."""
    if _redis_available:
        return "redis"
    return "single-instance"


def is_redis_available() -> bool:
    """Check if Redis is available for distributed locking."""
    return _redis_available
