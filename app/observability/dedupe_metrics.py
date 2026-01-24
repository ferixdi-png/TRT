"""In-memory metrics and alerting for dedupe orphan entries."""
from __future__ import annotations

from typing import Dict

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


_METRICS: Dict[str, int] = {
    "dedupe_orphan_count": 0,
}
_LAST_ALERTED_COUNT = 0


def record_orphan_count(count: int, *, alert_threshold: int) -> int:
    """Record orphan count and emit a growth alert when it increases past threshold."""
    global _LAST_ALERTED_COUNT
    count = max(0, int(count))
    previous = _METRICS.get("dedupe_orphan_count", 0)
    _METRICS["dedupe_orphan_count"] = count
    logger.info("METRIC_GAUGE name=dedupe_orphan_count value=%s delta=%s", count, count - previous)
    if count >= alert_threshold and count > _LAST_ALERTED_COUNT:
        growth = count - max(previous, _LAST_ALERTED_COUNT)
        logger.warning(
            "DEDUPE_ORPHAN_GROWTH_ALERT count=%s threshold=%s growth=%s",
            count,
            alert_threshold,
            growth,
        )
        _LAST_ALERTED_COUNT = count
    elif count < alert_threshold:
        _LAST_ALERTED_COUNT = 0
    return count


def metrics_snapshot() -> Dict[str, int]:
    return dict(_METRICS)


def reset_metrics() -> None:
    global _LAST_ALERTED_COUNT
    for key in _METRICS:
        _METRICS[key] = 0
    _LAST_ALERTED_COUNT = 0
