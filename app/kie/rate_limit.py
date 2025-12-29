import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Dict, Any


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for a sliding-window rate limit."""

    max_requests: int
    per_seconds: float
    safety_margin: float = 0.05  # small buffer to avoid edge bursts


class SlidingWindowRateLimiter:
    """Async sliding-window rate limiter (in-process).

    This queues callers (awaits) instead of failing fast, which is exactly
    what we need for Kie: excess *new generation* requests are not queued
    server-side and will return 429.

    Note: This is process-local (Render typically runs 1 instance). If you
    scale to multiple instances, you'd want a shared limiter (Redis).
    """

    def __init__(self, cfg: RateLimitConfig, name: Optional[str] = None):
        self.cfg = cfg
        self.name = name or "rate_limiter"
        self._lock = asyncio.Lock()
        self._events: Deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.cfg.per_seconds
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._prune(now)

                if len(self._events) < self.cfg.max_requests:
                    self._events.append(now)
                    return

                oldest = self._events[0]
                wait_s = (oldest + self.cfg.per_seconds - now) + self.cfg.safety_margin

            wait_s = max(0.01, wait_s)
            # tiny jitter prevents stampedes when many coroutines wake together
            jitter = random.uniform(0, min(0.25, wait_s * 0.1))
            await asyncio.sleep(wait_s + jitter)

    def snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        self._prune(now)
        return {
            "name": self.name,
            "in_window": len(self._events),
            "max": self.cfg.max_requests,
            "window_s": self.cfg.per_seconds,
        }
