"""Rate limiting and deduplication helpers."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Hashable, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: float, time_fn: Callable[[], float] | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn or time.monotonic
        self._entries: Dict[Hashable, float] = {}

    def _cleanup(self, now: float) -> None:
        expired = [key for key, ts in self._entries.items() if now - ts > self.ttl_seconds]
        for key in expired:
            self._entries.pop(key, None)

    def seen(self, key: Hashable) -> bool:
        now = self._time_fn()
        self._cleanup(now)
        if key in self._entries:
            return True
        self._entries[key] = now
        return False


@dataclass
class TokenBucket:
    rate: float
    capacity: float
    tokens: float
    updated_at: float
    time_fn: Callable[[], float]

    @classmethod
    def create(cls, rate: float, capacity: float, time_fn: Callable[[], float]) -> "TokenBucket":
        now = time_fn()
        return cls(rate=rate, capacity=capacity, tokens=capacity, updated_at=now, time_fn=time_fn)

    def consume(self, amount: float = 1.0) -> Tuple[bool, float]:
        now = self.time_fn()
        elapsed = max(0.0, now - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated_at = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0.0
        if self.rate <= 0:
            return False, float("inf")
        needed = amount - self.tokens
        return False, needed / self.rate


class PerUserRateLimiter:
    def __init__(self, rate: float, capacity: float, time_fn: Callable[[], float] | None = None) -> None:
        self.rate = rate
        self.capacity = capacity
        self._time_fn = time_fn or time.monotonic
        self._buckets: Dict[int, TokenBucket] = {}

    def check(self, user_id: int, amount: float = 1.0) -> Tuple[bool, float]:
        bucket = self._buckets.get(user_id)
        if bucket is None:
            bucket = TokenBucket.create(self.rate, self.capacity, self._time_fn)
            self._buckets[user_id] = bucket
        return bucket.consume(amount)


class PerKeyRateLimiter:
    def __init__(self, rate: float, capacity: float, time_fn: Callable[[], float] | None = None) -> None:
        self.rate = rate
        self.capacity = capacity
        self._time_fn = time_fn or time.monotonic
        self._buckets: Dict[Hashable, TokenBucket] = {}

    def check(self, key: Hashable, amount: float = 1.0) -> Tuple[bool, float]:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket.create(self.rate, self.capacity, self._time_fn)
            self._buckets[key] = bucket
        return bucket.consume(amount)
