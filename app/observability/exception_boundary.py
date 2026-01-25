from __future__ import annotations

import json
import logging
import time
import traceback
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.observability.error_buffer import record_error_summary
from app.observability.trace import ensure_correlation_id
from app.observability.no_silence_guard import track_outgoing_action

logger = logging.getLogger(__name__)


def _mask_callback_data(callback_data: Optional[str]) -> Optional[str]:
    if not callback_data:
        return None
    base = callback_data.split(":", 1)[0]
    masked = f"{base}:…" if base != callback_data else base
    return masked[:32] + ("…" if len(masked) > 32 else "")


def _guess_stage(error: BaseException) -> str:
    tb = traceback.extract_tb(error.__traceback__) if error.__traceback__ else []
    for frame in tb:
        lowered = f"{frame.filename}:{frame.name}".lower()
        if "router" in lowered:
            return "router"
        if "storage" in lowered or "db" in lowered:
            return "storage"
        if "api" in lowered or "client" in lowered:
            return "api"
    return "handler"


def _guess_handler(error: BaseException) -> Optional[str]:
    tb = traceback.extract_tb(error.__traceback__) if error.__traceback__ else []
    if not tb:
        return None
    return tb[-1].name


def _compact_traceback(error: BaseException, limit: int = 6) -> str:
    try:
        entries = traceback.format_exception(type(error), error, error.__traceback__)
    except Exception:
        return ""
    trimmed = entries[-limit:] if len(entries) > limit else entries
    return "".join(trimmed).strip()


def _update_type(update: Any) -> str:
    if isinstance(update, Update):
        if update.callback_query:
            return "callback_query"
        if update.message:
            return "message"
    return "unknown"


def _safe_state(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    if not context:
        return None
    for key in ("state", "waiting_for", "current_state"):
        value = context.user_data.get(key) if context.user_data else None
        if value:
            return str(value)
    return None


def _build_main_menu_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    if user_lang == "en":
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Models", callback_data="show_models")],
                [InlineKeyboardButton("Balance / Payment", callback_data="check_balance")],
                [InlineKeyboardButton("Help", callback_data="help_menu")],
                [InlineKeyboardButton("Profile", callback_data="my_generations")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Модели", callback_data="show_models")],
            [InlineKeyboardButton("Баланс / Оплата", callback_data="check_balance")],
            [InlineKeyboardButton("Помощь", callback_data="help_menu")],
            [InlineKeyboardButton("Профиль", callback_data="my_generations")],
        ]
    )


async def handle_update_exception(
    update: Any,
    context: ContextTypes.DEFAULT_TYPE,
    error: BaseException,
    *,
    stage: Optional[str] = None,
    handler: Optional[str] = None,
    partner_id: Optional[str] = None,
) -> str:
    if not partner_id:
        import os

        partner_id = (
            os.getenv("BOT_INSTANCE_ID", "").strip()
            or os.getenv("PARTNER_ID", "").strip()
            or None
        )
    correlation_id = ensure_correlation_id(update, context)
    update_id = update.update_id if isinstance(update, Update) else None
    callback_data = None
    if isinstance(update, Update) and update.callback_query:
        callback_data = update.callback_query.data

    if stage:
        stage_final = stage
    elif isinstance(update, Update) and update.callback_query:
        stage_final = "router"
    else:
        stage_final = _guess_stage(error)
    handler_final = handler or _guess_handler(error)
    masked_callback = _mask_callback_data(callback_data)
    state = _safe_state(context)

    payload = {
        "correlation_id": correlation_id,
        "update_id": update_id,
        "update_type": _update_type(update),
        "handler": handler_final,
        "callback": masked_callback,
        "state": state,
        "partner_id": partner_id,
        "stage": stage_final,
        "error_class": type(error).__name__,
        "error": str(error)[:200],
        "trace": f"{type(error).__name__}: {str(error)[:120]}",
        "stack": _compact_traceback(error),
    }
    logger.info("ROUTER_FAIL %s", json.dumps(payload, ensure_ascii=False, default=str))
    logger.debug("ROUTER_FAIL trace", exc_info=error)

    record_error_summary(
        {
            "correlation_id": correlation_id,
            "stage": stage_final,
            "handler": handler_final,
            "error_class": type(error).__name__,
            "timestamp": int(time.time()),
        }
    )

    user_lang = "ru"
    if isinstance(update, Update) and update.effective_user:
        user_lang = update.effective_user.language_code or "ru"
    menu_keyboard = _build_main_menu_keyboard("en" if user_lang.lower().startswith("en") else "ru")
    user_message = (
        "⚠️ Временный сбой, вернул в меню."
        f" Лог: {correlation_id}."
    )

    if isinstance(update, Update) and update.callback_query:
        try:
            await update.callback_query.answer("⚠️ Техническая ошибка", show_alert=False)
            if update_id:
                track_outgoing_action(update_id)
        except Exception:
            logger.debug("ROUTER_FAIL callback answer failed", exc_info=True)
        try:
            chat_id = update.callback_query.message.chat_id if update.callback_query.message else None
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=user_message, reply_markup=menu_keyboard)
                if update_id:
                    track_outgoing_action(update_id)
        except Exception:
            logger.debug("ROUTER_FAIL message send failed", exc_info=True)
        try:
            from bot_kie import ensure_main_menu

            await ensure_main_menu(
                update,
                context,
                source="router_exception",
                correlation_id=correlation_id,
                prefer_edit=False,
            )
        except Exception:
            logger.debug("ROUTER_FAIL ensure_main_menu failed", exc_info=True)
        return correlation_id

    if isinstance(update, Update) and update.message:
        try:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=user_message,
                reply_markup=menu_keyboard,
            )
            if update_id:
                track_outgoing_action(update_id)
        except Exception:
            logger.debug("ROUTER_FAIL message send failed", exc_info=True)
        try:
            from bot_kie import ensure_main_menu

            await ensure_main_menu(
                update,
                context,
                source="router_exception",
                correlation_id=correlation_id,
                prefer_edit=False,
            )
        except Exception:
            logger.debug("ROUTER_FAIL ensure_main_menu failed", exc_info=True)

    return correlation_id


async def handle_unknown_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    callback_data: Optional[str],
    *,
    partner_id: Optional[str] = None,
) -> str:
    if not partner_id:
        import os

        partner_id = (
            os.getenv("BOT_INSTANCE_ID", "").strip()
            or os.getenv("PARTNER_ID", "").strip()
            or None
        )
    correlation_id = ensure_correlation_id(update, context)
    masked_callback = _mask_callback_data(callback_data)
    payload = {
        "correlation_id": correlation_id,
        "update_id": update.update_id if update else None,
        "update_type": "callback_query",
        "handler": "unknown_callback",
        "callback": masked_callback,
        "state": _safe_state(context),
        "partner_id": partner_id,
        "stage": "router",
        "error_class": "UnknownCallback",
        "error": "unhandled_callback",
        "trace": "unknown_callback",
    }
    logger.warning("UNKNOWN_CALLBACK %s", json.dumps(payload, ensure_ascii=False, default=str))

    record_error_summary(
        {
            "correlation_id": correlation_id,
            "stage": "router",
            "handler": "unknown_callback",
            "error_class": "UnknownCallback",
            "timestamp": int(time.time()),
        }
    )
    return correlation_id
