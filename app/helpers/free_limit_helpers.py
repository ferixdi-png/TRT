"""Simple free-limit helpers for tests and lightweight usage."""
from __future__ import annotations

from typing import Dict

from app.pricing.free_policy import get_free_daily_limit

_COUNTERS: Dict[int, int] = {}


def get_free_counter(user_id: int) -> int:
    """Return remaining free generations for a user."""
    default_limit = int(get_free_daily_limit())
    return int(_COUNTERS.get(user_id, default_limit))


def consume_free_generation(user_id: int) -> bool:
    """Consume one free generation if available."""
    remaining = get_free_counter(user_id)
    if remaining <= 0:
        return False
    _COUNTERS[user_id] = remaining - 1
    return True


def reset_free_counters() -> None:
    """Reset in-memory free counters (used in tests)."""
    _COUNTERS.clear()
