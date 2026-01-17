"""
Singleton lock utilities for preventing multiple bot instances.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Global state for lock acquisition
_lock_acquired = False
_lock_strict_mode = os.getenv("SINGLETON_LOCK_STRICT", "0").lower() in ("1", "true", "yes")


def _locks_disabled() -> bool:
    storage_mode = os.getenv("STORAGE_MODE", "github").lower()
    disabled = os.getenv("DISABLE_DB_LOCKS", "1").lower() in ("1", "true", "yes")
    return disabled or storage_mode == "github"

# Module-global SingletonLock instance
_singleton_lock_instance = None


def is_lock_acquired() -> bool:
    """Check if singleton lock was acquired."""
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
    if _lock_acquired:
        return "active"
    return "passive"


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
    
    if _locks_disabled():
        logger.info("[LOCK] singleton_disabled=true reason=db_disabled")
        return False

    try:
        from app.locking.single_instance import SingletonLock

        _singleton_lock_instance = SingletonLock(dsn)
        result = await _singleton_lock_instance.acquire()
        return result
    except Exception as e:
        logger.error(f"Failed to acquire singleton lock: {e}")
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


# Explicit export for importlib compatibility
__all__ = [
    'is_lock_acquired',
    'set_lock_acquired',
    'is_strict_mode',
    'should_exit_on_lock_conflict',
    'get_safe_mode',
    'acquire_singleton_lock',
    'release_singleton_lock'
]
