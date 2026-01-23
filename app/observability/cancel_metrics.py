"""Metrics counters for cancel/job lifecycle."""
from __future__ import annotations

from typing import Dict

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


_COUNTERS: Dict[str, int] = {
    "cancel_received_total": 0,
    "cancel_accepted_total": 0,
    "cancel_ignored_total": 0,
    "cancel_without_job_total": 0,
    "job_timeout_total": 0,
    "worker_restart_detected_total": 0,
}


def increment(metric: str, value: int = 1) -> int:
    """Increment a known metric counter and return the new value."""
    if metric not in _COUNTERS:
        logger.warning("METRIC_UNKNOWN name=%s", metric)
        _COUNTERS[metric] = 0
    _COUNTERS[metric] += value
    logger.info("METRIC_INCREMENT name=%s value=%s", metric, _COUNTERS[metric])
    return _COUNTERS[metric]


def get_metrics_snapshot() -> Dict[str, int]:
    """Return a copy of the metrics counters."""
    return dict(_COUNTERS)


def reset_metrics() -> None:
    """Reset counters (intended for tests)."""
    for key in _COUNTERS:
        _COUNTERS[key] = 0
