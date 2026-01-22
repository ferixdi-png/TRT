"""Single-instance advisory lock (in-memory fallback)."""
from __future__ import annotations

import os
import time
import threading

_lock = threading.Lock()
_lock_holder_pid: int | None = None
_lock_acquired_at: float | None = None
_lock_takeover_event: str | None = None
_lock_key = int(os.getenv("SINGLETON_LOCK_KEY", "76473"))


def acquire_single_instance_lock() -> bool:
    global _lock_holder_pid, _lock_acquired_at, _lock_takeover_event
    acquired = _lock.acquire(blocking=False)
    if acquired:
        _lock_holder_pid = os.getpid()
        _lock_acquired_at = time.time()
        _lock_takeover_event = "acquired"
    return acquired


def release_single_instance_lock() -> None:
    global _lock_holder_pid, _lock_acquired_at, _lock_takeover_event
    if _lock.locked():
        _lock.release()
    _lock_holder_pid = None
    _lock_acquired_at = None
    _lock_takeover_event = "released"


def get_lock_debug_info() -> dict:
    now = time.time()
    idle_duration = None
    if _lock_acquired_at is not None:
        idle_duration = max(0.0, now - _lock_acquired_at)
    return {
        "holder_pid": _lock_holder_pid,
        "idle_duration": idle_duration,
        "heartbeat_age": idle_duration,
        "takeover_event": _lock_takeover_event,
    }


def get_lock_key() -> int:
    return _lock_key
