from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

_ERROR_BUFFER: Deque[Dict[str, Any]] = deque(maxlen=100)


def record_error_summary(summary: Dict[str, Any]) -> None:
    payload = summary.copy()
    payload.setdefault("timestamp", int(time.time()))
    _ERROR_BUFFER.append(payload)


def get_error_summary(correlation_id: str) -> Optional[Dict[str, Any]]:
    for item in reversed(_ERROR_BUFFER):
        if item.get("correlation_id") == correlation_id:
            return item
    return None


def get_last_errors(limit: int = 10) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    return list(_ERROR_BUFFER)[-limit:]
