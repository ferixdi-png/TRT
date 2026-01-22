"""
Singleton lock utilities for preventing multiple bot instances.
"""
import logging
import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Global state for lock acquisition
_lock_acquired = False
_lock_strict_mode = os.getenv("SINGLETON_LOCK_STRICT", "0").lower() in ("1", "true", "yes")
_lock_mode = "none"
_lock_degraded = False
_lock_degraded_reason: Optional[str] = None
_file_lock_handle = None
_file_lock_path: Optional[Path] = None
_no_db_warned = False
_pg_conn = None
_pg_lock_key: Optional[int] = None
_redis_client = None
_redis_lock_key: Optional[str] = None
_redis_lock_value: Optional[str] = None


def _is_production_env() -> bool:
    env_name = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
    return env_name in {"prod", "production"}


def _allow_file_fallback() -> bool:
    if os.getenv("SINGLETON_LOCK_ALLOW_FILE_FALLBACK", "").lower() in ("1", "true", "yes"):
        return True
    return not _is_production_env()


def _locks_disabled() -> bool:
    disabled = os.getenv("DISABLE_DB_LOCKS", "0").lower() in ("1", "true", "yes")
    return disabled

# Module-global SingletonLock instance
_singleton_lock_instance = None


def is_lock_acquired() -> bool:
    """Check if singleton lock was acquired."""
    if _locks_disabled():
        return True
    return _lock_acquired


def set_lock_acquired(acquired: bool):
    """Set lock acquisition status."""
    global _lock_acquired
    _lock_acquired = acquired


def is_strict_mode() -> bool:
    """Check if strict mode is enabled (exit on lock conflict)."""
    return _lock_strict_mode


def should_exit_on_lock_conflict() -> bool:
    """Determine if process should exit when lock cannot be acquired."""
    return _lock_strict_mode


def get_safe_mode() -> str:
    """
    Get safe mode status based on lock acquisition.
    
    Returns:
        "active" if lock acquired, "passive" if not acquired
    """
    if is_lock_acquired():
        return "active"
    return "passive"


def get_lock_mode() -> str:
    """Return current lock mode."""
    return _lock_mode


def is_lock_degraded() -> bool:
    """Return whether lock is in degraded mode."""
    return _lock_degraded


def get_lock_degradation_notice(lang: str = "ru") -> str:
    """Return a user-facing notice when running in degraded lock mode."""
    if not _lock_degraded:
        return ""
    reason = _lock_degraded_reason or "lock_degraded"
    if lang == "en":
        return (
            "⚠️ The service is running in a degraded mode. Some actions may be slower or require retry.\n"
            f"Reason: {reason}."
        )
    return (
        "⚠️ Сейчас сервис работает в режиме деградации. Возможны задержки или повторные попытки.\n"
        f"Причина: {reason}."
    )


def get_lock_admin_notice(lang: str = "ru") -> str:
    """Return a neutral lock status line for admins only."""
    if not _lock_degraded:
        return ""
    reason = _lock_degraded_reason or "lock_degraded"
    if reason == "LOCK_DISABLED_NO_DB":
        if lang == "en":
            return "ℹ️ Lock disabled (LOCK_DISABLED_NO_DB)."
        return "ℹ️ Блокировка отключена (LOCK_DISABLED_NO_DB)."
    if reason == "file_lock_fallback":
        if lang == "en":
            return "ℹ️ Local-only lock mode active."
        return "ℹ️ Локальный режим блокировки активен."
    if lang == "en":
        return f"ℹ️ Lock status: {reason}."
    return f"ℹ️ Статус блокировки: {reason}."


def _set_lock_state(mode: str, acquired: bool, reason: Optional[str] = None) -> None:
    global _lock_mode, _lock_degraded, _lock_degraded_reason
    _lock_mode = mode
    set_lock_acquired(acquired)
    if reason or not acquired:
        _lock_degraded = True
        _lock_degraded_reason = reason or "lock_not_acquired"
    else:
        _lock_degraded = False
        _lock_degraded_reason = None


