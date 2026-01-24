"""Request-scoped JSON logging helpers for generation lifecycle."""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.observability.correlation_store import note_missing_ids, register_ids, resolve_correlation_ids

logger = logging.getLogger(__name__)

_PRE_CREATE_STATUSES = {"ui_received", "create_start", "create_failed", "dedupe_broken"}


def log_request_event(
    *,
    request_id: str,
    user_id: Optional[int],
    model: Optional[str],
    prompt_hash: Optional[str],
    status: str,
    latency_ms: Optional[int] = None,
    attempt: Optional[int] = None,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
    task_id: Optional[str] = None,
    job_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Emit a single-line JSON log for request tracking."""
    resolved_ids = resolve_correlation_ids(
        correlation_id=correlation_id,
        request_id=request_id,
        task_id=task_id,
        job_id=job_id,
    )
    correlation_id = resolved_ids.get("correlation_id") or correlation_id or request_id
    task_id = resolved_ids.get("task_id") or task_id
    job_id = resolved_ids.get("job_id") or job_id

    register_ids(
        correlation_id=correlation_id,
        request_id=request_id,
        task_id=task_id,
        job_id=job_id,
        user_id=user_id,
        model_id=model,
        source="request_logger",
    )

    missing_ids = {name for name, value in {"task_id": task_id, "job_id": job_id}.items() if not value}
    partial_reason = None
    status_l = (status or "").lower()
    if missing_ids and status_l not in _PRE_CREATE_STATUSES:
        partial_reason = {
            "reason": "missing_required_ids_after_create",
            "missing_ids": sorted(missing_ids),
        }
        note_missing_ids(
            correlation_id=correlation_id,
            request_id=request_id,
            action="REQUEST_LOGGER",
            stage=status,
            missing_ids=missing_ids,
            reason="missing_required_ids_after_create",
        )

    payload = {
        "request_id": request_id,
        "correlation_id": correlation_id,
        "user_id": user_id,
        "model": model,
        "prompt_hash": prompt_hash,
        "task_id": task_id,
        "job_id": job_id,
        "status": status,
        "latency_ms": latency_ms,
        "attempt": attempt,
        "error_code": error_code,
        "error_msg": error_msg,
    }
    if partial_reason:
        payload["outcome"] = "partial"
        payload["partial_reason"] = partial_reason
    logger.info(json.dumps(payload, ensure_ascii=False))
