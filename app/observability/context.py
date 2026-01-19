"""Context propagation for per-update observability fields."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional, Dict



_update_id_var: ContextVar[Optional[int]] = ContextVar("update_id", default=None)
_user_id_var: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
_chat_id_var: ContextVar[Optional[int]] = ContextVar("chat_id", default=None)
_update_type_var: ContextVar[Optional[str]] = ContextVar("update_type", default=None)


@dataclass(frozen=True)
class UpdateContext:
    correlation_id: Optional[str]
    update_id: Optional[int]
    user_id: Optional[int]
    chat_id: Optional[int]
    update_type: Optional[str]


def _resolve_update_type(update: Any) -> Optional[str]:
    if getattr(update, "callback_query", None):
        return "callback"
    if getattr(update, "message", None):
        return "message"
    if getattr(update, "edited_message", None):
        return "edited_message"
    if getattr(update, "inline_query", None):
        return "inline_query"
    return "unknown"


def set_update_context(update: Any, context: Any, *, correlation_id: Optional[str] = None) -> UpdateContext:
    """Populate contextvars for the current update."""
    from app.observability.trace import ensure_correlation_id, set_correlation_id
    update_id = getattr(update, "update_id", None)
    user_id = None
    if getattr(update, "effective_user", None):
        user_id = update.effective_user.id
    elif getattr(update, "callback_query", None) and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id

    chat_id = None
    if getattr(update, "effective_chat", None):
        chat_id = update.effective_chat.id
    elif getattr(update, "callback_query", None) and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id

    update_type = _resolve_update_type(update)

    resolved_corr = correlation_id or ensure_correlation_id(update, context)
    set_correlation_id(resolved_corr)

    _update_id_var.set(update_id)
    _user_id_var.set(user_id)
    _chat_id_var.set(chat_id)
    _update_type_var.set(update_type)

    return UpdateContext(
        correlation_id=resolved_corr,
        update_id=update_id,
        user_id=user_id,
        chat_id=chat_id,
        update_type=update_type,
    )


def get_update_context() -> UpdateContext:
    """Fetch the current update context from contextvars."""
    from app.observability.trace import get_correlation_id
    return UpdateContext(
        correlation_id=get_correlation_id(),
        update_id=_update_id_var.get(),
        user_id=_user_id_var.get(),
        chat_id=_chat_id_var.get(),
        update_type=_update_type_var.get(),
    )


def get_context_fields() -> Dict[str, Optional[Any]]:
    """Return context fields for log enrichment."""
    return {
        "update_id": _update_id_var.get(),
        "user_id": _user_id_var.get(),
        "chat_id": _chat_id_var.get(),
        "update_type": _update_type_var.get(),
    }
