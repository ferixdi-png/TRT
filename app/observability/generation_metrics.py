"""In-memory latency metrics for generation pipeline (p50/p95)."""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Optional


_WINDOW = 4000

_CREATE_LATENCIES: Deque[float] = deque(maxlen=_WINDOW)
_WAIT_LATENCIES: Deque[float] = deque(maxlen=_WINDOW)
_DELIVERY_LATENCIES: Deque[float] = deque(maxlen=_WINDOW)
_END_TO_END_LATENCIES: Deque[float] = deque(maxlen=_WINDOW)


def _percentile(values: Deque[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(percentile * (len(ordered) - 1)))))
    return ordered[index]


def _summary(values: Deque[float]) -> Dict[str, Optional[float]]:
    return {
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "samples": float(len(values)),
    }


def record_create_latency(latency_ms: Optional[float]) -> None:
    if latency_ms is None or latency_ms < 0:
        return
    _CREATE_LATENCIES.append(float(latency_ms))


def record_wait_latency(latency_ms: Optional[float]) -> None:
    if latency_ms is None or latency_ms < 0:
        return
    _WAIT_LATENCIES.append(float(latency_ms))


def record_delivery_latency(latency_ms: Optional[float]) -> None:
    if latency_ms is None or latency_ms < 0:
        return
    _DELIVERY_LATENCIES.append(float(latency_ms))


def record_end_to_end_latency(latency_ms: Optional[float]) -> None:
    if latency_ms is None or latency_ms < 0:
        return
    _END_TO_END_LATENCIES.append(float(latency_ms))


def metrics_snapshot() -> dict:
    return {
        "create_latency_ms": _summary(_CREATE_LATENCIES),
        "wait_latency_ms": _summary(_WAIT_LATENCIES),
        "delivery_latency_ms": _summary(_DELIVERY_LATENCIES),
        "end_to_end_latency_ms": _summary(_END_TO_END_LATENCIES),
    }


def reset_metrics() -> None:
    _CREATE_LATENCIES.clear()
    _WAIT_LATENCIES.clear()
    _DELIVERY_LATENCIES.clear()
    _END_TO_END_LATENCIES.clear()
