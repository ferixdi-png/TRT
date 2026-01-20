"""Trace logging utilities for absolute traceability."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import traceback
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Dict, Optional
from collections.abc import MutableMapping

from app.observability.context import get_context_fields

logger = logging.getLogger(__name__)
_correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


@dataclass(frozen=True)
class TraceContext:
    correlation_id: str
    update_id: Optional[int]
    user_id: Optional[int]
    chat_id: Optional[int]
    update_type: Optional[str]


def set_correlation_id(correlation_id: Optional[str]) -> Token[Optional[str]]:
    """Store correlation id in a context-local variable."""
    return _correlation_id_var.set(correlation_id)


def reset_correlation_id(token: Token[Optional[str]]) -> None:
    """Reset correlation id context to previous token."""
    _correlation_id_var.reset(token)


def get_correlation_id() -> Optional[str]:
    """Fetch correlation id from the current context."""
    return _correlation_id_var.get()


def _get_env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _get_log_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)


def make_correlation_id(update: Any) -> str:
    """Generate a correlation id for the update."""
    update_id = getattr(update, "update_id", "na")
    user_id = None
    if getattr(update, "effective_user", None):
        user_id = update.effective_user.id
    elif getattr(update, "callback_query", None) and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id
    base = f"{update_id}-{user_id or 'na'}"
    return f"corr-{base}-{uuid.uuid4().hex[:8]}"


def ensure_correlation_id(update: Any, context: Any) -> str:
    """Get or create a correlation id stored in user/chat context for this update."""
    update_id = getattr(update, "update_id", None)
    user_id = None
    if getattr(update, "effective_user", None):
        user_id = update.effective_user.id
    elif getattr(update, "callback_query", None) and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id

    correlation_id = get_correlation_id()
    if context and isinstance(getattr(context, "user_data", None), MutableMapping):
        if context.user_data.get("correlation_update_id") == update_id:
            correlation_id = context.user_data.get("correlation_id")
        if correlation_id and context.user_data.get("correlation_id") != correlation_id:
            context.user_data["correlation_id"] = correlation_id
            context.user_data["correlation_update_id"] = update_id
        if not correlation_id:
            correlation_id = make_correlation_id(update)
            context.user_data["correlation_id"] = correlation_id
            context.user_data["correlation_update_id"] = update_id
    elif context and isinstance(getattr(context, "chat_data", None), MutableMapping):
        if context.chat_data.get("correlation_update_id") == update_id:
            correlation_id = context.chat_data.get("correlation_id")
        if correlation_id and context.chat_data.get("correlation_id") != correlation_id:
            context.chat_data["correlation_id"] = correlation_id
            context.chat_data["correlation_update_id"] = update_id
        if not correlation_id:
            correlation_id = make_correlation_id(update)
            context.chat_data["correlation_id"] = correlation_id
            context.chat_data["correlation_update_id"] = update_id
    if not correlation_id:
        correlation_id = make_correlation_id(update)
    return correlation_id


def prompt_summary(prompt: Optional[str]) -> Dict[str, Any]:
    if not prompt:
        return {"prompt_len": 0, "prompt_hash": None}
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    return {"prompt_len": len(prompt), "prompt_hash": digest}


def url_summary(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc or "unknown"
        trimmed = url.replace(domain, "")
        if len(trimmed) <= 20:
            return f"{domain}{trimmed}"
        return f"{domain}{trimmed[:10]}...{trimmed[-10:]}"
    except Exception:
        return url[:24]


def _sanitize_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    redacted_keys = {"telegram_bot_token", "kie_api_key", "authorization"}
    sanitized: Dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower() in redacted_keys:
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


def trace_event(level: str, correlation_id: str, stage: Optional[str] = None, **fields: Any) -> None:
    """Emit a structured trace event."""
    try:
        trace_verbose = _get_env_flag("TRACE_VERBOSE", "false")
        trace_payloads = _get_env_flag("TRACE_PAYLOADS", "false")
        trace_pricing = _get_env_flag("TRACE_PRICING", "false")
        log_level = _get_log_level(os.getenv("LOG_LEVEL", "INFO"))
        desired_level = _get_log_level(level)
        if desired_level < log_level:
            return

        if stage is None:
            stage = fields.pop("stage", None)
        else:
            fields.pop("stage", None)

        always_fields = set(fields.pop("always_fields", []))
        context_fields = get_context_fields()
        base_fields: Dict[str, Any] = {
            "correlation_id": correlation_id,
            "event": fields.get("event"),
            "stage": stage,
            "duration_ms": fields.get("duration_ms"),
            "update_id": fields.get("update_id") or context_fields.get("update_id"),
            "user_id": fields.get("user_id") or context_fields.get("user_id"),
            "chat_id": fields.get("chat_id") or context_fields.get("chat_id"),
            "update_type": fields.get("update_type") or context_fields.get("update_type"),
            "action": fields.get("action"),
            "action_path": fields.get("action_path"),
            "outcome": fields.get("outcome"),
        }

        extra_fields = {k: v for k, v in fields.items() if k not in base_fields}
        if not trace_payloads:
            payload_keys = {
                "payload",
                "input",
                "params",
                "result",
                "result_json",
                "raw_response",
                "response_payload",
            }
            extra_fields = {
                k: v
                for k, v in extra_fields.items()
                if k not in payload_keys and "payload" not in k.lower()
            }
        if not trace_pricing:
            extra_fields = {
                k: v
                for k, v in extra_fields.items()
                if all(token not in k.lower() for token in ("price", "pricing", "credits", "official_usd"))
            }
        payload = base_fields
        if trace_verbose:
            payload.update(extra_fields)
        elif always_fields:
            payload.update({k: v for k, v in extra_fields.items() if k in always_fields})
        payload = _sanitize_fields(payload)

        logger.log(desired_level, "TRACE %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception as exc:
        logger.warning("TRACE_EVENT_FAILED error=%s", exc, exc_info=True)


def trace_error(
    correlation_id: str,
    error_code: str,
    fix_hint: str,
    exc: BaseException,
    **fields: Any,
) -> None:
    """Emit a structured error trace entry."""
    debug_enabled = _get_env_flag("TRACE_VERBOSE", "false") or _get_log_level(os.getenv("LOG_LEVEL", "INFO")) <= logging.DEBUG
    context_fields = get_context_fields()
    payload = {
        "correlation_id": correlation_id,
        "event": "ERROR",
        "error_code": error_code,
        "fix_hint": fix_hint,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "update_id": fields.get("update_id") or context_fields.get("update_id"),
        "user_id": fields.get("user_id") or context_fields.get("user_id"),
        "chat_id": fields.get("chat_id") or context_fields.get("chat_id"),
    }
    payload.update(fields)
    if debug_enabled:
        payload["stacktrace"] = traceback.format_exc()
    payload = _sanitize_fields(payload)
    logger.error("TRACE_ERROR %s", json.dumps(payload, ensure_ascii=False, default=str))
