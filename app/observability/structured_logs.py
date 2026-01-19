"""
Structured logging helpers for UX/diagnostics contract.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from app.observability.trace import get_correlation_id as get_trace_correlation_id
from app.observability.context import get_context_fields

logger = logging.getLogger(__name__)


def get_correlation_id(update_id: Optional[int], user_id: Optional[int]) -> str:
    """Generate a correlation_id if not provided."""
    base = f"{update_id or 'na'}-{user_id or 'na'}"
    return f"corr-{base}-{uuid.uuid4().hex[:8]}"


def build_action_path(callback_data: Optional[str]) -> str:
    """Build a basic breadcrumb path from callback_data."""
    if not callback_data:
        return "menu>unknown"
    if ":" in callback_data:
        prefix = callback_data.split(":", 1)[0]
        return f"menu>{prefix}"
    return f"menu>{callback_data}"


def log_structured_event(**fields: Any) -> None:
    """Emit a structured log line as JSON."""
    correlation_id = fields.get("correlation_id") or get_trace_correlation_id()
    context_fields = get_context_fields()
    payload = {
        "correlation_id": correlation_id,
        "user_id": fields.get("user_id") or context_fields.get("user_id"),
        "chat_id": fields.get("chat_id") or context_fields.get("chat_id"),
        "update_id": fields.get("update_id") or context_fields.get("update_id"),
        "update_type": fields.get("update_type") or context_fields.get("update_type"),
        "action": fields.get("action"),
        "action_path": fields.get("action_path"),
        "command": fields.get("command"),
        "callback_data": fields.get("callback_data"),
        "model_id": fields.get("model_id"),
        "gen_type": fields.get("gen_type"),
        "task_id": fields.get("task_id"),
        "job_id": fields.get("job_id"),
        "stage": fields.get("stage"),
        "waiting_for": fields.get("waiting_for"),
        "param": fields.get("param"),
        "outcome": fields.get("outcome"),
        "duration_ms": fields.get("duration_ms"),
        "error_id": fields.get("error_id"),
        "error_code": fields.get("error_code"),
        "fix_hint": fields.get("fix_hint"),
    }
    logger.info("STRUCTURED_LOG %s", json.dumps(payload, ensure_ascii=False, default=str))
