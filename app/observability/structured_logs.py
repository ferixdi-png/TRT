"""
Structured logging helpers for UX/diagnostics contract.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from app.observability.trace import get_correlation_id as get_trace_correlation_id
from app.observability.context import get_context_fields
from app.observability.correlation_store import note_missing_ids, register_ids, resolve_correlation_ids

logger = logging.getLogger(__name__)

_PRE_CREATE_OUTCOMES = {"start", "request", "received", "locked_wait"}
_TERMINAL_FAILURE_OUTCOMES = {"failed", "error", "blocked", "canceled", "cancelled", "timeout"}
_STAGES_REQUIRING_IDS = {
    "KIE_POLL",
    "KIE_PARSE",
    "TG_DELIVER",
    "DELIVERY_PENDING",
    "DELIVERY_POLL",
    "TASK_LIFECYCLE",
    "GEN_COMPLETE",
}
_ACTIONS_REQUIRING_IDS = {
    "TG_DELIVER",
    "RESULT_DELIVERED",
    "DELIVERY_SEND_OK",
    "DELIVERY_SEND_FAIL",
    "DELIVERY_PENDING",
    "TASK_LIFECYCLE",
    "KIE_POLL",
    "KIE_PARSE",
}


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


def _requires_ids(stage: Optional[str], action: Optional[str], outcome: Optional[str]) -> bool:
    outcome_l = (outcome or "").lower()
    if outcome_l in _PRE_CREATE_OUTCOMES:
        return False
    if stage in _STAGES_REQUIRING_IDS or action in _ACTIONS_REQUIRING_IDS:
        return True
    if stage == "KIE_CREATE" and outcome_l not in _PRE_CREATE_OUTCOMES:
        return True
    return False


def log_structured_event(**fields: Any) -> None:
    """Emit a structured log line as JSON."""
    request_id = fields.get("request_id")
    correlation_id = fields.get("correlation_id") or get_trace_correlation_id()
    skip_correlation_store = bool(fields.get("skip_correlation_store"))
    if fields.get("stage") == "BOOT":
        skip_correlation_store = True
    resolved_ids = resolve_correlation_ids(
        correlation_id=correlation_id,
        request_id=request_id,
        task_id=fields.get("task_id"),
        job_id=fields.get("job_id"),
    )
    correlation_id = resolved_ids.get("correlation_id") or correlation_id
    request_id = resolved_ids.get("request_id") or request_id or correlation_id
    task_id = resolved_ids.get("task_id") or fields.get("task_id")
    job_id = resolved_ids.get("job_id") or fields.get("job_id")
    context_fields = get_context_fields()
    outcome = fields.get("outcome")
    action = fields.get("action")
    stage = fields.get("stage")
    param = fields.get("param")

    if not skip_correlation_store:
        register_ids(
            correlation_id=correlation_id,
            request_id=request_id,
            task_id=task_id,
            job_id=job_id,
            user_id=fields.get("user_id") or context_fields.get("user_id"),
            model_id=fields.get("model_id"),
            source="structured_logs",
        )

    if not skip_correlation_store and _requires_ids(stage, action, outcome):
        missing_ids = {name for name, value in {"task_id": task_id, "job_id": job_id}.items() if not value}
        if missing_ids:
            reason = "missing_required_ids_after_create"
            outcome_l = (outcome or "").lower()
            if outcome_l not in _TERMINAL_FAILURE_OUTCOMES and outcome_l != "partial":
                outcome = "partial"
            if isinstance(param, dict):
                partial_reason = {
                    "reason": reason,
                    "missing_ids": sorted(missing_ids),
                }
                existing_partial = param.get("partial_reason")
                if isinstance(existing_partial, dict):
                    existing_missing = set(existing_partial.get("missing_ids") or [])
                    existing_partial["missing_ids"] = sorted(existing_missing.union(missing_ids))
                    existing_partial.setdefault("reason", reason)
                else:
                    param["partial_reason"] = partial_reason
            elif param is None:
                param = {"partial_reason": {"reason": reason, "missing_ids": sorted(missing_ids)}}
            note_missing_ids(
                correlation_id=correlation_id,
                request_id=request_id,
                action=action,
                stage=stage,
                missing_ids=missing_ids,
                reason=reason,
            )

    payload = {
        "correlation_id": correlation_id,
        "request_id": request_id,
        "timestamp_ms": int(time.time() * 1000),
        "user_id": fields.get("user_id") or context_fields.get("user_id"),
        "chat_id": fields.get("chat_id") or context_fields.get("chat_id"),
        "update_id": fields.get("update_id") or context_fields.get("update_id"),
        "update_type": fields.get("update_type") or context_fields.get("update_type"),
        "action": fields.get("action"),
        "action_path": fields.get("action_path"),
        "command": fields.get("command"),
        "callback_data": fields.get("callback_data"),
        "message_type": fields.get("message_type"),
        "text_length": fields.get("text_length"),
        "text_hash": fields.get("text_hash"),
        "text_preview": fields.get("text_preview"),
        "model_id": fields.get("model_id"),
        "gen_type": fields.get("gen_type"),
        "task_id": task_id,
        "job_id": job_id,
        "sku_id": fields.get("sku_id"),
        "price_rub": fields.get("price_rub"),
        "stage": stage,
        "waiting_for": fields.get("waiting_for"),
        "param": fields.get("param"),
        "outcome": outcome,
        "duration_ms": fields.get("duration_ms"),
        "lock_key": fields.get("lock_key"),
        "lock_wait_ms_total": fields.get("lock_wait_ms_total"),
        "lock_attempts": fields.get("lock_attempts"),
        "lock_ttl_s": fields.get("lock_ttl_s"),
        "lock_acquired": fields.get("lock_acquired"),
        "poll_attempt": fields.get("poll_attempt"),
        "poll_latency_ms": fields.get("poll_latency_ms"),
        "total_wait_ms": fields.get("total_wait_ms"),
        "retry_count": fields.get("retry_count"),
        "task_state": fields.get("task_state"),
        "dedup_hit": fields.get("dedup_hit"),
        "existing_task_id": fields.get("existing_task_id"),
        "error_id": fields.get("error_id"),
        "error_code": fields.get("error_code"),
        "fix_hint": fields.get("fix_hint"),
        "abuse_id": fields.get("abuse_id"),
    }
    payload["param"] = param
    logger.info("STRUCTURED_LOG %s", json.dumps(payload, ensure_ascii=False, default=str))


def log_critical_event(
    *,
    correlation_id: Optional[str],
    update_id: Optional[int],
    stage: str,
    latency_ms: Optional[float],
    retry_after: Optional[float],
    timeout_s: Optional[float],
    attempt: Optional[int],
) -> None:
    """Emit a critical event line with a unified key-value format."""
    logger.warning(
        "CRIT_EVENT correlation_id=%s update_id=%s stage=%s latency_ms=%s retry_after=%s timeout_s=%s attempt=%s",
        correlation_id or "na",
        update_id,
        stage,
        f"{latency_ms:.1f}" if isinstance(latency_ms, (int, float)) else latency_ms,
        retry_after,
        timeout_s,
        attempt,
    )
