"""In-memory request tracker for idempotent generation submissions."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


RequestKey = Tuple[int, str, str]


@dataclass
class RequestEntry:
    job_id: str
    task_id: Optional[str]
    created_ts: float


def build_request_key(user_id: int, model_id: str, prompt_hash: str) -> RequestKey:
    return (user_id, model_id, prompt_hash)


class RequestTracker:
    """Tracks recent generation requests to prevent duplicate submissions."""

    def __init__(self, ttl_seconds: int = 15, time_fn: Optional[Callable[[], float]] = None) -> None:
        self._ttl = ttl_seconds
        self._time_fn = time_fn or time.monotonic
        self._entries: Dict[RequestKey, RequestEntry] = {}

    def get(self, key: RequestKey) -> Optional[RequestEntry]:
        entry = self._entries.get(key)
        if not entry:
            return None
        if self._time_fn() - entry.created_ts > self._ttl:
            self._entries.pop(key, None)
            return None
        return entry

    def set(self, key: RequestKey, job_id: str, task_id: Optional[str] = None) -> RequestEntry:
        entry = RequestEntry(job_id=job_id, task_id=task_id, created_ts=self._time_fn())
        self._entries[key] = entry
        return entry

    def update_task_id(self, key: RequestKey, task_id: Optional[str]) -> None:
        entry = self._entries.get(key)
        if not entry:
            return
        self._entries[key] = RequestEntry(job_id=entry.job_id, task_id=task_id, created_ts=entry.created_ts)
