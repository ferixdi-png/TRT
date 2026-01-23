"""Helpers for task lifecycle structured logging."""
from __future__ import annotations

from typing import Optional, Dict, Any

from app.observability.structured_logs import log_structured_event


def log_task_lifecycle(
    *,
    state: str,
    user_id: Optional[int],
    task_id: Optional[str] = None,
    job_id: Optional[str] = None,
    model_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    source: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="TASK_LIFECYCLE",
        action_path=source or "task_lifecycle",
        model_id=model_id,
        task_id=task_id,
        job_id=job_id,
        stage="TASK_LIFECYCLE",
        outcome=state,
        param=detail or {"state": state},
    )
