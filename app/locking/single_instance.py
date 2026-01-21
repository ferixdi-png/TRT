"""
Single instance locking (GitHub-only mode).
Uses file lock fallback from app.utils.singleton_lock.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from typing import Dict

from app.utils import singleton_lock as lock_utils

logger = logging.getLogger(__name__)

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _run_coro_sync(coro, *, label: str) -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = _executor.submit(lambda: asyncio.run(coro))
    try:
        return future.result()
    except Exception as exc:
        logger.error("LOCK_SYNC_CALL_FAILED label=%s error=%s", label, exc, exc_info=True)
        return False


class SingletonLock:
    """Compatibility wrapper around file-based singleton lock."""

    async def acquire(self, timeout: float = 5.0) -> bool:
        del timeout
        dsn = os.getenv("DATABASE_URL", "").strip() or None
        return await lock_utils.acquire_singleton_lock(dsn=dsn, require_lock=True)

    async def release(self) -> None:
        await lock_utils.release_singleton_lock()


def acquire_single_instance_lock() -> bool:
    dsn = os.getenv("DATABASE_URL", "").strip() or None
    if dsn:
        logger.info("🔒 DB lock requested (DATABASE_URL present)")
    else:
        logger.info("🔒 DB lock requested without DATABASE_URL (fallback allowed=%s)", lock_utils._allow_file_fallback())
    return _run_coro_sync(lock_utils.acquire_singleton_lock(dsn=dsn, require_lock=True), label="acquire")


def release_single_instance_lock() -> None:
    _run_coro_sync(lock_utils.release_singleton_lock(), label="release")


def is_lock_held() -> bool:
    return lock_utils.is_lock_acquired()


def get_lock_debug_info() -> Dict[str, str]:
    return {
        "mode": lock_utils.get_lock_mode(),
        "safe_mode": lock_utils.get_safe_mode(),
        "degraded": str(lock_utils.is_lock_degraded()).lower(),
    }
