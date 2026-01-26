"""
Distributed lock implementation via Redis for multi-instance scaling.
Falls back to single-instance mode if Redis is not available.
"""

import asyncio
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional
import uuid

logger = logging.getLogger(__name__)

_redis_client: Optional[any] = None
_redis_available: bool = False
_redis_initialized: bool = False
_tenant_default_warned: bool = False


def _read_float_env(name: str, default: float, *, min_value: float = 0.1, max_value: float = 10.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value.strip())
    except ValueError:
        logger.warning("Invalid %s value '%s', defaulting to %s", name, raw_value, default)
        return default
    return max(min_value, min(max_value, value))


@dataclass(frozen=True)
class LockResult:
    acquired: bool
    wait_ms_total: int
    attempts: int
    ttl_seconds: int
    key: str

    def __bool__(self) -> bool:
        return self.acquired


def build_tenant_lock_key(key: str) -> str:
    bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip() or os.getenv("PARTNER_ID", "").strip()
    if not bot_instance_id:
        bot_instance_id = "default"
        global _tenant_default_warned
        if not _tenant_default_warned:
            _tenant_default_warned = True
            logger.warning("[DISTRIBUTED_LOCK] tenant_defaulted=true tenant=%s", bot_instance_id)
    prefix = f"tenant:{bot_instance_id}:"
    if key.startswith(prefix):
        return key
    return f"{prefix}{key}"


def build_redis_lock_key(key: str) -> str:
    return f"lock:{build_tenant_lock_key(key)}"


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

    connect_timeout = _read_float_env("REDIS_CONNECT_TIMEOUT_SECONDS", 1.0, min_value=0.2, max_value=5.0)
    read_timeout = _read_float_env("REDIS_READ_TIMEOUT_SECONDS", 1.0, min_value=0.2, max_value=5.0)
    connect_deadline = _read_float_env(
        "REDIS_CONNECT_DEADLINE_SECONDS",
        max(connect_timeout, read_timeout),
        min_value=0.3,
        max_value=6.0,
    )
    
    try:
        import redis.asyncio as redis
        _redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=connect_timeout,
            socket_timeout=read_timeout,
        )
        # Test connection
        await asyncio.wait_for(_redis_client.ping(), timeout=connect_deadline)
        _redis_available = True
        logger.info("[DISTRIBUTED_LOCK] mode=redis url=%s", redis_url.split("@")[-1] if "@" in redis_url else "configured")
        return True
    except ImportError:
        logger.warning("[DISTRIBUTED_LOCK] mode=single-instance reason=redis_module_missing")
        _redis_available = False
        return False
    except asyncio.TimeoutError:
        logger.warning("[DISTRIBUTED_LOCK] mode=single-instance reason=redis_connect_timeout")
        _redis_available = False
    except Exception as exc:
        logger.warning("[DISTRIBUTED_LOCK] mode=single-instance reason=redis_connect_failed error=%s", exc)
        _redis_available = False
    if _redis_client:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None
    return False


async def get_redis_client() -> Optional[any]:
    await _init_redis()
    if not _redis_available:
        return None
    return _redis_client


@asynccontextmanager
async def distributed_lock(
    key: str,
    ttl_seconds: int = 10,
    wait_seconds: float = 2.0,
    retry_interval: float = 0.1,
    max_attempts: int = 3,
    backoff_base: float = 0.2,
    backoff_cap: float = 2.0,
    jitter: float = 0.15,
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
        yield LockResult(
            acquired=True,
            wait_ms_total=0,
            attempts=1,
            ttl_seconds=ttl_seconds,
            key=key,
        )
        return
    
    lock_key = build_redis_lock_key(key)
    lock_value = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"
    acquired = False
    start_time = time.monotonic()
    attempts = 0
    
    try:
        # Try to acquire lock with retries
        while attempts < max_attempts and time.monotonic() - start_time < wait_seconds:
            attempts += 1
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
            
            remaining = wait_seconds - (time.monotonic() - start_time)
            if remaining <= 0:
                break
            # Wait before retry with backoff + jitter
            if attempts >= max_attempts:
                break
            backoff = min(backoff_base * (2 ** (attempts - 1)), backoff_cap)
            sleep_for = min(
                remaining,
                max(retry_interval, backoff + random.uniform(0, jitter)),
            )
            await asyncio.sleep(sleep_for)
        
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        if not acquired:
            logger.warning(
                "[LOCK_TIMEOUT] key=%s wait_ms=%s attempts=%s ttl_s=%s",
                key,
                elapsed_ms,
                attempts,
                ttl_seconds,
            )
        yield LockResult(
            acquired=acquired,
            wait_ms_total=elapsed_ms,
            attempts=max(attempts, 1),
            ttl_seconds=ttl_seconds,
            key=key,
        )
        
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
