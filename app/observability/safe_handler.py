"""Safe handler wrapper for Telegram handlers to prevent crashes."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional
from weakref import WeakSet

from telegram import Update
from telegram.ext import BaseHandler, ConversationHandler, ContextTypes

from app.observability.exception_boundary import handle_update_exception
from app.observability.trace import ensure_correlation_id

logger = logging.getLogger(__name__)

_wrapped_handlers: WeakSet[BaseHandler] = WeakSet()
_wrapped_handler_ids: set[int] = set()


def _resolve_handler_name(handler: BaseHandler) -> str:
    callback = getattr(handler, "callback", None)
    if callback is None:
        return handler.__class__.__name__
    return getattr(callback, "__name__", handler.__class__.__name__)


def _safe_callback(
    handler_name: str,
    callback: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]],
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]:
    async def _wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        try:
            return await callback(update, context)
        except Exception as exc:
            correlation_id = ensure_correlation_id(update, context)
            user_id = update.effective_user.id if isinstance(update, Update) and update.effective_user else None
            partner_id = None
            try:
                import os

                partner_id = (
                    os.getenv("BOT_INSTANCE_ID", "").strip()
                    or os.getenv("PARTNER_ID", "").strip()
                    or None
                )
            except Exception:
                partner_id = None

            callback_data = None
            if isinstance(update, Update) and update.callback_query:
                callback_data = update.callback_query.data
            model_id = None
            sku_id = None
            if context and getattr(context, "user_data", None):
                model_id = context.user_data.get("model_id") or context.user_data.get("selected_model_id")
                sku_id = context.user_data.get("sku_id")

            logger.exception(
                "SAFE_HANDLER_EXCEPTION handler=%s user_id=%s partner_id=%s model_id=%s sku_id=%s "
                "callback_data=%s correlation_id=%s",
                handler_name,
                user_id,
                partner_id,
                model_id,
                sku_id,
                callback_data,
                correlation_id,
            )
            try:
                await handle_update_exception(
                    update,
                    context,
                    exc,
                    stage="handler",
                    handler=handler_name,
                    partner_id=partner_id,
                )
            except Exception:
                logger.debug("SAFE_HANDLER_EXCEPTION boundary failed", exc_info=True)
            return None

    return _wrapped


def _is_wrapped(handler: BaseHandler) -> bool:
    if getattr(handler, "_safe_wrapped", False):
        return True
    if handler in _wrapped_handlers:
        return True
    return id(handler) in _wrapped_handler_ids


def _mark_wrapped(handler: BaseHandler) -> None:
    try:
        handler._safe_wrapped = True  # type: ignore[attr-defined]
        return
    except AttributeError:
        pass
    try:
        _wrapped_handlers.add(handler)
        return
    except TypeError:
        _wrapped_handler_ids.add(id(handler))


def _wrap_handler(handler: BaseHandler) -> None:
    if _is_wrapped(handler):
        return
    if isinstance(handler, ConversationHandler):
        for entry in handler.entry_points:
            _wrap_handler(entry)
        for state_handlers in handler.states.values():
            for entry in state_handlers:
                _wrap_handler(entry)
        for entry in handler.fallbacks:
            _wrap_handler(entry)
        _mark_wrapped(handler)
        return

    callback = getattr(handler, "callback", None)
    if not callback:
        _mark_wrapped(handler)
        return
    handler_name = _resolve_handler_name(handler)
    handler.callback = _safe_callback(handler_name, callback)  # type: ignore[assignment]
    _mark_wrapped(handler)


def install_safe_handler_wrapper(application: Any) -> None:
    if getattr(application, "_safe_handler_wrapper_installed", False):
        return
    original_add_handler = application.add_handler

    def _wrapped_add_handler(handler: BaseHandler, *args: Any, **kwargs: Any) -> Any:
        _wrap_handler(handler)
        return original_add_handler(handler, *args, **kwargs)

    application.add_handler = _wrapped_add_handler  # type: ignore[assignment]
    application._safe_handler_wrapper_installed = True
