"""Lightweight in-memory counters for update processing pipeline metrics."""
from __future__ import annotations

from typing import Dict

_metrics: Dict[str, int] = {
    "webhook_update_in": 0,
    "webhook_process_start": 0,
    "webhook_process_done": 0,
    "handler_enter": 0,
    "handler_exit": 0,
    "send_message": 0,
}


def increment_metric(name: str, value: int = 1) -> int:
    """Increment a known metric counter and return the new value."""
    _metrics[name] = _metrics.get(name, 0) + value
    return _metrics[name]


def get_metrics_snapshot() -> Dict[str, int]:
    """Return a copy of the metrics counters."""
    return dict(_metrics)


def reset_metrics() -> None:
    """Reset counters (intended for tests)."""
    for key in list(_metrics.keys()):
        _metrics[key] = 0