def _get_file_lock_path() -> Path:
    lock_dir = Path(os.getenv("SINGLETON_LOCK_DIR", "/app/data"))
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("[LOCK] file_lock_dir_fallback=true reason=%s", exc)
        lock_dir = Path("/tmp")
        lock_dir.mkdir(parents=True, exist_ok=True)
    lock_name = os.getenv("SINGLETON_LOCK_NAME", "trt_webhook_singleton.lock")
    return lock_dir / lock_name


def _acquire_file_lock() -> bool:
    global _file_lock_handle, _file_lock_path
    if _file_lock_handle is not None:
        return True
    _file_lock_path = _get_file_lock_path()
    try:
        _file_lock_handle = open(_file_lock_path, "w")
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_file_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _file_lock_handle.write(f"{os.getpid()}:{time.time()}\n")
        _file_lock_handle.flush()
        logger.info("[LOCK] LOCK_MODE=file lock_path=%s", _file_lock_path)
        return True
    except Exception as exc:
        if _file_lock_handle:
            try:
                _file_lock_handle.close()
            except Exception:
                pass
        _file_lock_handle = None
        logger.warning("[LOCK] LOCK_MODE=file lock_acquire_failed=true reason=%s", exc)
        return False


def _derive_pg_lock_key() -> int:
    global _pg_lock_key
    if _pg_lock_key is not None:
        return _pg_lock_key
    seed = (
        os.getenv("PG_ADVISORY_LOCK_KEY")
        or os.getenv("PARTNER_ID")
        or os.getenv("BOT_INSTANCE_ID")
        or "trt_bot_lock"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    _pg_lock_key = int(digest[:8], 16) % 2147483647
    return _pg_lock_key

async def _acquire_redis_lock(redis_url: str, ttl_seconds: int = 30) -> bool:
    """Acquire lock using Redis SET NX EX."""
    global _redis_client, _redis_lock_key, _redis_lock_value
    try:
        import redis.asyncio as redis  # type: ignore
    except ImportError:
        logger.debug("[LOCK] redis not available, skipping redis lock")
        return False
    
    try:
        _redis_client = await redis.from_url(redis_url, decode_responses=True)
        _redis_lock_key = f"trt_bot_lock:{os.getenv('BOT_INSTANCE_ID', 'default')}"
        _redis_lock_value = f"{os.getpid()}:{time.time()}"
        
        acquired = await _redis_client.set(
            _redis_lock_key,
            _redis_lock_value,
            nx=True,
            ex=ttl_seconds
        )
        if acquired:
            logger.info("[LOCK] LOCK_MODE=redis lock_acquired=true ttl=%s", ttl_seconds)
            return True
        else:
            await _redis_client.close()
            _redis_client = None
            logger.warning("[LOCK] LOCK_MODE=redis lock_acquired=false reason=already_held")
            return False
    except Exception as exc:
        logger.error("[LOCK] LOCK_MODE=redis lock_acquire_failed=true reason=%s", exc)
        if _redis_client:
            try:
                await _redis_client.close()
            except Exception:
                pass
            _redis_client = None
        return False


async def _release_redis_lock() -> None:
    """Release Redis lock."""
    global _redis_client, _redis_lock_key, _redis_lock_value
    if _redis_client is None or _redis_lock_key is None:
        return
    try:
        # Use Lua script for atomic check-and-delete
        lua_script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
        await _redis_client.eval(lua_script, 1, _redis_lock_key, _redis_lock_value)
        logger.info("[LOCK] LOCK_MODE=redis lock_released=true")
    except Exception as exc:
        logger.error("[LOCK] LOCK_MODE=redis lock_release_failed=true reason=%s", exc)
    finally:
        if _redis_client:
            try:
                await _redis_client.close()
            except Exception:
                pass
            _redis_client = None


async def _acquire_postgres_lock(dsn: str) -> bool:
    global _pg_conn
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:
        # Gracefully skip postgres lock if driver not installed (avoid noisy warnings)
        logger.debug("[LOCK] LOCK_MODE=postgres skipped missing_asyncpg=true reason=%s", exc)
        return False

    try:
        conn = await asyncpg.connect(dsn)
        lock_key = _derive_pg_lock_key()
        acquired = await conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_key)
        if not acquired:
            await conn.close()
            logger.error(
                "[LOCK] LOCK_MODE=postgres lock_acquired=false lock_key=%s reason=pg_try_advisory_lock_failed",
                lock_key,
            )
            return False
        _pg_conn = conn
        logger.info("[LOCK] LOCK_MODE=postgres lock_acquired=true lock_key=%s", lock_key)
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("[LOCK] LOCK_MODE=postgres lock_acquire_failed=true reason=%s", exc)
        return False


