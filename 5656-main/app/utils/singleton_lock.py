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
