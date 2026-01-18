"""In-memory job storage for UX flows and tests."""
from __future__ import annotations

from typing import Any, Dict, Optional


class JobStorage:
    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(self, job_id: str, payload: Dict[str, Any]) -> None:
        self._jobs[job_id] = dict(payload)

    def update_job(self, job_id: str, **updates: Any) -> None:
        if job_id not in self._jobs:
            raise KeyError(f"Job {job_id} not found")
        self._jobs[job_id].update(updates)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)