async def _release_postgres_lock() -> None:
    global _pg_conn
    if _pg_conn is None:
        return
    lock_key = _derive_pg_lock_key()
    try:
        await _pg_conn.execute("SELECT pg_advisory_unlock($1)", lock_key)
        await _pg_conn.close()
        logger.info("[LOCK] LOCK_MODE=postgres lock_released=true lock_key=%s", lock_key)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("[LOCK] LOCK_MODE=postgres lock_release_failed=true reason=%s", exc)
    finally:
        _pg_conn = None


def _release_file_lock() -> None:
    global _file_lock_handle, _file_lock_path
    if _file_lock_handle is None:
        return
    try:
        if sys.platform != "win32":
            import fcntl

            fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_UN)
        _file_lock_handle.close()
        logger.info("[LOCK] LOCK_MODE=file lock_released=true path=%s", _file_lock_path)
    except Exception as exc:
        logger.error("[LOCK] LOCK_MODE=file lock_release_failed=true reason=%s", exc)
    finally:
        _file_lock_handle = None
        _file_lock_path = None


async def acquire_singleton_lock(dsn=None, *, require_lock: bool = False) -> bool:
    """
    Async function to acquire singleton lock.
    Creates SingletonLock instance and acquires lock.
    
    Args:
        dsn: Optional database connection string
        
    Returns:
        True if lock acquired, False otherwise
    """
    global _singleton_lock_instance
    
    # Redis first (primary for multi-instance)
    redis_url = os.getenv("REDIS_URL", "").strip() or None
    if _locks_disabled():
        _set_lock_state("disabled", True, reason="lock_disabled_by_env")
        logger.info("[LOCK] singleton_disabled=true reason=disabled_by_env")
        return True

    if redis_url:
        redis_acquired = await _acquire_redis_lock(redis_url)
        if redis_acquired:
            _set_lock_state("redis", True, reason=None)
            logger.info("[LOCK] LOCK_MODE=redis lock_acquired=true for multi-instance scaling")
            return True
        logger.warning("[LOCK] LOCK_MODE=redis lock_acquired=false reason=redis_lock_failed")

    # Fallback to file only in non-prod
    storage_mode = os.getenv("STORAGE_MODE", "auto").lower()
    if _allow_file_fallback():
        acquired = _acquire_file_lock()
        if acquired:
            _set_lock_state("file", True, reason="file_lock_fallback")
            logger.warning("[LOCK] LOCK_MODE=file fallback=true degraded=true storage_mode=%s", storage_mode)
            return True
        _set_lock_state("file", False, reason="file_lock_failed")
        return False

    logger.error("[LOCK] LOCK_MODE=none reason=redis_unavailable storage_mode=%s", storage_mode)
    _set_lock_state("none", False, reason="redis_unavailable")
    return False


async def release_singleton_lock() -> None:
    """
    Async function to release singleton lock.
    Releases lock if instance exists.
    """
    global _singleton_lock_instance
    
    if _locks_disabled():
        return

    if _singleton_lock_instance is not None:
        try:
            await _singleton_lock_instance.release()
        except Exception as e:
            logger.error(f"Failed to release singleton lock: {e}")
        finally:
            _singleton_lock_instance = None

    if _lock_mode == "redis":
        await _release_redis_lock()

    if _lock_mode == "postgres":
        await _release_postgres_lock()

    if _file_lock_handle is not None:
        _release_file_lock()


# Explicit export for importlib compatibility
__all__ = [
    'is_lock_acquired',
    'set_lock_acquired',
    'is_strict_mode',
    'should_exit_on_lock_conflict',
    'get_safe_mode',
    'get_lock_mode',
    'is_lock_degraded',
    'get_lock_degradation_notice',
    'acquire_singleton_lock',
    'release_singleton_lock'
]
