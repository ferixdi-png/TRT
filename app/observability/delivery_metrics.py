"""In-memory delivery metrics tracking."""
from __future__ import annotations

from collections import deque
from typing import Deque, Optional

_PENDING_AGES: Deque[float] = deque(maxlen=2000)
_DELIVERY_RESULTS: Deque[bool] = deque(maxlen=2000)


def record_pending_age(age_seconds: float) -> None:
    if age_seconds < 0:
        return
    _PENDING_AGES.append(float(age_seconds))


def record_delivery_attempt(success: bool) -> None:
    _DELIVERY_RESULTS.append(bool(success))


def _percentile(values: Deque[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(percentile * (len(ordered) - 1)))))
    return ordered[k]


def pending_age_p95() -> Optional[float]:
    return _percentile(_PENDING_AGES, 0.95)


def deliver_success_rate() -> Optional[float]:
    if not _DELIVERY_RESULTS:
        return None
    total = len(_DELIVERY_RESULTS)
    success = sum(1 for value in _DELIVERY_RESULTS if value)
    return success / total if total else None


def metrics_snapshot() -> dict:
    return {
        "pending_age_p95": pending_age_p95(),
        "pending_samples": len(_PENDING_AGES),
        "deliver_success_rate": deliver_success_rate(),
        "delivery_samples": len(_DELIVERY_RESULTS),
    }
