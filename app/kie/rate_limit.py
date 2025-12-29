from __future__ import annotations

import asyncio
import hashlib
import time
from collections import deque


class SlidingWindowRateLimiter:
    """Simple async sliding-window limiter.

    Enforces up to `limit` acquisitions per `window_seconds`.
    Designed for account-wide API limits (per API key).
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = float(window_seconds)
        self._lock = asyncio.Lock()
        self._timestamps: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                cutoff = now - self.window_seconds
                while self._timestamps and self._timestamps[0] <= cutoff:
                    self._timestamps.popleft()

                if len(self._timestamps) < self.limit:
                    self._timestamps.append(now)
                    return

                # Need to wait until the oldest timestamp exits the window.
                wait_for = (self._timestamps[0] + self.window_seconds) - now

            if wait_for > 0:
                await asyncio.sleep(wait_for)


class KieAccountLimiter:
    """Global (process-wide) limiter keyed by API key."""

    _limiters: dict[str, SlidingWindowRateLimiter] = {}
    _global_lock = asyncio.Lock()

    @staticmethod
    def _key(api_key: str) -> str:
        # Avoid keeping raw keys in memory dict keys/logs.
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def for_key(cls, api_key: str, limit: int, window_seconds: float) -> SlidingWindowRateLimiter:
        k = cls._key(api_key)
        # Fast path
        limiter = cls._limiters.get(k)
        if limiter is not None:
            return limiter

        # Rare slow path (first time per key)
        # We can't `await` here, so create optimistically; duplicates are fine and will be GC'd.
        limiter = SlidingWindowRateLimiter(limit=limit, window_seconds=window_seconds)
        cls._limiters[k] = limiter
        return limiter
