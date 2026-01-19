"""
Singleton lock utilities for preventing multiple bot instances.
"""
import logging
import os
import sys
import time
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


async def acquire_singleton_lock(dsn=None) -> bool:
    """
    Async function to acquire singleton lock.
    Creates SingletonLock instance and acquires lock.
    
    Args:
        dsn: Optional database connection string
        
    Returns:
        True if lock acquired, False otherwise
    """
    global _singleton_lock_instance
    
    if not dsn:
        global _no_db_warned
        storage_mode = os.getenv("STORAGE_MODE", "github").lower()
        if storage_mode == "github" or _locks_disabled():
            if not _no_db_warned:
                _no_db_warned = True
                logger.warning(
                    "[LOCK] error_code=LOCK_DISABLED_NO_DB mode=webhook storage_mode=%s",
                    storage_mode,
                )
            _set_lock_state("none", True, reason="LOCK_DISABLED_NO_DB")
            try:
                from app.observability.structured_logs import log_structured_event

                log_structured_event(
                    correlation_id=None,
                    action="SINGLETON_LOCK",
                    action_path="singleton_lock.acquire_singleton_lock",
                    stage="STARTUP",
                    waiting_for="LOCK",
                    outcome="skipped",
                    error_code="LOCK_DISABLED_NO_DB",
                    fix_hint="Set DATABASE_URL or enable DB storage if singleton lock is required.",
                )
            except Exception:
                pass
            return True
        logger.warning("[LOCK] LOCK_MODE=none reason=database_url_missing storage_mode=%s", storage_mode)
        _set_lock_state("none", False, reason="database_url_missing")
        return False

    if _locks_disabled():
        _set_lock_state("disabled", True, reason="lock_disabled_by_env")
        logger.info("[LOCK] singleton_disabled=true reason=disabled_by_env")
        return True

    try:
        from app.locking.single_instance import SingletonLock

        _singleton_lock_instance = SingletonLock(dsn)
        result = await _singleton_lock_instance.acquire()
        _set_lock_state("db", result, reason=None if result else "lock_not_acquired")
        return result
    except Exception as e:
        logger.error(f"Failed to acquire singleton lock: {e}")
        _set_lock_state("db", False, reason="lock_acquire_failed")
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
