"""Request-scoped JSON logging helpers for generation lifecycle."""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
) -> None:
    """Emit a single-line JSON log for request tracking."""
    payload = {
        "request_id": request_id,
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
    logger.info(json.dumps(payload, ensure_ascii=False))
