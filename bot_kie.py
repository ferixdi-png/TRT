"""
KIE (Knowledge Is Everything) Telegram Bot
Enhanced version with KIE AI model selection and generation
"""

from __future__ import annotations

import logging
import json
import asyncio
import concurrent.futures
import sys
import os
import re
import math
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Set

from app.observability.structured_logs import (
    build_action_path,
    get_correlation_id,
    log_structured_event,
)
from app.observability.no_silence_guard import track_outgoing_action
from app.observability.trace import (
    ensure_correlation_id,
    prompt_summary,
    trace_error,
    trace_event,
)
from app.observability.error_catalog import ERROR_CATALOG
from app.middleware.rate_limit import PerKeyRateLimiter, PerUserRateLimiter, TTLCache
from app.session_store import get_session_store, get_session_cached
# Enable logging FIRST (before any other imports that might log)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)
DEBUG_VERBOSE_LOGS = os.getenv("DEBUG_VERBOSE_LOGS", "0").lower() in ("1", "true", "yes")

# ==================== CALLBACK REGISTRY HELPERS ====================
KNOWN_CALLBACK_PREFIXES = (
    "category:",
    "gen_type:",
    "select_model:",
    "edit_param:",
    "set_param:",
    "confirm_param:",
    "sku:",
    "sk:",
    "model:",
    "modelk:",
    "select_mode:",
    "start:",
    "example:",
    "info:",
    "type_header:",
    "m:",
    "admin_gen_nav:",
    "admin_gen_view:",
    "admin_search:",
    "admin_add:",
    "admin_payments_back",
    "payment_screenshot_nav:",
    "admin_promocodes",
    "admin_broadcast",
    "admin_create_broadcast",
    "admin_broadcast_stats",
    "admin_test_ocr",
    "admin_user_mode",
    "admin_back_to_admin",
    "admin_user_info:",
    "admin_topup_user:",
    "topup_amount:",
    "pay_sbp:",
    "pay_card:",
    "pay_stars:",
    "gen_view:",
    "gen_repeat:",
    "gen_history:",
    "tutorial_step",
    "retry_generate:",
    "retry_delivery:",
)

KNOWN_CALLBACK_EXACT = {
    "show_models",
    "show_all_models_list",
    "other_models",
    "all_models",
    "free_tools",
    "check_balance",
    "copy_bot",
    "claim_gift",
    "help_menu",
    "support_contact",
    "admin_stats",
    "admin_view_generations",
    "admin_settings",
    "admin_set_currency_rate",
    "back_to_menu",
    "back_to_confirmation",
    "topup_balance",
    "topup_custom",
    "referral_info",
    "generate_again",
    "my_generations",
    "tutorial_start",
    "tutorial_complete",
    "confirm_generate",
    "show_parameters",
    "add_image",
    "skip_image",
    "image_done",
    "add_audio",
    "skip_audio",
    "reset_wizard",
    "reset_step",
    "cancel",
    "back_to_previous_step",
    "view_payment_screenshots",
}

SKIP_PARAM_VALUE = "__skip__"

MESSAGE_RATE_LIMIT_PER_SEC = float(os.getenv("TG_RATE_LIMIT_PER_SEC", "1.5"))
MESSAGE_RATE_LIMIT_BURST = float(os.getenv("TG_RATE_LIMIT_BURST", "5"))
CALLBACK_RATE_LIMIT_PER_SEC = float(os.getenv("TG_CALLBACK_RATE_LIMIT_PER_SEC", "2.0"))
CALLBACK_RATE_LIMIT_BURST = float(os.getenv("TG_CALLBACK_RATE_LIMIT_BURST", "6"))
CALLBACK_DATA_RATE_LIMIT_PER_SEC = float(os.getenv("TG_CALLBACK_DATA_RATE_LIMIT_PER_SEC", "1.0"))
CALLBACK_DATA_RATE_LIMIT_BURST = float(os.getenv("TG_CALLBACK_DATA_RATE_LIMIT_BURST", "2"))
UPDATE_DEDUP_TTL_SECONDS = float(os.getenv("TG_UPDATE_DEDUP_TTL_SECONDS", "60"))
CALLBACK_DEDUP_TTL_SECONDS = float(os.getenv("TG_CALLBACK_DEDUP_TTL_SECONDS", "30"))
CALLBACK_CONCURRENCY_LIMIT = int(os.getenv("TG_CALLBACK_CONCURRENCY_LIMIT", "8"))
CALLBACK_CONCURRENCY_TIMEOUT_SECONDS = float(os.getenv("TG_CALLBACK_CONCURRENCY_TIMEOUT_SECONDS", "2.0"))
STORAGE_IO_TIMEOUT_SECONDS = float(os.getenv("STORAGE_IO_TIMEOUT_SECONDS", "2.5"))

_message_rate_limiter = PerUserRateLimiter(MESSAGE_RATE_LIMIT_PER_SEC, MESSAGE_RATE_LIMIT_BURST)
_callback_rate_limiter = PerUserRateLimiter(CALLBACK_RATE_LIMIT_PER_SEC, CALLBACK_RATE_LIMIT_BURST)
_callback_data_rate_limiter = PerKeyRateLimiter(CALLBACK_DATA_RATE_LIMIT_PER_SEC, CALLBACK_DATA_RATE_LIMIT_BURST)
_update_deduper = TTLCache(UPDATE_DEDUP_TTL_SECONDS)
_callback_deduper = TTLCache(CALLBACK_DEDUP_TTL_SECONDS)
_callback_semaphore = asyncio.Semaphore(CALLBACK_CONCURRENCY_LIMIT) if CALLBACK_CONCURRENCY_LIMIT > 0 else None
KIE_CREDITS_CACHE_TTL_SECONDS = float(os.getenv("KIE_CREDITS_CACHE_TTL_SECONDS", "120"))
KIE_CREDITS_TIMEOUT_SECONDS = float(os.getenv("KIE_CREDITS_TIMEOUT_SECONDS", "2.0"))
_kie_credits_cache: Dict[str, Any] = {"timestamp": 0.0, "value": None}


def is_known_callback_data(callback_data: Optional[str]) -> bool:
    """Return True if callback data matches known routing patterns."""
    if not callback_data:
        return False
    if callback_data in KNOWN_CALLBACK_EXACT:
        return True
    return any(callback_data.startswith(prefix) for prefix in KNOWN_CALLBACK_PREFIXES)


def _truncate_log_value(value: Optional[str], limit: int = 160) -> Optional[str]:
    if not value:
        return value
    value = str(value)
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"


def _resolve_update_type(update: Update) -> str:
    if update.message:
        if update.message.text:
            return "text"
        if update.message.photo:
            return "photo"
        if update.message.audio or update.message.voice:
            return "audio"
        if update.message.document:
            return "document"
    return "unknown"


def _resolve_message_type(message: Optional[Any]) -> str:
    if not message:
        return "unknown"
    if getattr(message, "text", None):
        return "text"
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "audio", None) or getattr(message, "voice", None):
        return "audio"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "video", None):
        return "video"
    return "unknown"


def _safe_text_preview(text: Optional[str], limit: int = 40) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}…"


def _safe_text_hash(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _log_structured_warning(**fields: Any) -> None:
    """Emit a structured warning log (JSON payload)."""
    from app.observability.context import get_context_fields
    from app.observability.trace import get_correlation_id as get_trace_correlation_id

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
        "message_type": fields.get("message_type"),
        "text_length": fields.get("text_length"),
        "text_hash": fields.get("text_hash"),
        "text_preview": fields.get("text_preview"),
        "model_id": fields.get("model_id"),
        "gen_type": fields.get("gen_type"),
        "task_id": fields.get("task_id"),
        "job_id": fields.get("job_id"),
        "sku_id": fields.get("sku_id"),
        "price_rub": fields.get("price_rub"),
        "stage": fields.get("stage"),
        "waiting_for": fields.get("waiting_for"),
        "param": fields.get("param"),
        "outcome": fields.get("outcome"),
        "duration_ms": fields.get("duration_ms"),
        "error_id": fields.get("error_id"),
        "error_code": fields.get("error_code"),
        "fix_hint": fields.get("fix_hint"),
    }
    logger.warning("STRUCTURED_LOG %s", json.dumps(payload, ensure_ascii=False, default=str))


async def get_kie_credits_cached(*, correlation_id: Optional[str] = None) -> Dict[str, Any]:
    """Fetch KIE credits with TTL cache and strict timeout."""
    now = time.monotonic()
    cached_ts = _kie_credits_cache.get("timestamp", 0.0)
    cached_value = _kie_credits_cache.get("value")
    if cached_value and now - cached_ts < KIE_CREDITS_CACHE_TTL_SECONDS:
        return cached_value
    if kie is None:
        return {
            "ok": False,
            "credits": None,
            "status": 0,
            "error": "kie_not_initialized",
            "correlation_id": correlation_id,
        }
    get_credits = getattr(kie, "get_credits", None)
    if not callable(get_credits):
        return {
            "ok": False,
            "credits": None,
            "status": 0,
            "error": "missing_get_credits",
            "correlation_id": correlation_id,
        }
    try:
        result = await asyncio.wait_for(get_credits(), timeout=KIE_CREDITS_TIMEOUT_SECONDS)
    except Exception as exc:
        corr_id = correlation_id or uuid.uuid4().hex
        logger.warning("KIE credits request failed corr_id=%s error=%s", corr_id, exc)
        result = {
            "ok": False,
            "credits": None,
            "status": 0,
            "error": "timeout",
            "correlation_id": corr_id,
        }
    _kie_credits_cache["timestamp"] = now
    _kie_credits_cache["value"] = result
    return result


def _log_handler_latency(handler: str, start_ts: float, update: Update) -> None:
    duration_ms = int((time.monotonic() - start_ts) * 1000)
    user_id = update.effective_user.id if update and update.effective_user else None
    chat_id = update.effective_chat.id if update and update.effective_chat else None
    update_id = update.update_id if update else None
    logger.info(
        "HANDLER_LATENCY handler=%s duration_ms=%s user_id=%s chat_id=%s update_id=%s",
        handler,
        duration_ms,
        user_id,
        chat_id,
        update_id,
    )


def _extract_session_snapshot(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: Optional[int],
    update_id: Optional[int],
) -> Dict[str, Any]:
    if user_id is None:
        return {}
    store = get_session_store(context)
    session = get_session_cached(context, store, user_id, update_id, default={})
    if not isinstance(session, dict):
        return {}
    price_quote = session.get("price_quote") if isinstance(session.get("price_quote"), dict) else {}
    return {
        "waiting_for": session.get("waiting_for"),
        "current_param": session.get("current_param"),
        "model_id": session.get("model_id"),
        "sku_id": session.get("sku_id"),
        "price_rub": price_quote.get("price_rub"),
    }


def _log_route_decision_once(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    waiting_for: Optional[str],
    chosen_handler: str,
    reason: str,
) -> None:
    if not update.message:
        return
    update_id = getattr(update, "update_id", None)
    log_key = update_id if update_id is not None else id(update)
    app = getattr(context, "application", None)
    if app is None:
        return
    logged = app.bot_data.setdefault("_route_decision_logged", set())
    if log_key in logged:
        return
    logged.add(log_key)
    correlation_id = ensure_correlation_id(update, context)
    update_type = _resolve_update_type(update)
    logger.info(
        "ROUTE_DECISION update_type=%s waiting_for=%s chosen_handler=%s reason=%s correlation_id=%s",
        update_type,
        waiting_for,
        chosen_handler,
        reason,
        correlation_id,
    )


async def inbound_update_logger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log every inbound Telegram update and set contextvars for propagation."""
    from app.observability.context import set_update_context

    correlation_id = ensure_correlation_id(update, context)
    ctx = set_update_context(update, context, correlation_id=correlation_id)

    command = None
    callback_data = None
    action_path = None
    if update.message and update.message.text and update.message.text.startswith("/"):
        command = update.message.text.split()[0]
        action_path = f"command:{command}"
    if update.callback_query:
        callback_data = update.callback_query.data
        action_path = build_action_path(callback_data)

    log_structured_event(
        correlation_id=correlation_id,
        update_id=ctx.update_id,
        user_id=ctx.user_id,
        chat_id=ctx.chat_id,
        update_type=ctx.update_type,
        action="TG_UPDATE_IN",
        action_path=action_path,
        command=_truncate_log_value(command),
        callback_data=_truncate_log_value(callback_data),
        outcome="received",
    )


async def user_action_audit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Audit layer for all callback queries (non-blocking)."""
    if not update.callback_query:
        return
    query = update.callback_query
    correlation_id = ensure_correlation_id(update, context)
    user_id = query.from_user.id if query.from_user else None
    chat_id = query.message.chat_id if query.message else None
    update_id = getattr(update, "update_id", None)
    session_snapshot = _extract_session_snapshot(context, user_id, update_id)
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        update_type="callback",
        action="USER_ACTION",
        action_path=build_action_path(query.data),
        callback_data=_truncate_log_value(query.data),
        message_type=None,
        model_id=session_snapshot.get("model_id"),
        waiting_for=session_snapshot.get("waiting_for"),
        sku_id=session_snapshot.get("sku_id"),
        price_rub=session_snapshot.get("price_rub"),
        stage="USER_ACTION_AUDIT",
        outcome="observed",
        param={
            "handled_by": "user_action_audit_callback",
            "current_param": session_snapshot.get("current_param"),
        },
    )


async def user_action_audit_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Audit layer for all incoming messages (non-blocking)."""
    if not update.message:
        return
    correlation_id = ensure_correlation_id(update, context)
    update_id = getattr(update, "update_id", None)
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    message = update.message
    message_type = _resolve_message_type(message)
    text_value = message.text or message.caption or ""
    session_snapshot = _extract_session_snapshot(context, user_id, update_id)
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        update_type="message",
        action="USER_ACTION",
        action_path=f"message_input:{message_type}",
        message_type=message_type,
        text_length=len(text_value) if text_value else 0,
        text_hash=_safe_text_hash(text_value),
        text_preview=_safe_text_preview(text_value),
        model_id=session_snapshot.get("model_id"),
        waiting_for=session_snapshot.get("waiting_for"),
        sku_id=session_snapshot.get("sku_id"),
        price_rub=session_snapshot.get("price_rub"),
        stage="USER_ACTION_AUDIT",
        outcome="observed",
        param={
            "handled_by": "user_action_audit_message",
            "current_param": session_snapshot.get("current_param"),
        },
    )


async def inbound_rate_limit_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deduplicate updates and apply per-user rate limits before handlers."""
    from telegram.ext import ApplicationHandlerStop
    from app.observability.no_silence_guard import track_outgoing_action
    from app.ux.navigation import build_back_to_menu_keyboard

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    correlation_id = ensure_correlation_id(update, context)
    update_id = getattr(update, "update_id", None)

    if update_id is not None and _update_deduper.seen(update_id):
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="TG_UPDATE_IN",
            action_path="dedup:update_id",
            outcome="deduped",
            fix_hint="duplicate_update_id",
        )
        if update.callback_query:
            try:
                await update.callback_query.answer()
                track_outgoing_action(update_id, action_type="answerCallbackQuery")
            except Exception as exc:
                logger.warning("CALLBACK_THROTTLE_ANSWER_FAILED user_id=%s update_id=%s error=%s", user_id, update_id, exc, exc_info=True)
        raise ApplicationHandlerStop

    if update.callback_query and update.callback_query.id:
        callback_id = update.callback_query.id
        if _callback_deduper.seen(callback_id):
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="TG_UPDATE_IN",
                action_path="dedup:callback",
                outcome="deduped",
                fix_hint="duplicate_callback_id",
                param={"callback_id": callback_id},
            )
            try:
                await update.callback_query.answer()
                if update_id is not None:
                    track_outgoing_action(update_id, action_type="answerCallbackQuery")
            except Exception as exc:
                logger.warning("CALLBACK_DEDUP_ANSWER_FAILED user_id=%s update_id=%s callback_id=%s error=%s", user_id, update_id, callback_id, exc, exc_info=True)
            raise ApplicationHandlerStop

    if update.callback_query and update.callback_query.data and user_id is not None:
        callback_key = (user_id, update.callback_query.data)
        allowed, retry_after = _callback_data_rate_limiter.check(callback_key)
        if not allowed:
            wait_seconds = max(1, int(math.ceil(retry_after)))
            user_lang = get_user_language(user_id) if user_id else "ru"
            text = (
                f"⏳ <b>Слишком часто</b>\n\n"
                f"Попробуйте снова через {wait_seconds} сек."
                if user_lang == "ru"
                else f"⏳ <b>Too many taps</b>\n\nTry again in {wait_seconds}s."
            )
            reply_markup = build_back_to_menu_keyboard(user_lang)
            try:
                await update.callback_query.answer()
                if update_id is not None:
                    track_outgoing_action(update_id, action_type="answerCallbackQuery")
            except Exception as exc:
                logger.warning("CALLBACK_RATELIMIT_ANSWER_FAILED user_id=%s update_id=%s error=%s", user_id, update_id, exc, exc_info=True)
            if chat_id:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    if update_id is not None:
                        track_outgoing_action(update_id, action_type="send_message")
                except Exception:
                    logger.warning("Failed to send callback throttle response to user %s", user_id, exc_info=True)
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="TG_RATE_LIMIT",
                action_path="rate_limit_guard:callback_data",
                outcome="throttled",
                param={
                    "retry_after": wait_seconds,
                    "callback_data": update.callback_query.data,
                },
            )
            raise ApplicationHandlerStop

    limiter = _callback_rate_limiter if update.callback_query else _message_rate_limiter
    allowed, retry_after = limiter.check(user_id)
    if allowed:
        return

    wait_seconds = max(1, int(math.ceil(retry_after)))
    user_lang = get_user_language(user_id) if user_id else "ru"
    text = (
        f"⏳ <b>Слишком быстро</b>\n\n"
        f"Попробуйте снова через {wait_seconds} сек."
        if user_lang == "ru"
        else f"⏳ <b>Too fast</b>\n\nTry again in {wait_seconds}s."
    )
    reply_markup = build_back_to_menu_keyboard(user_lang)

    if update.callback_query:
        try:
            await update.callback_query.answer()
            if update_id is not None:
                track_outgoing_action(update_id, action_type="answerCallbackQuery")
        except Exception as exc:
            logger.warning("MESSAGE_RATELIMIT_CALLBACK_ANSWER_FAILED user_id=%s update_id=%s error=%s", user_id, update_id, exc, exc_info=True)

    if chat_id:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            if update_id is not None:
                track_outgoing_action(update_id, action_type="send_message")
        except Exception:
            logger.warning("Failed to send throttle response to user %s", user_id, exc_info=True)

    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        action="TG_RATE_LIMIT",
        action_path="rate_limit_guard",
        outcome="throttled",
        param={"retry_after": wait_seconds, "update_type": "callback" if update.callback_query else "message"},
    )
    raise ApplicationHandlerStop

# ==================== SELF-CHECK: ENV SUMMARY AND VALIDATION ====================
def log_env_summary():
    """Логирует summary ENV переменных без секретов"""
    env_vars = {
        "PORT": os.getenv("PORT", "not set"),
        "RENDER": os.getenv("RENDER", "not set"),
        "ENV": os.getenv("ENV", "not set"),
        "BOT_MODE": os.getenv("BOT_MODE", "not set"),
        "STORAGE_MODE": os.getenv("STORAGE_MODE", "not set"),
        "TELEGRAM_BOT_TOKEN": "[SET]" if os.getenv("TELEGRAM_BOT_TOKEN") else "[NOT SET]",
        "KIE_API_KEY": "[SET]" if os.getenv("KIE_API_KEY") else "[NOT SET]",
        "KIE_API_URL": os.getenv("KIE_API_URL", "not set"),
        "TEST_MODE": os.getenv("TEST_MODE", "not set"),
        "DRY_RUN": os.getenv("DRY_RUN", "not set"),
        "ALLOW_REAL_GENERATION": os.getenv("ALLOW_REAL_GENERATION", "not set"),
        "KIE_STUB": os.getenv("KIE_STUB", "not set"),
    }
    
    logger.info("=" * 60)
    logger.info("ENVIRONMENT VARIABLES SUMMARY")
    logger.info("=" * 60)
    for key, value in sorted(env_vars.items()):
        logger.info(f"{key}={value}")
    logger.info("=" * 60)


def validate_required_env():
    """Проверяет обязательные переменные окружения"""
    errors = []
    warnings = []
    
    # TELEGRAM_BOT_TOKEN - обязателен всегда
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        errors.append("TELEGRAM_BOT_TOKEN is required but not set")
    
    # KIE_API_KEY - обязателен если real generation
    allow_real = os.getenv("ALLOW_REAL_GENERATION", "1") != "0"
    test_mode = os.getenv("TEST_MODE", "0") == "1"
    kie_stub = os.getenv("KIE_STUB", "0") == "1"
    
    if allow_real and not test_mode and not kie_stub:
        if not os.getenv("KIE_API_KEY"):
            errors.append("KIE_API_KEY is required for real generation (set ALLOW_REAL_GENERATION=0 or TEST_MODE=1 to disable)")
    
    # Проверяем наличие критических файлов (warning, не error - может быть опциональным)
    models_yaml = Path(__file__).parent / "models" / "kie_models.yaml"
    if not models_yaml.exists():
        warnings.append(f"models/kie_models.yaml not found at {models_yaml} - model registry may not work")
    
    # Проверяем PyYAML (warning, не error - может быть опциональным в некоторых режимах)
    try:
        import yaml
    except ImportError:
        warnings.append("PyYAML not installed - model registry from YAML will not work (install with: pip install PyYAML)")
    
    # Выводим предупреждения
    if warnings:
        logger.warning("=" * 60)
        logger.warning("ENVIRONMENT WARNINGS")
        logger.warning("=" * 60)
        for warning in warnings:
            logger.warning(f"⚠️  {warning}")
        logger.warning("=" * 60)
    
    # Выводим ошибки и выходим
    if errors:
        logger.error("=" * 60)
        logger.error("ENVIRONMENT VALIDATION FAILED")
        logger.error("=" * 60)
        for error in errors:
            logger.error(f"❌ {error}")
        logger.error("=" * 60)
        logger.error("Please fix the errors above and restart the bot")
        sys.exit(1)
    
    logger.info("✅ Environment validation passed")


# Выполняем self-check ПЕРЕД импортом других модулей
# ТОЛЬКО если явно запрошено через RUN_ENV_CHECK=1 и не пропущено через SKIP_CONFIG_INIT=1
# Это позволяет тестам импортировать модуль без side effects
if os.getenv("RUN_ENV_CHECK", "0") == "1" and os.getenv("SKIP_CONFIG_INIT", "0") != "1":
    log_env_summary()
    validate_required_env()
elif os.getenv("SKIP_CONFIG_INIT", "0") != "1" and os.getenv("TEST_MODE", "0") != "1":
    # В production режиме логируем summary без валидации (чтобы не падать при отсутствии ENV)
    # Валидация будет происходить в main() / create_bot_application()
    log_env_summary()

# ==================== IMPORTS AFTER SELF-CHECK ====================
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler, TypeHandler
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery, BotCommand
from telegram.ext import ContextTypes
from telegram.error import BadRequest

# ==================== TELEGRAM TEXT LIMITS ====================
TELEGRAM_TEXT_LIMIT = 4000
TELEGRAM_CHUNK_LIMIT = 3900

_CALLBACK_ANSWER_PATCHED = False
_CALLBACK_EDIT_TEXT_PATCHED = False
_MESSAGE_EDIT_TEXT_PATCHED = False


def _patch_callback_query_answer() -> None:
    global _CALLBACK_ANSWER_PATCHED
    if _CALLBACK_ANSWER_PATCHED:
        return

    original_answer = CallbackQuery.answer

    async def safe_answer(self, *args, **kwargs):
        try:
            return await original_answer(self, *args, **kwargs)
        except BadRequest as exc:
            message = str(exc).lower()
            if (
                "query is too old" in message
                or "response timeout expired" in message
                or "query id is invalid" in message
            ):
                logger.info(
                    "Ignoring expired callback answer: query_id=%s error=%s",
                    getattr(self, "id", None),
                    exc,
                )
                return None
            raise
        except Exception as exc:
            logger.warning(
                "Failed to answer callback query: query_id=%s error=%s",
                getattr(self, "id", None),
                exc,
            )
            return None

    CallbackQuery.answer = safe_answer
    _CALLBACK_ANSWER_PATCHED = True


_patch_callback_query_answer()


def _patch_callback_query_edit_message_text() -> None:
    """Patch CallbackQuery.edit_message_text to ignore benign 'Message is not modified' errors.

    This error is expected when a user presses the same menu button twice and the bot
    attempts to edit the message with identical content/markup.
    """

    global _CALLBACK_EDIT_TEXT_PATCHED
    if _CALLBACK_EDIT_TEXT_PATCHED:
        return

    original_edit = CallbackQuery.edit_message_text

    async def safe_edit_message_text(self, *args, **kwargs):
        try:
            return await original_edit(self, *args, **kwargs)
        except BadRequest as exc:
            message = str(exc).lower()
            if "message is not modified" in message:
                logger.info(
                    "Ignoring benign edit_message_text(no-op): query_id=%s error=%s",
                    getattr(self, "id", None),
                    exc,
                )
                # Return current message object (best-effort) to match PTB expectations.
                return getattr(self, "message", None)
            raise
        except Exception as exc:
            logger.warning(
                "Failed to edit callback message text: query_id=%s error=%s",
                getattr(self, "id", None),
                exc,
            )
            return getattr(self, "message", None)

    CallbackQuery.edit_message_text = safe_edit_message_text
    _CALLBACK_EDIT_TEXT_PATCHED = True


def _patch_message_edit_text() -> None:
    """Patch Message.edit_text to ignore benign 'Message is not modified' errors."""

    global _MESSAGE_EDIT_TEXT_PATCHED
    if _MESSAGE_EDIT_TEXT_PATCHED:
        return

    try:
        from telegram import Message
    except Exception as exc:
        logger.error("CRITICAL_IMPORT_FAILED module=telegram.Message error=%s", exc, exc_info=True)
        return

    original_edit = Message.edit_text

    async def safe_message_edit_text(self, *args, **kwargs):
        try:
            return await original_edit(self, *args, **kwargs)
        except BadRequest as exc:
            message = str(exc).lower()
            if "message is not modified" in message:
                logger.info(
                    "Ignoring benign message.edit_text(no-op): message_id=%s error=%s",
                    getattr(self, "message_id", None),
                    exc,
                )
                return self
            raise
        except Exception as exc:
            logger.warning(
                "Failed to edit message text: message_id=%s error=%s",
                getattr(self, "message_id", None),
                exc,
            )
            return self

    Message.edit_text = safe_message_edit_text
    _MESSAGE_EDIT_TEXT_PATCHED = True


_patch_callback_query_edit_message_text()
_patch_message_edit_text()

# Убрано: from dotenv import load_dotenv
# Все переменные окружения ТОЛЬКО из ENV (Render Dashboard)

# ==================== GLOBAL POLLING START CONTROL ====================
# Жёсткая защита от повторных запусков polling (409 Conflict)
_POLLING_STARTED = False
_POLLING_LOCK = asyncio.Lock()
from knowledge_storage import KnowledgeStorage
from translations import t, TRANSLATIONS
from kie_client import get_client
from kie_gateway import get_kie_gateway
from config_runtime import is_dry_run, allow_real_generation, is_test_mode, get_config_summary
from helpers import (
    build_main_menu_keyboard, get_balance_info, format_balance_message,
    get_balance_keyboard, set_constants
)
# Используем registry как единый источник моделей
from app.models.registry import get_models_sync
from app.services.free_tools_service import (
    add_referral_free_bonus,
    check_and_consume_free_generation,
    check_free_generation_available,
    consume_free_generation,
    format_free_counter_block,
    get_free_generation_status,
    get_free_counter_snapshot,
    get_free_tools_config,
    get_free_tools_model_ids,
)
from app.pricing.ssot_catalog import format_pricing_blocked_message
from kie_models import (
    get_generation_types, get_models_by_generation_type, get_generation_type_info
)
from app.session_store import (
    get_session_store,
    get_session_cached,
    ensure_session_cached,
    get_session_get_count,
)


def ensure_source_of_truth():
    """Validate registry/pricing sources and exit on mismatch."""
    from app.models.yaml_registry import get_registry_path, load_yaml_models
    from app.kie_catalog.catalog import get_catalog_source_info, _load_yaml_catalog
    from pricing.engine import get_settings_source_info

    registry_path = get_registry_path()
    registry_models = load_yaml_models()
    if not registry_models:
        logger.error(f"❌ FATAL: registry file missing or empty: {registry_path}")
        sys.exit(1)

    catalog_info = get_catalog_source_info()
    raw_catalog = _load_yaml_catalog()
    if not raw_catalog:
        logger.error(f"❌ FATAL: pricing catalog missing or empty: {catalog_info['path']}")
        sys.exit(1)

    pricing_settings_info = get_settings_source_info()
    pricing_settings = pricing_settings_info.get("settings", {})
    price_multiplier_env = os.getenv("PRICE_MULTIPLIER", "").strip()
    if not pricing_settings_info.get("path") or pricing_settings_info.get("path") == "unknown":
        if not price_multiplier_env:
            logger.error("❌ FATAL: pricing settings file not found and env overrides missing")
            sys.exit(1)

    if "usd_to_rub" not in pricing_settings:
        logger.error("❌ FATAL: usd_to_rub missing in pricing settings and USD_TO_RUB env not set")
        sys.exit(1)
    if not price_multiplier_env and "markup_multiplier" not in pricing_settings:
        logger.error("❌ FATAL: markup_multiplier missing in pricing settings and PRICE_MULTIPLIER env not set")
        sys.exit(1)

    usd_to_rub_value = float(pricing_settings.get("usd_to_rub"))
    markup_multiplier_value = float(price_multiplier_env or pricing_settings.get("markup_multiplier"))

    registry_ids = set(registry_models.keys())
    pricing_ids = {item.get("id") for item in raw_catalog if isinstance(item, dict)}
    missing_in_pricing = sorted([model_id for model_id in registry_ids if model_id not in pricing_ids])
    if missing_in_pricing:
        logger.error(
            "❌ FATAL: registry models missing in pricing catalog: %s (catalog=%s)",
            ", ".join(missing_in_pricing),
            catalog_info["path"],
        )
        sys.exit(1)

    logger.info(
        "✅ SOURCE OF TRUTH: registry=%s models=%s | pricing_catalog=%s models=%s | pricing_settings=%s "
        "| usd_to_rub=%s | price_multiplier=%s",
        registry_path,
        len(registry_models),
        catalog_info["path"],
        catalog_info["count"],
        pricing_settings_info["path"],
        usd_to_rub_value,
        markup_multiplier_value,
    )


# Вспомогательные функции для работы с реестром моделей
def get_model_by_id_from_registry(model_id: str) -> Optional[Dict[str, Any]]:
    """Получает модель из реестра по ID"""
    models = get_models_sync()
    for model in models:
        if model.get('id') == model_id:
            return model
    return None


_VISIBLE_MODEL_IDS_CACHE: Optional[Set[str]] = None


def _get_visible_model_ids() -> Set[str]:
    global _VISIBLE_MODEL_IDS_CACHE
    if _VISIBLE_MODEL_IDS_CACHE is None:
        from app.ux.model_visibility import is_model_visible

        _VISIBLE_MODEL_IDS_CACHE = {
            model_id
            for model in get_models_sync()
            if (model_id := model.get("id")) and is_model_visible(model_id)
        }
    return _VISIBLE_MODEL_IDS_CACHE


def filter_visible_models(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    visible_ids = _get_visible_model_ids()
    return [model for model in models if model.get("id") in visible_ids]


def get_visible_models_by_generation_type(gen_type: str) -> List[Dict[str, Any]]:
    return filter_visible_models(get_models_by_generation_type(gen_type))

def get_models_by_category_from_registry(category: str) -> List[Dict[str, Any]]:
    """Получает модели из реестра по категории"""
    models = get_models_sync()
    return filter_visible_models([m for m in models if m.get('category') == category])

def get_categories_from_registry() -> List[str]:
    """Получает список категорий из реестра"""
    models = get_models_sync()
    categories = set()
    for model in models:
        cat = model.get('category')
        if cat:
            categories.add(cat)
    return sorted(list(categories))


def _determine_primary_input(
    model_info: Dict[str, Any],
    input_params: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    """Determine which input should be requested first based on model_type + schema."""
    model_type = (model_info.get("model_mode") or model_info.get("model_type") or "").lower()
    image_param = None
    if "image_input" in input_params:
        image_param = "image_input"
    elif "image_urls" in input_params:
        image_param = "image_urls"
    audio_param = None
    if "audio_input" in input_params:
        audio_param = "audio_input"
    elif "audio_url" in input_params:
        audio_param = "audio_url"

    if model_type in {"image_to_video", "image_to_image", "image_edit", "outpaint", "upscale", "video_upscale"}:
        if image_param:
            return {"type": "image", "param": image_param}
    if model_type in {"speech_to_text", "audio_to_audio", "speech_to_video"}:
        if audio_param:
            return {"type": "audio", "param": audio_param}
    if model_type in {"text_to_video", "text_to_image", "text_to_speech", "text_to_audio", "text"}:
        if "prompt" in input_params:
            return {"type": "prompt", "param": "prompt"}
        if "text" in input_params:
            return {"type": "prompt", "param": "text"}

    # Fallback for unknown types: prefer required media, then prompt
    if image_param and input_params.get(image_param, {}).get("required", False):
        return {"type": "image", "param": image_param}
    if audio_param and input_params.get(audio_param, {}).get("required", False):
        return {"type": "audio", "param": audio_param}
    if "prompt" in input_params:
        return {"type": "prompt", "param": "prompt"}
    if "text" in input_params:
        return {"type": "prompt", "param": "text"}

    return None


def _normalize_enum_values(param_info: Dict[str, Any]) -> List[Any]:
    enum_values = param_info.get("enum") or param_info.get("values")
    if enum_values is None:
        return []
    if isinstance(enum_values, str):
        return [enum_values]
    if isinstance(enum_values, dict):
        return list(enum_values.values())
    normalized: List[Any] = []
    for value in enum_values:
        if isinstance(value, dict):
            normalized.append(value.get("value") or value.get("id") or value.get("name"))
        else:
            normalized.append(value)
    return [value for value in normalized if value is not None]


def _get_media_kind(param_name: str) -> Optional[str]:
    name = param_name.lower()
    if any(key in name for key in ["image", "photo", "mask"]):
        return "image"
    if "video" in name:
        return "video"
    if any(key in name for key in ["audio", "voice"]):
        return "audio"
    if any(key in name for key in ["document", "file"]):
        return "document"
    return None


def _is_primary_media_input_param(param_name: str) -> bool:
    normalized = param_name.lower()
    primary_media_inputs = {
        "image_input",
        "image_urls",
        "image_url",
        "video_input",
        "video_url",
        "audio_input",
        "audio_url",
        "document_input",
        "document_url",
        "file_input",
        "file_url",
    }
    if normalized in primary_media_inputs:
        return True
    if normalized.endswith("_input") or normalized.endswith("_url") or normalized.endswith("_urls"):
        return _get_media_kind(normalized) in {"image", "video", "audio", "document"}
    return False


def _should_force_media_required(model_type: str, media_kind: str) -> bool:
    normalized = (model_type or "").lower()
    if media_kind == "image":
        return normalized in {
            "image_edit",
            "image_to_image",
            "image_to_video",
            "outpaint",
            "upscale",
            "video_upscale",
        }
    if media_kind == "video":
        return normalized in {"image_to_video", "video_upscale"}
    if media_kind == "audio":
        return normalized.startswith("audio_") or normalized in {"speech_to_text", "speech_to_video", "music"}
    if media_kind == "document":
        return normalized in {"document", "document_to_text"}
    return False


def _apply_media_required_overrides(
    model_spec: "ModelSpec",
    input_params: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str], List[str]]:
    """Force media inputs to required when model type implies mandatory media."""
    import copy

    properties = copy.deepcopy(input_params or {})
    required = set(model_spec.schema_required or [])
    forced_required: List[str] = []
    model_type = (model_spec.model_type or model_spec.model_mode or "").lower()

    for param_name, param_info in properties.items():
        media_kind = _get_media_kind(param_name)
        if not media_kind or not _is_primary_media_input_param(param_name):
            continue
        if not _should_force_media_required(model_type, media_kind):
            continue
        if not param_info.get("required", False):
            param_info["required"] = True
            forced_required.append(param_name)
        required.add(param_name)

    return properties, sorted(required), forced_required


def _build_param_order(input_params: Dict[str, Any]) -> List[str]:
    media_params = []
    text_params = []
    required_params = []
    optional_params = []

    for param_name, param_info in input_params.items():
        is_required = param_info.get("required", False)
        media_kind = _get_media_kind(param_name)

        if media_kind:
            target = media_params if is_required else optional_params
            target.append(param_name)
            continue

        if param_name in {"prompt", "text"}:
            target = text_params if is_required else optional_params
            target.append(param_name)
            continue

        if is_required:
            required_params.append(param_name)
        else:
            optional_params.append(param_name)

    return media_params + text_params + required_params + optional_params


def _is_image_only_model(properties: Dict[str, Any]) -> bool:
    if not properties:
        return False
    required_fields = [name for name, info in properties.items() if info.get("required", False)]
    if not required_fields:
        return False
    has_text = any(name in {"prompt", "text"} for name in required_fields)
    if has_text:
        return False
    return all(_get_media_kind(name) == "image" for name in required_fields)


def _first_required_media_param(properties: Dict[str, Any]) -> Optional[str]:
    for param_name, info in properties.items():
        if info.get("required", False) and _get_media_kind(param_name):
            return param_name
    return None


def _detect_ssot_conflicts(model_spec: "ModelSpec", properties_override: Optional[Dict[str, Any]] = None) -> list[str]:
    conflicts: list[str] = []
    model_type = (model_spec.model_type or "").lower()
    properties = properties_override or model_spec.schema_properties or {}
    required_media = [
        name for name, info in properties.items()
        if info.get("required", False) and _get_media_kind(name)
    ]
    if model_type in {"text_to_image", "text_to_video", "text_to_audio", "text_to_speech", "text"} and required_media:
        conflicts.append("SSOT_CONFLICT_TEXT_MODEL_REQUIRES_IMAGE")
    if model_type in {"image_edit", "image_to_image", "image_to_video", "outpaint", "upscale", "video_upscale"}:
        if not required_media:
            conflicts.append("SSOT_CONFLICT_IMAGE_MODEL_MISSING_IMAGE_INPUT")
    return conflicts


def _is_missing_media_error(error: str) -> bool:
    if not error:
        return False
    lowered = error.lower()
    if "image" in lowered or "mask" in lowered:
        return any(token in lowered for token in ["required", "missing", "must", "need"])
    return False


def _extract_missing_param(error_message: Optional[str], properties: Dict[str, Any]) -> Optional[str]:
    if not error_message or not properties:
        return None
    lowered = error_message.lower()
    for param_name in properties:
        if param_name.lower() in lowered:
            return param_name
        spaced = param_name.replace("_", " ").lower()
        if spaced and spaced in lowered:
            return param_name
    return None


def _collect_missing_required_media(session: Dict[str, Any]) -> List[str]:
    properties = session.get("properties", {})
    params = session.get("params", {})
    required = set(session.get("required", []))
    model_type = session.get("model_type") or session.get("model_mode") or session.get("gen_type") or ""
    missing: List[str] = []
    for param_name, param_info in properties.items():
        media_kind = _get_media_kind(param_name)
        if not media_kind:
            continue
        is_required = param_info.get("required", False) or param_name in required
        if (
            not is_required
            and _is_primary_media_input_param(param_name)
            and _should_force_media_required(model_type, media_kind)
        ):
            is_required = True
        if not is_required:
            continue
        value = params.get(param_name)
        if value:
            continue
        session_value = session.get(param_name)
        if not session_value:
            missing.append(param_name)
    return missing


def _kie_readiness_state() -> tuple[bool, str]:
    if is_dry_run() or not allow_real_generation():
        return True, "dry_run"
    if is_test_mode() or os.getenv("KIE_STUB", "0").lower() in ("1", "true", "yes"):
        return True, "stub"
    api_key = os.getenv("KIE_API_KEY", "").strip()
    if not api_key:
        return False, "missing_api_key"
    try:
        from app.kie.kie_client import get_kie_client

        client = get_kie_client()
    except Exception as exc:
        logger.warning("KIE_CLIENT_IMPORT_FAILED error=%s - graceful degradation to None", exc, exc_info=True)
        client = None
    if client is None:
        return False, "client_none"
    if not getattr(client, "api_key", None):
        return False, "missing_api_key"
    return True, "ready"


def _select_next_param(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    properties = session.get("properties", {})
    params = session.get("params", {})
    param_order = session.get("param_order") or _build_param_order(properties)
    session["param_order"] = param_order
    required_params = session.get("required", [])
    required_order = [name for name in param_order if name in required_params]
    if not required_order:
        required_order = [name for name in required_params if name in properties]
    for param_name in required_order:
        if param_name in params:
            continue
        param_info = properties.get(param_name, {})
        param_type = param_info.get("type", "string")
        enum_values = _normalize_enum_values(param_info)
        is_optional = not param_info.get("required", False)
        if param_name in required_params:
            is_optional = False
        media_kind = _get_media_kind(param_name)
        reason = "missing_required"
        if enum_values:
            reason = "enum_buttons"
        return {
            "param_name": param_name,
            "param_info": param_info,
            "param_type": param_type,
            "enum_values": enum_values,
            "is_optional": is_optional,
            "media_kind": media_kind,
            "reason": reason,
        }
    return None
import json
import aiohttp
import aiofiles
import io
from io import BytesIO
import re
import platform
import random
import traceback
import time
from asyncio import Lock
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Shared HTTP client session (initialized lazily via get_http_client)
_http_client: aiohttp.ClientSession | None = None

# Ensure Python can find modules in the same directory (for Render compatibility)
sys.path.insert(0, str(Path(__file__).parent))

# Убрано: load_dotenv()
# Все переменные окружения ТОЛЬКО из ENV (Render Dashboard)
# Для локальной разработки используйте системные ENV переменные

# Try to import PIL/Pillow
try:
    from PIL import Image
    PIL_AVAILABLE = True
    logger.info("✅ PIL/Pillow loaded successfully")
except ImportError:
    PIL_AVAILABLE = False
    logger.info("ℹ️ PIL/Pillow not available. Image analysis will be limited. Install with: pip install Pillow")

# Try to import pytesseract and configure Tesseract path
try:
    import pytesseract
    OCR_AVAILABLE = True
    tesseract_found = False
    
    # Try to set Tesseract path
    # On Windows, check common installation paths
    # On Linux (Render/Timeweb), Tesseract should be in PATH
    if platform.system() == 'Windows':
        # Common Tesseract installation paths on Windows
        possible_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', '')),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                tesseract_found = True
                logger.info(f"Tesseract found at: {path}")
                break
    else:
        # On Linux, Tesseract should be in PATH (installed via apt-get in Dockerfile)
        # Try to verify it's available by checking if command exists
        import shutil
        if shutil.which('tesseract'):
            logger.info("✅ Tesseract found in PATH (Linux)")
            tesseract_found = True
        else:
            logger.info("ℹ️ Tesseract not found in PATH. OCR will be disabled. Install with: apt-get install tesseract-ocr")
            tesseract_found = False
    
    if not tesseract_found:
        logger.info("[INFO] Tesseract not found. OCR analysis will be disabled. Install tesseract-ocr package if needed.")
        OCR_AVAILABLE = False
    else:
        # Don't test Tesseract at import time - it can hang or timeout
        # Test will happen when OCR is actually needed
        logger.info("✅ Tesseract OCR path configured. Will be tested when needed.")
except ImportError:
    OCR_AVAILABLE = False
    tesseract_found = False
    logger.info("ℹ️ pytesseract not available. OCR analysis will be disabled. Install with: pip install pytesseract")

# Импортируем конфигурацию из app.config (централизованная конфигурация из ENV)
try:
    from app.config import BOT_TOKEN, BOT_MODE, WEBHOOK_URL
    from app.utils.mask import mask as mask_secret
    from app.singleton_lock import get_singleton_lock
    from app.bot_mode import get_bot_mode, ensure_polling_mode, ensure_webhook_mode, handle_conflict_gracefully
except ImportError:
    # Fallback для обратной совместимости (если app.config не доступен)
    import warnings
    warnings.warn("app.config not found, using os.getenv directly. This is deprecated.")
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    BOT_MODE = os.getenv('BOT_MODE', 'polling')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    
    # Fallback для mask_secret
    def mask_secret(value: Optional[str], show_first: int = 4, show_last: int = 4) -> str:
        """
        Fallback маскирование секретного значения.
        В продакшн используйте app.utils.mask.mask()
        """
        if not value:
            return ""
        if len(value) <= show_first + show_last:
            return "****"
        return value[:show_first] + "****" + value[-show_last:]
    
    # Fallback для bot_mode функций
    def get_bot_mode() -> str:
        """Fallback для get_bot_mode"""
        mode = os.getenv("BOT_MODE", "").lower().strip()
        if not mode:
            if os.getenv("PORT") and os.getenv("WEBHOOK_URL"):
                mode = "webhook"
            else:
                mode = "polling"
        if mode not in ["polling", "webhook"]:
            mode = "polling"
        return mode
    
    async def ensure_polling_mode(bot):
        """Fallback для ensure_polling_mode"""
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                await bot.delete_webhook(drop_pending_updates=True)
            return True
        except Exception as exc:
            logger.warning("DELETE_WEBHOOK_FAILED error=%s", exc, exc_info=True)
            return False
    
    async def ensure_webhook_mode(bot, webhook_url: str):
        """Fallback для ensure_webhook_mode"""
        if not webhook_url:
            return False
        try:
            await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            return True
        except Exception as exc:
            logger.warning("SET_WEBHOOK_FAILED url=%s error=%s", webhook_url, exc, exc_info=True)
            return False
    
    def handle_conflict_gracefully(error, mode: str):
        """Fallback для handle_conflict_gracefully"""
        import sys
        logging.getLogger(__name__).error(f"Conflict detected in {mode} mode: {error}")
        sys.exit(0)
    
    # Fallback для singleton_lock
    class DummyLock:
        def acquire(self, timeout=None):
            return True
        def release(self):
            pass
    
    def get_singleton_lock(key: str):
        """Fallback для get_singleton_lock"""
        return DummyLock()

# Admin user ID (can be set via environment variable)
try:
    admin_id_str = os.getenv('ADMIN_ID', '6913446846')
    if admin_id_str and admin_id_str != 'your_admin_id_here':
        ADMIN_ID = int(admin_id_str)
    else:
        ADMIN_ID = 6913446846  # Default fallback
except (ValueError, TypeError):
    ADMIN_ID = 6913446846  # Default fallback if invalid

# Price conversion constants
# Based on: 18 credits = $0.09 = 6.95 ₽
# NOTE: Теперь рекомендуется использовать config.settings для этих значений
CREDIT_TO_USD = 0.005  # 1 credit = $0.005 ($0.09 / 18)
USD_TO_RUB_DEFAULT = 77.83  # 1 USD = 77.83 RUB (fixed from pricing config)

def get_usd_to_rub_rate() -> float:
    """
    Get USD to RUB exchange rate from file, or return default if not set.
    DEPRECATED: Use app.services.payments_service.get_usd_to_rub_rate() instead
    """
    # Импортируем из app/services/payments_service (БЕЗ circular import)
    try:
        from app.services.payments_service import get_usd_to_rub_rate as _get_rate
        return _get_rate()
    except ImportError:
        # Fallback на старую логику
        try:
            rate_data = load_json_file(CURRENCY_RATE_FILE, {})
            rate = rate_data.get('usd_to_rub', USD_TO_RUB_DEFAULT)
            if isinstance(rate, (int, float)) and rate > 0:
                return float(rate)
            else:
                logger.warning(f"Invalid currency rate in file: {rate}, using default: {USD_TO_RUB_DEFAULT}")
                return USD_TO_RUB_DEFAULT
        except Exception as e:
            logger.error(f"Error loading currency rate: {e}, using default: {USD_TO_RUB_DEFAULT}")
            return USD_TO_RUB_DEFAULT

def set_usd_to_rub_rate(rate: float) -> bool:
    """Set USD to RUB exchange rate and save to file."""
    logger.warning("USD to RUB rate is locked from pricing config; update ignored: %s", rate)
    return False

# Импортируем новые сервисы для использования (опционально)
try:
    from bot_kie_services import pricing_service, storage_service, model_validator
    from bot_kie_utils import is_admin as is_admin_new
    NEW_SERVICES_AVAILABLE = True
    logger.info("✅ Новые сервисы загружены успешно")
except ImportError as e:
    NEW_SERVICES_AVAILABLE = False
    # Это нормально, если модуль bot_kie_services не настроен
    logger.debug(f"ℹ️ Новые сервисы не доступны, используется стандартная реализация (это нормально): {e}")

# Database module is disabled in github-only storage mode.
log_kie_operation = None
create_operation = None
get_user_operations = None

# Initialize knowledge storage and KIE client (will be initialized in main() to avoid blocking import)
storage = None
kie = None

# PostgreSQL advisory lock connection (global для keep-alive задачи)
# lock_conn и lock_key_int удалены - используется app.locking.single_instance

# Store user sessions (SSOT via SessionStore)
user_sessions = get_session_store()

# Deduplicate update_id to prevent double-processing bursts
_processed_update_ids: dict[int, float] = {}
_processed_update_ttl_seconds = 120

# Store active generations - allows multiple concurrent generations per user
# Structure: active_generations[(user_id, task_id)] = {session_data}
active_generations = {}
active_generations_lock = asyncio.Lock()

# Track in-flight generation tasks to allow user-triggered cancellation
active_generation_tasks: Dict[int, asyncio.Task] = {}
active_generation_tasks_lock = asyncio.Lock()


async def _remove_active_generation_task(user_id: int) -> None:
    """Remove task tracking entry (best-effort, ignores missing users)."""
    async with active_generation_tasks_lock:
        active_generation_tasks.pop(user_id, None)


async def register_active_generation_task(user_id: int) -> None:
    """Register the current asyncio.Task for cancellation hooks."""
    task = asyncio.current_task()
    if not task:
        return
    async with active_generation_tasks_lock:
        active_generation_tasks[user_id] = task

    def _cleanup(_task: asyncio.Task) -> None:
        asyncio.create_task(_remove_active_generation_task(user_id))

    task.add_done_callback(_cleanup)


async def cancel_active_generation(user_id: int) -> bool:
    """Cancel an in-flight generation task for the user if present."""
    async with active_generation_tasks_lock:
        task = active_generation_tasks.get(user_id)
        if not task:
            return False
        if task.done():
            active_generation_tasks.pop(user_id, None)
            return False
        task.cancel()
        active_generation_tasks.pop(user_id, None)
        return True

# Pending result deliveries for retry (user_id, task_id) -> payload
pending_deliveries: Dict[tuple[int, str], Dict[str, Any]] = {}
pending_deliveries_lock = asyncio.Lock()

# Generation submit locks to prevent double confirm clicks
generation_submit_locks: dict[int, float] = {}
GENERATION_SUBMIT_LOCK_TTL_SECONDS = 20

# Store saved generation data for "generate again" feature
saved_generations = {}

# Maximum concurrent generations per user (to prevent abuse)
MAX_CONCURRENT_GENERATIONS_PER_USER = 5


def get_admin_limits() -> dict:
    """Get admin limits data."""
    return load_json_file(ADMIN_LIMITS_FILE, {})


def save_admin_limits(data: dict):
    """Save admin limits data."""
    save_json_file(ADMIN_LIMITS_FILE, data)


def is_admin(user_id: int) -> bool:
    """Check if user is admin (main admin or limited admin)."""
    if user_id == ADMIN_ID:
        return True
    admin_limits = get_admin_limits()
    return str(user_id) in admin_limits


def get_admin_spent(user_id: int) -> float:
    """Get amount spent by admin (for limited admins)."""
    admin_limits = get_admin_limits()
    admin_data = admin_limits.get(str(user_id), {})
    return admin_data.get('spent', 0.0)


def get_admin_limit(user_id: int) -> float:
    """Get spending limit for admin (100 rubles for limited admins, unlimited for main admin)."""
    if user_id == ADMIN_ID:
        return float('inf')  # Main admin has unlimited
    admin_limits = get_admin_limits()
    admin_data = admin_limits.get(str(user_id), {})
    return admin_data.get('limit', 100.0)  # Default 100 rubles


def add_admin_spent(user_id: int, amount: float):
    """Add to admin's spent amount."""
    if user_id == ADMIN_ID:
        return  # Main admin doesn't have limits
    admin_limits = get_admin_limits()
    if str(user_id) not in admin_limits:
        return
    admin_limits[str(user_id)]['spent'] = admin_limits[str(user_id)].get('spent', 0.0) + amount
    save_admin_limits(admin_limits)


def get_admin_remaining(user_id: int) -> float:
    """Get remaining limit for admin."""
    limit = get_admin_limit(user_id)
    if limit == float('inf'):
        return float('inf')
    spent = get_admin_spent(user_id)
    return max(0.0, limit - spent)


def get_is_admin(user_id: int) -> bool:
    """
    Determine if user is admin, taking into account admin user mode.
    
    If admin is in user mode (admin_user_mode = True), returns False.
    Otherwise, returns True for admin, False for regular users.
    """
    if is_admin(user_id):
        # Check if admin is in user mode (viewing as regular user)
        if user_id in user_sessions and user_sessions[user_id].get('admin_user_mode', False):
            return False  # Show as regular user
        else:
            return True
    else:
        return False


def is_user_mode(user_id: int) -> bool:
    """
    Проверяет, находится ли админ в режиме обычного пользователя.
    
    Returns:
        True если админ в режиме пользователя, False иначе
    """
    if not is_admin(user_id):
        return False  # Не админ не может быть в режиме пользователя
    
    return user_id in user_sessions and user_sessions[user_id].get('admin_user_mode', False)


def create_user_context_for_pricing(user_id: int, has_free_generations: bool = False) -> 'UserContext':
    """
    Создает UserContext для расчета цен.
    
    ВСЕ проверки админа проходят через эту функцию.
    Запрещено передавать is_admin как bool напрямую.
    
    Args:
        user_id: ID пользователя
        has_free_generations: Есть ли у пользователя бесплатные генерации
    
    Returns:
        UserContext с правильно установленными is_admin и is_user_mode
    """
    from services.user_context_factory import create_user_context
    
    return create_user_context(
        user_id=user_id,
        is_admin_func=is_admin,
        is_user_mode_func=is_user_mode,
        has_free_generations=has_free_generations
    )


def _resolve_mode_index(model_id: str, params: Optional[dict], user_id: Optional[int]) -> int:
    """Resolve pricing mode index from session or params."""
    mode_index = None
    if params and isinstance(params, dict):
        mode_index = params.get("mode_index")
        if mode_index is None:
            mode_index = params.get("_mode_index")
    if mode_index is None and user_id is not None:
        mode_index = user_sessions.get(user_id, {}).get("mode_index")
    try:
        return int(mode_index) if mode_index is not None else 0
    except (TypeError, ValueError):
        logger.warning(
            "Invalid mode_index for model %s: %s (user_id=%s)",
            model_id,
            mode_index,
            user_id,
        )
        return 0


# COMPATIBILITY WRAPPER: calculate_price_rub для обратной совместимости
# Использует services.pricing_service.get_price() под капотом
def calculate_price_rub(model_id: str, params: dict = None, is_admin: bool = False, user_id: int = None) -> Optional[float]:
    """
    Thin-wrapper для обратной совместимости.
    Использует services.pricing_service.get_price() под капотом.
    
    Args:
        model_id: ID модели
        params: Параметры генерации
        is_admin: Является ли пользователь админом
        user_id: ID пользователя (опционально)
    
    Returns:
        Цена в рублях
    """
    try:
        from app.pricing.price_resolver import resolve_price_quote
        from app.config import get_settings

        settings = get_settings()
        mode_index = _resolve_mode_index(model_id, params, user_id)
        quote = resolve_price_quote(
            model_id=model_id,
            mode_index=mode_index,
            gen_type=None,
            selected_params=params or {},
            settings=settings,
            is_admin=is_admin,
        )
        if quote is None:
            logger.warning("Price not found for model %s", model_id)
            return None
        return float(quote.price_rub)
    except ImportError as e:
        logger.warning("Pricing resolver unavailable: %s", e)
        return None
    except Exception as e:
        logger.error(f"Error in calculate_price_rub: {e}", exc_info=True)
        return None

# Conversation states for model selection and parameter input
SELECTING_MODEL, INPUTTING_PARAMS, CONFIRMING_GENERATION = range(3)

# Payment states
SELECTING_AMOUNT, WAITING_PAYMENT_SCREENSHOT = range(3, 5)

# Admin test OCR state
ADMIN_TEST_OCR = 5

# Broadcast states
WAITING_BROADCAST_MESSAGE = 6
WAITING_CURRENCY_RATE = 7

# Store user sessions - now supports multiple concurrent generations per user
# Structure: user_sessions[user_id] = {session_data} for input/parameter collection
# Once task is created, it moves to active_generations
# NOTE: user_sessions already declared above (line 224), this is a duplicate - removed

# Store active generations - allows multiple concurrent generations per user
# Structure: active_generations[(user_id, task_id)] = {session_data}
# NOTE: active_generations already declared above (line 358), this is a duplicate - removed


def format_rub_amount(value: float) -> str:
    """Format RUB amount with 2 decimals (ROUND_HALF_UP)."""
    from app.pricing.price_resolver import format_price_rub

    return f"{format_price_rub(value)} ₽"


def format_price_rub(price: float, is_admin: bool = False) -> str:
    """Format price in rubles with appropriate text (2 decimals)."""
    price_str = format_rub_amount(price)
    if is_admin:
        return f"💰 <b>Безлимит</b> (цена: {price_str})"
    return f"💰 <b>{price_str}</b>"


def _normalize_sku_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _build_expected_sku_key(model_id: str, params: Optional[dict]) -> str:
    if not params:
        return f"{model_id}::default"
    parts = [f"{key}={_normalize_sku_param_value(params[key])}" for key in sorted(params)]
    return f"{model_id}::" + "|".join(parts)


def _format_pricing_context(settings: "Settings", is_admin: bool, user_lang: str) -> str:
    effective_multiplier = 1.0 if is_admin else settings.price_multiplier
    if user_lang == "ru":
        return f"курс {settings.usd_to_rub:.2f}, множитель {effective_multiplier:g}"
    return f"rate {settings.usd_to_rub:.2f}, multiplier {effective_multiplier:g}"


def _build_price_line(
    price_rub: float,
    settings: "Settings",
    is_admin: bool,
    user_lang: str,
    *,
    is_from: bool = False,
) -> str:
    from app.pricing.price_resolver import format_price_rub as format_price_value

    prefix = "от " if user_lang == "ru" and is_from else ("from " if user_lang != "ru" and is_from else "")
    label = "Стоимость" if user_lang == "ru" else "Price"
    price_display = format_price_value(price_rub)
    context = _format_pricing_context(settings, is_admin, user_lang)
    return f"💰 <b>{label}:</b> {prefix}{price_display} ₽ ({context})"


def _build_price_unavailable_line(user_lang: str) -> str:
    if user_lang == "ru":
        return "💰 <b>Стоимость:</b> цена временно недоступна"
    return "💰 <b>Price:</b> temporarily unavailable"


def _resolve_price_for_display(
    session: dict,
    *,
    model_id: str,
    mode_index: int,
    gen_type: Optional[str],
    params: dict,
    user_lang: str,
    is_admin: bool,
    correlation_id: Optional[str],
    update_id: Optional[int],
    action_path: str,
    user_id: Optional[int],
    chat_id: Optional[int],
) -> tuple[Optional[float], str, Optional[str]]:
    from app.config import get_settings
    from app.pricing.price_ssot import list_model_skus

    settings = get_settings()
    quote = _update_price_quote(
        session,
        model_id=model_id,
        mode_index=mode_index,
        gen_type=gen_type,
        params=params,
        correlation_id=correlation_id,
        update_id=update_id,
        action_path=action_path,
        user_id=user_id,
        chat_id=chat_id,
        is_admin=is_admin,
    )
    if quote:
        price_value = float(quote["price_rub"])
        return price_value, _build_price_line(price_value, settings, is_admin, user_lang), None

    skus = list_model_skus(model_id)
    if not skus:
        return None, _build_price_unavailable_line(user_lang), None

    min_sku = min(skus, key=lambda sku: sku.price_rub)
    price_value = float(min_sku.price_rub)
    note = (
        "ℹ️ Итоговая цена зависит от параметров."
        if user_lang == "ru"
        else "ℹ️ Final price depends on parameters."
    )
    return price_value, _build_price_line(price_value, settings, is_admin, user_lang, is_from=True), note


def get_model_price_text(model_id: str, params: dict = None, is_admin: bool = False, user_id: int = None) -> str:
    """Get formatted price text for a model (from-price for menu cards)."""
    from app.pricing.price_ssot import get_min_price

    price = calculate_price_rub(model_id, params, is_admin, user_id)
    if price is None:
        min_price = get_min_price(model_id)
        if min_price is None:
            return "💰 <b>от — ₽</b>"
        return f"💰 <b>от {format_rub_amount(float(min_price))}</b>"
    return format_price_rub(price, is_admin)


def get_from_price_value(model_id: str) -> Optional[float]:
    """Return the minimum price in RUB for a model, if available."""
    from app.pricing.price_ssot import get_min_price

    min_price = get_min_price(model_id)
    return float(min_price) if min_price is not None else None


def _normalize_gen_type(gen_type: Optional[str]) -> Optional[str]:
    if not gen_type:
        return None
    return gen_type.replace("_", "-")


UI_CONTEXT_MAIN_MENU = "MAIN_MENU"
UI_CONTEXT_GEN_TYPE_MENU = "GEN_TYPE_MENU"
UI_CONTEXT_MODEL_MENU = "MODEL_MENU"
UI_CONTEXT_FREE_TOOLS_MENU = "FREE_TOOLS_MENU"
UI_CONTEXT_WIZARD = "WIZARD"


def _derive_model_gen_type(model_spec: Any | None) -> Optional[str]:
    if model_spec is None:
        return None
    return _normalize_gen_type(
        getattr(model_spec, "model_mode", None)
        or getattr(model_spec, "model_type", None)
    )


def _resolve_session_gen_type(session: dict | None, model_spec: Any | None = None) -> Optional[str]:
    if session and session.get("active_gen_type"):
        return _normalize_gen_type(session.get("active_gen_type"))
    if session and session.get("gen_type"):
        return _normalize_gen_type(session.get("gen_type"))
    if model_spec is not None:
        return _normalize_gen_type(getattr(model_spec, "model_mode", None) or getattr(model_spec, "model_type", None))
    return None


def _model_supports_gen_type(model_spec: Any, gen_type: Optional[str]) -> bool:
    if not gen_type or not model_spec:
        return True
    expected = _normalize_gen_type(gen_type)
    supported = {
        _normalize_gen_type(getattr(model_spec, "model_mode", None)),
        _normalize_gen_type(getattr(model_spec, "model_type", None)),
    }
    return expected in supported


def _update_price_quote(
    session: dict,
    *,
    model_id: str,
    mode_index: int,
    gen_type: Optional[str],
    params: dict,
    correlation_id: Optional[str],
    update_id: Optional[int],
    action_path: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    is_admin: bool = False,
) -> Optional[dict]:
    from app.pricing.price_resolver import resolve_price_quote
    from app.config import get_settings

    def _resolve_free_tool_sku_id() -> Optional[str]:
        for free_sku in FREE_TOOL_SKU_IDS:
            if free_sku.split("::", 1)[0] == model_id:
                return free_sku
        return None

    quote = resolve_price_quote(
        model_id=model_id,
        mode_index=mode_index,
        gen_type=gen_type,
        selected_params=params or {},
        settings=get_settings(),
        is_admin=is_admin,
    )
    if quote is None:
        free_sku_id = _resolve_free_tool_sku_id()
        if free_sku_id:
            session["price_quote"] = {
                "price_rub": "0.00",
                "currency": "RUB",
                "breakdown": {
                    "model_id": model_id,
                    "mode_index": mode_index,
                    "gen_type": gen_type,
                    "params": dict(params or {}),
                    "sku_id": free_sku_id,
                    "unit": "free",
                    "free_fallback": True,
                },
            }
            session["sku_id"] = free_sku_id
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="PRICE_RESOLVED",
                action_path=action_path,
                model_id=model_id,
                gen_type=gen_type,
                stage="PRICE_RESOLVE",
                outcome="resolved",
                param={
                    "price_rub": "0.00",
                    "mode_index": mode_index,
                    "params": params or {},
                    "free_fallback": True,
                },
            )
            return session["price_quote"]
        session["price_quote"] = None
        try:
            from app.pricing.price_ssot import PRICING_SSOT_PATH, list_model_skus
        except Exception as exc:
            logger.debug("PRICING_SSOT_IMPORT_FALLBACK error=%s - using defaults", exc)
            PRICING_SSOT_PATH = "data/kie_pricing_rub.yaml"
            list_model_skus = None
        skus = list_model_skus(model_id) if list_model_skus else []
        if not skus:
            expected_sku = _build_expected_sku_key(model_id, params)
            logger.warning(
                "Missing pricing for SKU %s in %s",
                expected_sku,
                PRICING_SSOT_PATH,
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="PRICE_MISSING_RULE",
                action_path=action_path,
                model_id=model_id,
                gen_type=gen_type,
                stage="PRICE_RESOLVE",
                outcome="missing",
                error_code="PRICE_MISSING_RULE",
                fix_hint="pricing ssot missing SKU mapping; check params and catalog.",
                param={
                    "mode_index": mode_index,
                    "params": params or {},
                },
            )
            return None
        
        # FALLBACK: Если экзактный SKU не найден, используем минимальную цену из доступных SKUs
        if not quote:
            min_sku = min(skus, key=lambda sku: float(sku.price_rub))
            session["price_quote"] = {
                "price_rub": f"{min_sku.price_rub:.2f}",
                "currency": "RUB",
                "breakdown": {
                    "model_id": model_id,
                    "mode_index": mode_index,
                    "gen_type": gen_type,
                    "params": dict(params or {}),
                    "sku_id": min_sku.sku_key,
                    "unit": min_sku.unit,
                    "fallback_min_price": True,
                },
            }
            session["sku_id"] = min_sku.sku_key
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="PRICE_RESOLVED",
                action_path=action_path,
                model_id=model_id,
                gen_type=gen_type,
                stage="PRICE_RESOLVE",
                outcome="resolved_fallback",
                param={
                    "price_rub": f"{min_sku.price_rub:.2f}",
                    "mode_index": mode_index,
                    "params": params or {},
                    "fallback_min_price": True,
                },
            )
            return session["price_quote"]
    session["price_quote"] = {
        "price_rub": f"{quote.price_rub:.2f}",
        "currency": quote.currency,
        "breakdown": quote.breakdown,
    }
    session["sku_id"] = quote.sku_id
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        action="PRICE_RESOLVED",
        action_path=action_path,
        model_id=model_id,
        gen_type=gen_type,
        stage="PRICE_RESOLVE",
        outcome="resolved",
        param={
            "price_rub": f"{quote.price_rub:.2f}",
            "mode_index": mode_index,
            "params": params or {},
        },
    )
    return session["price_quote"]


def _build_current_price_line(
    session: dict,
    *,
    user_lang: str,
    model_id: str,
    mode_index: int,
    gen_type: Optional[str],
    params: dict,
    correlation_id: Optional[str],
    update_id: Optional[int],
    action_path: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    is_admin: bool = False,
) -> str:
    from app.pricing.price_resolver import format_price_rub as format_price_value

    quote = session.get("price_quote")
    if quote is None:
        quote = _update_price_quote(
            session,
            model_id=model_id,
            mode_index=mode_index,
            gen_type=gen_type,
            params=params,
            correlation_id=correlation_id,
            update_id=update_id,
            action_path=action_path,
            user_id=user_id,
            chat_id=chat_id,
            is_admin=is_admin,
        )
    if not quote:
        price_text = "Цена: уточняется" if user_lang == "ru" else "Price: уточняется"
    else:
        breakdown = quote.get("breakdown", {}) if isinstance(quote, dict) else {}
        price_value = quote.get("price_rub") if isinstance(quote, dict) else None
        is_free = bool(breakdown.get("free_sku")) or str(price_value) in {"0", "0.0", "0.00"}
        if price_value is None:
            price_text = "Цена: уточняется" if user_lang == "ru" else "Price: уточняется"
        elif is_free:
            price_text = "🎁 Бесплатно" if user_lang == "ru" else "🎁 Free"
        else:
            formatted_price = format_price_value(price_value)
            if user_lang == "ru":
                price_text = f"Цена по прайсу: {formatted_price} ₽"
            else:
                price_text = f"Price (RUB): {formatted_price} ₽"
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        action="PRICE_SHOWN",
        action_path=action_path,
        model_id=model_id,
        gen_type=gen_type,
        stage="PRICE_DISPLAY",
        outcome="shown",
        param={
            "mode_index": mode_index,
            "params": params or {},
            "price_text": price_text,
        },
    )
    return price_text


def build_option_confirm_text(
    user_lang: str,
    param_label: str,
    display_value: str,
    price_rub: float,
) -> str:
    price_line = f"{price_rub:.2f} ₽"
    if user_lang == "ru":
        return (
            f"✅ {param_label}: <b>{display_value}</b>\n"
            f"💰 <b>Эта опция:</b> {price_line}\n\n"
            "Подтвердить выбор?"
        )
    return (
        f"✅ {param_label}: <b>{display_value}</b>\n"
        f"💰 <b>This option:</b> {price_line}\n\n"
        "Confirm selection?"
    )


def _build_price_preview_text(user_lang: str, price: float, balance: float) -> str:
    after_balance = balance - price
    price_str = format_rub_amount(price)
    balance_str = format_rub_amount(balance)
    after_str = format_rub_amount(max(after_balance, 0))
    rounding_note = (
        "💡 <i>Цена округляется до копеек (0.01 ₽).</i>"
        if user_lang == "ru"
        else "💡 <i>Prices are rounded to 0.01 ₽.</i>"
    )
    if user_lang == "ru":
        return (
            "🧾 <b>Перед запуском</b>\n\n"
            f"💰 <b>Стоимость:</b> {price_str}\n"
            f"💳 <b>Баланс:</b> {balance_str}\n"
            f"✅ <b>После списания:</b> {after_str}\n\n"
            f"{rounding_note}"
        )
    return (
        "🧾 <b>Before we start</b>\n\n"
        f"💰 <b>Price:</b> {price_str}\n"
        f"💳 <b>Balance:</b> {balance_str}\n"
        f"✅ <b>After charge:</b> {after_str}\n\n"
        f"{rounding_note}"
    )


def _build_insufficient_funds_text(user_lang: str, price: float, balance: float) -> str:
    price_str = format_rub_amount(price)
    balance_str = format_rub_amount(balance)
    needed_str = format_rub_amount(max(price - balance, 0))
    rounding_note = (
        "💡 <i>Цена округляется до копеек (0.01 ₽).</i>"
        if user_lang == "ru"
        else "💡 <i>Prices are rounded to 0.01 ₽.</i>"
    )
    if user_lang == "ru":
        return (
            "❌ <b>Недостаточно средств</b>\n\n"
            f"💰 <b>Стоимость:</b> {price_str}\n"
            f"💳 <b>Баланс:</b> {balance_str}\n"
            f"❌ <b>Не хватает:</b> {needed_str}\n\n"
            f"{rounding_note}\n\n"
            "Что можно сделать:\n"
            "• Пополнить баланс\n"
            "• Посмотреть способы оплаты\n"
            "• Написать в поддержку"
        )
    return (
        "❌ <b>Insufficient funds</b>\n\n"
        f"💰 <b>Price:</b> {price_str}\n"
        f"💳 <b>Balance:</b> {balance_str}\n"
        f"❌ <b>Missing:</b> {needed_str}\n\n"
        f"{rounding_note}\n\n"
        "What you can do:\n"
        "• Top up your balance\n"
        "• See payment options\n"
        "• Contact support"
    )


def _build_insufficient_funds_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(t('btn_check_balance', lang=user_lang), callback_data="check_balance")],
        [
            InlineKeyboardButton(
                "💳 Как оплатить" if user_lang == "ru" else "💳 How to pay",
                callback_data="topup_balance",
            )
        ],
        [InlineKeyboardButton(t('btn_support', lang=user_lang), callback_data="support_contact")],
        [InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _build_mode_selection_text(model_name: str, user_lang: str) -> str:
    if user_lang == "ru":
        return (
            "🧩 <b>Выберите режим генерации</b>\n\n"
            f"🤖 <b>Модель:</b> {model_name}\n\n"
            "Цена и списание зависят от режима."
        )
    return (
        "🧩 <b>Select a generation mode</b>\n\n"
        f"🤖 <b>Model:</b> {model_name}\n\n"
        "Price and charge depend on the mode."
    )


def _build_mode_selection_keyboard(model_id: str, modes: List[Any], user_lang: str) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for index, mode in enumerate(modes):
        label = _resolve_mode_label(mode, index, user_lang)
        buttons.append([InlineKeyboardButton(label, callback_data=f"select_mode:{model_id}:{index}")])
    buttons.append([InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)


def _build_kie_request_failed_message(
    status: Optional[int],
    user_lang: str,
    user_message: Optional[str] = None,
) -> str:
    if user_message:
        return user_message
    if status == 401:
        return (
            "❌ <b>Неверный ключ</b>\n\n"
            "Проверьте KIE_API_KEY в ENV (Render/Timeweb) и перезапустите сервис."
            if user_lang == "ru"
            else "❌ <b>Authorization issue</b>\n\nCheck KIE_API_KEY in ENV and restart the service."
        )
    if status == 402:
        return (
            "⚠️ <b>Недостаточно средств на KIE аккаунте</b>\n\n"
            "Пополните баланс KIE аккаунта и попробуйте снова."
            if user_lang == "ru"
            else "⚠️ <b>KIE account has insufficient credits</b>\n\nPlease top up and try again."
        )
    if status == 422:
        return (
            "⚠️ <b>Ошибка параметров модели</b>\n\n"
            "Проверьте значения параметров и попробуйте снова."
            if user_lang == "ru"
            else "⚠️ <b>Check the parameters</b>\n\nSome values are invalid. Please adjust your request."
        )
    if status == 429:
        return (
            "⏳ <b>Слишком много запросов</b>\n\n"
            "Очередь перегружена. Попробуйте через пару минут."
            if user_lang == "ru"
            else "⏳ <b>Too many requests</b>\n\nQueue is busy. Please try again in a few minutes."
        )
    if status == 500:
        return (
            "❌ <b>Ошибка сервера</b>\n\n"
            "Мы уже ищем причину. Попробуйте позже."
            if user_lang == "ru"
            else "❌ <b>Server error</b>\n\nWe're investigating. Please try again later."
        )
    return (
        "❌ <b>Не удалось запустить генерацию</b>\n\nПопробуйте позже."
        if user_lang == "ru"
        else "❌ <b>Could not start generation</b>\n\nPlease try again later."
    )

# Broadcast states
WAITING_BROADCAST_MESSAGE = 6
WAITING_CURRENCY_RATE = 7

# Helper functions for balance management

# Data directory - use environment variable or default to ./data
# This allows mounting a volume for persistent storage
DATA_DIR = os.getenv('DATA_DIR', './data')
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"✅ Created local data directory (cache/fallback): {DATA_DIR}")
    except Exception as e:
        logger.error(f"❌ Failed to create data directory {DATA_DIR}: {e}")
        # Fallback to current directory if data dir creation fails
        DATA_DIR = '.'
        logger.warning(f"⚠️ Using current directory for data storage")


def get_data_file_path(filename: str) -> str:
    """Get full path to data file, ensuring directory exists."""
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / filename)


# NOTE: active_generations already declared above (line 358), this is a duplicate - removed

# File operation locks to prevent race conditions (using threading.Lock for sync operations)
_file_locks = {
    'balances': threading.Lock(),
    'generations_history': threading.Lock(),
    'referrals': threading.Lock(),
    'promocodes': threading.Lock(),
    'free_generations': threading.Lock(),
    'languages': threading.Lock(),
    'gifts': threading.Lock(),
    'payments': threading.Lock(),
    'broadcasts': threading.Lock(),
    'admin_limits': threading.Lock(),
    'blocked_users': threading.Lock(),
    'user_registry': threading.Lock()
}

# In-memory cache for frequently accessed data (optimized for 1000+ users)
_data_cache = {
    'balances': {},
    'free_generations': {},
    'languages': {},
    'gifts': {},
    'user_registry': {},
    'cache_timestamps': {}
}

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300
_last_save_time = {}

# Data directory - use environment variable or default to ./data
# This allows mounting a volume for persistent storage
DATA_DIR = os.getenv('DATA_DIR', './data')
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"✅ Created local data directory (cache/fallback): {DATA_DIR}")
    except Exception as e:
        logger.error(f"❌ Failed to create data directory {DATA_DIR}: {e}")
        # Fallback to current directory if data dir creation fails
        DATA_DIR = '.'
        logger.warning(f"⚠️ Using current directory for data storage")

def get_data_file_path(filename: str) -> str:
    """Get full path to data file, ensuring directory exists."""
    if DATA_DIR == '.':
        return filename
    return os.path.join(DATA_DIR, filename)

# Payment data files - all stored in DATA_DIR for persistence
BALANCES_FILE = get_data_file_path("user_balances.json")
USER_LANGUAGES_FILE = get_data_file_path("user_languages.json")
GIFT_CLAIMED_FILE = get_data_file_path("gift_claimed.json")
ADMIN_LIMITS_FILE = get_data_file_path("admin_limits.json")  # File to store admins with spending limits
PAYMENTS_FILE = get_data_file_path("payments.json")
BLOCKED_USERS_FILE = get_data_file_path("blocked_users.json")
FREE_GENERATIONS_FILE = get_data_file_path("daily_free_generations.json")  # File to store daily free generations
PROMOCODES_FILE = get_data_file_path("promocodes.json")  # File to store promo codes
CURRENCY_RATE_FILE = get_data_file_path("currency_rate.json")  # File to store USD to RUB exchange rate
REFERRALS_FILE = get_data_file_path("referrals.json")  # File to store referral data
BROADCASTS_FILE = get_data_file_path("broadcasts.json")  # File to store broadcast statistics
GENERATIONS_HISTORY_FILE = get_data_file_path("generations_history.json")  # File to store user generation history
USER_REGISTRY_FILE = get_data_file_path("user_registry.json")

# Free tools settings
FREE_TOOLS_CONFIG = get_free_tools_config()
FREE_TOOL_SKU_IDS = get_free_tools_model_ids()
FREE_TOOL_MODEL_IDS = [sku_id.split("::", 1)[0] for sku_id in FREE_TOOL_SKU_IDS]
FREE_SKU_ID = FREE_TOOL_SKU_IDS[0] if FREE_TOOL_SKU_IDS else ""

def is_video_model(model_id: str) -> bool:
    """Check if model is a video generation model"""
    video_keywords = ['video', 'animate', 'avatar', 'speech-to-video']
    return any(keyword in model_id.lower() for keyword in video_keywords)

def is_audio_model(model_id: str) -> bool:
    """Check if model is an audio processing model"""
    audio_keywords = ['speech-to-text', 'audio', 'transcribe']
    return any(keyword in model_id.lower() for keyword in audio_keywords)


def get_generation_timeout_seconds(model_spec: Any) -> int:
    """Determine generation timeout per model category."""
    model_mode = (getattr(model_spec, "model_mode", "") or "").lower()
    output_media = (getattr(model_spec, "output_media_type", "") or "").lower()
    if "video" in model_mode or output_media == "video":
        return int(os.getenv("KIE_TIMEOUT_VIDEO", "420"))
    if any(token in model_mode for token in ("audio", "speech")) or output_media in {"audio", "voice"}:
        return int(os.getenv("KIE_TIMEOUT_AUDIO", "180"))
    return int(os.getenv("KIE_TIMEOUT_IMAGE", "180"))
FREE_GENERATIONS_PER_DAY = FREE_TOOLS_CONFIG.base_per_day
REFERRAL_BONUS_GENERATIONS = FREE_TOOLS_CONFIG.referral_bonus  # Bonus generations for inviting a user

# Инициализация констант в helpers
set_constants(FREE_GENERATIONS_PER_DAY, REFERRAL_BONUS_GENERATIONS, ADMIN_ID)


# ==================== Payment System Functions ====================

def get_cache_key(filename: str) -> str:
    """Get cache key for filename."""
    cache_map = {
        BALANCES_FILE: 'balances',
        FREE_GENERATIONS_FILE: 'free_generations',
        USER_LANGUAGES_FILE: 'languages',
        GIFT_CLAIMED_FILE: 'gifts',
        REFERRALS_FILE: 'referrals',
        PROMOCODES_FILE: 'promocodes',
        GENERATIONS_HISTORY_FILE: 'generations_history',
        PAYMENTS_FILE: 'payments',
        BROADCASTS_FILE: 'broadcasts',
        ADMIN_LIMITS_FILE: 'admin_limits',
        BLOCKED_USERS_FILE: 'blocked_users',
        USER_REGISTRY_FILE: 'user_registry'
    }
    return cache_map.get(filename, filename)

def load_json_file(filename: str, default: dict = None) -> dict:
    """Load JSON file with caching and locking for performance (optimized for 1000+ users).
    Automatically creates file if it doesn't exist (for critical files)."""
    if default is None:
        default = {}
    
    cache_key = get_cache_key(filename)
    current_time = time.time()
    
    # Check cache first (thread-safe read)
    if cache_key in _data_cache['cache_timestamps']:
        cache_time = _data_cache['cache_timestamps'][cache_key]
        if current_time - cache_time < CACHE_TTL and cache_key in _data_cache:
            if cache_key != filename:  # Only for mapped cache keys
                cached_data = _data_cache.get(cache_key)
                if cached_data is not None:
                    return cached_data.copy()
    
    # Get lock for this file type
    lock_key = cache_key if cache_key in _file_locks else 'balances'  # Default to balances lock
    lock = _file_locks.get(lock_key, _file_locks['balances'])
    
    # Load from file with lock to prevent race conditions
    with lock:
        try:
            try:
                from app.storage.factory import get_storage

                storage = get_storage()
                storage_filename = os.path.basename(filename)
                data = _run_storage_coro_sync(
                    storage.read_json_file(storage_filename, default),
                    label=f"read:{storage_filename}",
                )
                if cache_key != filename:
                    _data_cache[cache_key] = data.copy()
                    _data_cache['cache_timestamps'][cache_key] = current_time
                return data
            except Exception as storage_error:
                logger.warning(
                    "Storage read failed for %s, falling back to local cache: %s",
                    filename,
                    storage_error,
                )

            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Update cache (thread-safe)
                    if cache_key != filename:
                        _data_cache[cache_key] = data.copy()
                        _data_cache['cache_timestamps'][cache_key] = current_time
                    return data
            else:
                # For critical files, create empty file if it doesn't exist
                critical_files = [BALANCES_FILE, GENERATIONS_HISTORY_FILE, PAYMENTS_FILE]
                if filename in critical_files:
                    try:
                        # Ensure directory exists
                        dir_path = os.path.dirname(filename)
                        if dir_path and not os.path.exists(dir_path):
                            os.makedirs(dir_path, exist_ok=True)
                        
                        # Create empty file
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(default, f, ensure_ascii=False, indent=2)
                        logger.info(f"✅ Auto-created missing critical file: {filename}")
                        return default
                    except Exception as e:
                        logger.error(f"Error auto-creating critical file {filename}: {e}")
                        return default
                return default
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error in {filename}: {e}. File may be corrupted. Returning default.")
            # Try to backup corrupted file
            try:
                backup_name = filename + '.corrupted.' + str(int(time.time()))
                if os.path.exists(filename):
                    os.rename(filename, backup_name)
                    logger.warning(f"Backed up corrupted file to {backup_name}")
            except:
                pass
            return default
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}", exc_info=True)
            return default


def save_json_file(filename: str, data: dict, use_cache: bool = True):
    """Save data to JSON file with batched writes (optimized for 1000+ users).
    Guarantees data persistence for critical files."""
    try:
        cache_key = get_cache_key(filename)
        current_time = time.time()
        
        # Update cache immediately
        if use_cache and cache_key != filename:
            _data_cache[cache_key] = data.copy()
            _data_cache['cache_timestamps'][cache_key] = current_time
        
        # Batch writes: only save if enough time passed (reduce I/O)
        # For critical files (balances, generations history, payments, gift claims), save immediately always
        critical_files = [BALANCES_FILE, GENERATIONS_HISTORY_FILE, PAYMENTS_FILE, GIFT_CLAIMED_FILE]
        is_critical = filename in critical_files
        
        if not is_critical and filename in _last_save_time:
            time_since_last_save = current_time - _last_save_time[filename]
            # For non-critical files, batch every 2 seconds max
            if time_since_last_save < 2.0:
                return  # Skip write, will be saved later or by batch save

        try:
            from app.storage.factory import get_storage

            storage = get_storage()
            storage_filename = os.path.basename(filename)
            _run_storage_coro_sync(
                storage.write_json_file(storage_filename, data),
                label=f"write:{storage_filename}",
            )
        except Exception as storage_error:
            logger.error(
                "Storage write failed for %s, falling back to local cache: %s",
                filename,
                storage_error,
                exc_info=True,
            )
        
        # Ensure directory exists (for subdirectories like knowledge_store)
        dir_path = os.path.dirname(filename)
        if dir_path and not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
            except Exception as e:
                logger.error(f"Error creating directory {dir_path}: {e}")
        
        # Perform actual write with atomic operation (write to temp file, then rename)
        temp_filename = filename + '.tmp'
        try:
            # Write to temporary file first
            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()  # Force write to disk immediately
                if hasattr(os, 'fsync'):
                    os.fsync(f.fileno())  # Force sync to disk (Unix/Linux)
            
            # Atomic rename (works on Unix/Linux/Windows)
            if os.path.exists(filename):
                os.replace(temp_filename, filename)
            else:
                os.rename(temp_filename, filename)
            
            # Verify file was written correctly
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                if file_size == 0:
                    logger.error(f"❌ CRITICAL: {filename} was written but is empty!")
                else:
                    logger.debug(f"✅ Saved {filename} ({file_size} bytes)")
            else:
                logger.error(f"❌ CRITICAL: {filename} does not exist after save!")
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except:
                    pass
            raise e
        
        _last_save_time[filename] = current_time
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR saving {filename}: {e}", exc_info=True)
        # For critical files, try one more time
        if filename in critical_files:
            try:
                logger.warning(f"Retrying save for critical file {filename}...")
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    if hasattr(os, 'fsync'):
                        os.fsync(f.fileno())
                logger.info(f"✅ Retry successful for {filename}")
            except Exception as retry_error:
                logger.error(f"❌ Retry failed for {filename}: {retry_error}", exc_info=True)


def upsert_user_registry_entry(user: Optional["telegram.User"]) -> None:
    """Store basic user identity for admin lookup."""
    if user is None:
        return
    try:
        user_id = user.id
        username = user.username or ""
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        data = load_json_file(USER_REGISTRY_FILE, {})
        user_key = str(user_id)
        existing = data.get(user_key, {})
        if (
            existing.get("username") == username
            and existing.get("first_name") == first_name
            and existing.get("last_name") == last_name
        ):
            return
        data[user_key] = {
            **existing,
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "updated_at": datetime.now().isoformat(),
        }
        save_json_file(USER_REGISTRY_FILE, data, use_cache=True)
    except Exception as e:
        logger.error(f"❌ Failed to update user registry: {e}", exc_info=True)


def get_user_registry_entry(user_id: int) -> dict:
    """Get stored user identity if available."""
    data = load_json_file(USER_REGISTRY_FILE, {})
    return data.get(str(user_id), {})


async def build_admin_user_overview(target_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build admin overview text and keyboard for a user."""
    registry_entry = get_user_registry_entry(target_user_id)
    username = registry_entry.get("username") or ""
    first_name = registry_entry.get("first_name") or ""
    last_name = registry_entry.get("last_name") or ""
    full_name = " ".join([name for name in [first_name, last_name] if name]).strip() or "—"
    username_text = f"@{username}" if username else "—"

    balance = await get_user_balance_async(target_user_id)
    balance_str = format_rub_amount(balance)
    user_payments = get_user_payments(target_user_id)
    total_paid = sum(p.get("amount", 0) for p in user_payments)
    total_paid_str = format_rub_amount(total_paid)

    lines = [
        f"👤 <b>Пользователь:</b> {target_user_id}",
        f"🧾 <b>Ник:</b> {username_text}",
        f"📛 <b>Имя:</b> {full_name}",
        f"💰 <b>Баланс:</b> {balance_str}",
        f"💵 <b>Пополнено всего:</b> {total_paid_str}",
        f"📝 <b>Платежей:</b> {len(user_payments)}",
    ]

    if user_payments:
        lines.append("\n<b>Последние пополнения:</b>")
        for payment in user_payments[:5]:
            amount_str = format_rub_amount(payment.get("amount", 0))
            timestamp = payment.get("timestamp")
            if timestamp:
                dt = datetime.fromtimestamp(timestamp)
                date_str = dt.strftime("%d.%m.%Y %H:%M")
            else:
                date_str = "Неизвестно"
            lines.append(f"• {amount_str} | {date_str}")

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Начислить баланс", callback_data=f"admin_topup_user:{target_user_id}")],
            [InlineKeyboardButton("🔄 Обновить", callback_data=f"admin_user_info:{target_user_id}")],
            [InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")],
        ]
    )
    return text, keyboard


async def get_http_client() -> aiohttp.ClientSession:
    """Get or create global HTTP client with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.closed:
        connector = aiohttp.TCPConnector(
            limit=100,  # Max connections
            limit_per_host=30,  # Max connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        _http_client = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'TelegramBot/1.0'}
        )
    return _http_client


async def cleanup_http_client():
    """Close HTTP client on shutdown."""
    global _http_client
    if _http_client and not _http_client.closed:
        await _http_client.close()
        _http_client = None


async def cleanup_storage():
    """Close storage sessions on shutdown."""
    try:
        from app.storage.factory import get_storage

        storage_instance = get_storage()
        close_method = getattr(storage_instance, "close", None)
        if close_method:
            result = close_method()
            if asyncio.iscoroutine(result):
                await result
    except Exception as exc:
        logger.warning("Failed to close storage cleanly: %s", exc)


def cleanup_old_sessions(max_age_seconds: int = 3600):
    """Clean up old user sessions to prevent memory leaks (optimized for 1000+ users)."""
    current_time = time.time()
    keys_to_remove = []
    
    for user_id, session in user_sessions.items():
        session_time = session.get('last_activity', current_time)
        if current_time - session_time > max_age_seconds:
            keys_to_remove.append(user_id)
    
    for key in keys_to_remove:
        del user_sessions[key]
    
    if keys_to_remove:
        logger.info(f"Cleaned up {len(keys_to_remove)} old user sessions")


def update_session_activity(user_id: int):
    """Update last activity time for user session."""
    if user_id in user_sessions:
        user_sessions[user_id]['last_activity'] = time.time()


def _clear_session_flow_keys(session: dict, *, clear_gen_type: bool) -> list[str]:
    cleared_keys: list[str] = []
    for key in (
        "waiting_for",
        "current_param",
        "model_id",
        "model_info",
        "model_spec",
        "param_history",
        "param_order",
        "params",
        "properties",
        "required",
        "required_original",
        "required_forced_media",
        "optional_media_params",
        "image_ref_prompt",
        "ssot_conflicts",
        "skipped_params",
        "payment_method",
        "topup_amount",
        "stars_amount",
        "invoice_payload",
        "balance_charged",
        "active_model_id",
    ):
        if key in session:
            session.pop(key, None)
            cleared_keys.append(key)
    if clear_gen_type:
        for key in ("active_gen_type", "gen_type"):
            if key in session:
                session.pop(key, None)
                cleared_keys.append(key)
    return cleared_keys


def reset_session_context(
    user_id: int,
    *,
    reason: str,
    clear_gen_type: bool,
    correlation_id: Optional[str] = None,
    update_id: Optional[int] = None,
    chat_id: Optional[int] = None,
) -> None:
    """Clear flow-specific session data when user navigates to a new context."""
    if user_id not in user_sessions:
        return
    session = user_sessions[user_id]
    from_context = session.get("ui_context")
    cleared_keys = _clear_session_flow_keys(session, clear_gen_type=clear_gen_type)
    if cleared_keys:
        logger.info(
            "🧹 SESSION_RESET: action_path=%s cleared=%s",
            reason,
            ",".join(cleared_keys),
        )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        action="SESSION_CONTEXT_RESET",
        action_path=reason,
        model_id=session.get("active_model_id") or session.get("model_id"),
        gen_type=session.get("active_gen_type") or session.get("gen_type"),
        stage="SESSION",
        outcome="cleared" if cleared_keys else "no_op",
        param={
            "from_context": from_context,
            "to_context": session.get("ui_context"),
            "cleared_keys": cleared_keys,
        },
    )
    if session.get("model_id") is None and any(
        key in session for key in ("params", "properties", "required", "waiting_for", "current_param")
    ):
        clear_user_session(user_id, reason=f"{reason}:stale_model_id")


def set_session_context(
    user_id: int,
    *,
    to_context: str,
    reason: str,
    active_gen_type: Optional[str] = None,
    active_model_id: Optional[str] = None,
    clear_gen_type: bool = False,
    correlation_id: Optional[str] = None,
    update_id: Optional[int] = None,
    chat_id: Optional[int] = None,
) -> None:
    session = user_sessions.ensure(user_id)
    from_context = session.get("ui_context")
    if clear_gen_type:
        for key in ("active_gen_type", "gen_type"):
            session.pop(key, None)
    if active_gen_type is not None:
        session["active_gen_type"] = active_gen_type
        session["gen_type"] = active_gen_type
    if active_model_id is not None:
        session["active_model_id"] = active_model_id
    session["ui_context"] = to_context
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        action="SESSION_CONTEXT_SET",
        action_path=reason,
        model_id=session.get("active_model_id") or session.get("model_id"),
        gen_type=session.get("active_gen_type") or session.get("gen_type"),
        stage="SESSION",
        outcome="updated",
        param={
            "from_context": from_context,
            "to_context": to_context,
            "cleared_keys": ["active_gen_type", "gen_type"] if clear_gen_type else [],
        },
    )


def reset_session_on_navigation(user_id: int, *, reason: str) -> None:
    """Backward-compatible wrapper for legacy reset semantics."""
    reset_session_context(user_id, reason=reason, clear_gen_type=False)


def clear_user_session(user_id: int, *, reason: str) -> None:
    """Hard reset session state to avoid stale keys."""
    session = user_sessions.get(user_id)
    if session is None:
        return
    session.clear()
    session["last_activity"] = time.time()
    logger.info("🧹 SESSION_RESET_FULL: action_path=%s user_id=%s", reason, user_id)


def _acquire_generation_submit_lock(user_id: int) -> bool:
    now = time.time()
    last = generation_submit_locks.get(user_id)
    if last and now - last < GENERATION_SUBMIT_LOCK_TTL_SECONDS:
        return False
    generation_submit_locks[user_id] = now
    return True


def _release_generation_submit_lock(user_id: int) -> None:
    generation_submit_locks.pop(user_id, None)

def _cleanup_processed_updates(now_ts: float) -> None:
    expired = [
        update_id
        for update_id, ts in _processed_update_ids.items()
        if now_ts - ts > _processed_update_ttl_seconds
    ]
    for update_id in expired:
        _processed_update_ids.pop(update_id, None)


def _should_dedupe_update(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    action_path: str,
    user_id: Optional[int],
    chat_id: Optional[int],
) -> bool:
    update_id = getattr(update, "update_id", None)
    if update_id is None:
        return False
    now_ts = time.time()
    _cleanup_processed_updates(now_ts)
    if update_id in _processed_update_ids:
        correlation_id = ensure_correlation_id(update, context)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action=action,
            action_path=action_path,
            stage="dedup",
            outcome="deduped",
            error_code=None,
            fix_hint="duplicate_update_id",
        )
        return True
    _processed_update_ids[update_id] = now_ts
    return False


def _guard_sync_wrapper_in_event_loop(wrapper_name: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if loop.is_running():
        import traceback

        stack = "".join(traceback.format_stack(limit=12))
        logger.error(
            "SYNC_WRAPPER_CALLED_IN_ASYNC wrapper=%s stack=%s",
            wrapper_name,
            stack,
        )
        raise RuntimeError(f"{wrapper_name} called inside running event loop")


_storage_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_storage_coro_sync(coro, *, label: str = "storage_call"):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = _storage_executor.submit(lambda: asyncio.run(coro))
    try:
        return future.result(timeout=STORAGE_IO_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError as exc:
        logger.error(
            "SYNC_STORAGE_CALL_TIMEOUT label=%s timeout=%.2fs",
            label,
            STORAGE_IO_TIMEOUT_SECONDS,
        )
        raise TimeoutError(f"{label} timed out after {STORAGE_IO_TIMEOUT_SECONDS}s") from exc
    except Exception as exc:
        logger.error("SYNC_STORAGE_CALL_FAILED label=%s error=%s", label, exc, exc_info=True)
        raise


def get_user_balance(user_id: int) -> float:
    """Get user balance in rubles (synchronous wrapper for storage)."""
    import asyncio
    from app.services.user_service import get_user_balance as get_balance_async

    _guard_sync_wrapper_in_event_loop("get_user_balance")
    try:
        return asyncio.run(get_balance_async(user_id))
    except Exception as e:
        logger.error(f"❌ Error getting user balance: {e}", exc_info=True)
        return 0.0


def set_user_balance(user_id: int, amount: float):
    """Set user balance in rubles (synchronous wrapper for storage)."""
    # Use storage layer through async wrapper (blocking call)
    import asyncio
    from app.services.user_service import set_user_balance as set_balance_async
    logger.info(f"💰💰💰 SET_BALANCE: user_id={user_id}, amount={amount:.2f} ₽")

    _guard_sync_wrapper_in_event_loop("set_user_balance")
    try:
        asyncio.run(set_balance_async(user_id, amount))
    except Exception as e:
        logger.error(f"❌ Error setting user balance: {e}", exc_info=True)


def add_user_balance(user_id: int, amount: float) -> float:
    """Add amount to user balance, return new balance (synchronous wrapper for storage)."""
    # Use storage layer through async wrapper (blocking call)
    import asyncio
    from app.services.user_service import add_user_balance as add_balance_async
    logger.info(f"💰💰💰 ADD_BALANCE: user_id={user_id}, amount={amount:.2f} ₽")

    _guard_sync_wrapper_in_event_loop("add_user_balance")
    try:
        return asyncio.run(add_balance_async(user_id, amount))
    except Exception as e:
        logger.error(f"❌ Error adding user balance: {e}", exc_info=True)
        return get_user_balance(user_id)  # Return current balance on error


def subtract_user_balance(user_id: int, amount: float) -> bool:
    """Subtract amount from user balance. Returns True if successful, False if insufficient funds (synchronous wrapper for storage)."""
    # Use storage layer through async wrapper (blocking call)
    import asyncio
    from app.services.user_service import subtract_user_balance as subtract_balance_async

    _guard_sync_wrapper_in_event_loop("subtract_user_balance")
    try:
        return asyncio.run(subtract_balance_async(user_id, amount))
    except Exception as e:
        logger.error(f"❌ Error subtracting user balance: {e}", exc_info=True)
        return False


# ==================== Async wrappers for storage operations ====================
# These use storage layer (async) - no blocking operations

async def get_user_balance_async(user_id: int) -> float:
    """Async get user balance using storage layer."""
    from app.services.user_service import get_user_balance as get_balance_async
    return await get_balance_async(user_id)


async def set_user_balance_async(user_id: int, amount: float):
    """Async set user balance using storage layer."""
    from app.services.user_service import set_user_balance as set_balance_async
    await set_balance_async(user_id, amount)


async def add_user_balance_async(user_id: int, amount: float) -> float:
    """Async add to user balance using storage layer."""
    from app.services.user_service import add_user_balance as add_balance_async
    return await add_balance_async(user_id, amount)


async def subtract_user_balance_async(user_id: int, amount: float) -> bool:
    """Async subtract from user balance using storage layer."""
    from app.services.user_service import subtract_user_balance as subtract_balance_async
    return await subtract_balance_async(user_id, amount)


def db_update_user_balance(user_id: int, amount: float):
    """
    Обновляет баланс пользователя напрямую в БД (для тестов/диагностики).
    Используется для ручного управления балансом.
    
    Args:
        user_id: ID пользователя
        amount: Новый баланс
    """
    logger.info(f"db_update_user_balance: user_id={user_id}, amount={amount:.2f} ₽")
    set_user_balance(user_id, amount)


# ==================== User Language System ====================

# Кэш для языков пользователей (для производительности)
_user_language_cache = {}
_user_language_cache_time = {}
CACHE_TTL_LANGUAGE = 300  # 5 минут

def get_user_language(user_id: int) -> str:
    """Get user language preference (default: 'ru') with caching."""
    user_key = str(user_id)
    
    # Проверяем кэш
    current_time = time.time()
    if user_key in _user_language_cache:
        cache_time = _user_language_cache_time.get(user_key, 0)
        if current_time - cache_time < CACHE_TTL_LANGUAGE:
            return _user_language_cache[user_key]
    
    # Загружаем из файла
    languages = load_json_file(USER_LANGUAGES_FILE, {})
    lang = languages.get(user_key, 'ru')  # Default to Russian
    
    # Обновляем кэш
    _user_language_cache[user_key] = lang
    _user_language_cache_time[user_key] = current_time
    
    return lang

def has_user_language_set(user_id: int) -> bool:
    """Check if user has explicitly set their language preference."""
    languages = load_json_file(USER_LANGUAGES_FILE, {})
    return str(user_id) in languages


def set_user_language(user_id: int, language: str):
    """Set user language preference ('ru' or 'en') and update cache."""
    user_key = str(user_id)
    languages = load_json_file(USER_LANGUAGES_FILE, {})
    languages[user_key] = language
    save_json_file(USER_LANGUAGES_FILE, languages)
    
    # Обновляем кэш
    _user_language_cache[user_key] = language
    _user_language_cache_time[user_key] = time.time()


# ==================== Gift System ====================

def has_claimed_gift(user_id: int) -> bool:
    """Check if user has already claimed their gift."""
    claimed = load_json_file(GIFT_CLAIMED_FILE, {})
    return claimed.get(str(user_id), False)


def set_gift_claimed(user_id: int):
    """Mark gift as claimed for user."""
    claimed = load_json_file(GIFT_CLAIMED_FILE, {})
    claimed[str(user_id)] = True
    save_json_file(GIFT_CLAIMED_FILE, claimed)


def spin_gift_wheel() -> float:
    """Spin the gift wheel and return random amount between 10 and 30 rubles."""
    import random
    # Generate random amount between 10 and 30 with 2 decimal places
    amount = round(random.uniform(10.0, 30.0), 2)
    return amount


# ==================== Free Generations System ====================

def get_free_generations_data() -> dict:
    """Get daily free generations data."""
    return load_json_file(FREE_GENERATIONS_FILE, {})


def save_free_generations_data(data: dict):
    """Save daily free generations data."""
    save_json_file(FREE_GENERATIONS_FILE, data)


def get_user_free_generations_today(user_id: int) -> int:
    """Get number of free generations used by user today."""
    from datetime import datetime
    
    data = get_free_generations_data()
    user_key = str(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    
    if user_key not in data:
        return 0
    
    user_data = data[user_key]
    if user_data.get('date') == today:
        return user_data.get('count', 0)
    else:
        # Reset for new day
        return 0


async def get_user_free_generations_remaining(user_id: int) -> int:
    """Get remaining free generations for user today (including referral bank)."""
    status = await get_free_generation_status(user_id)
    return int(status.get("total_remaining", 0))


async def use_free_generation(user_id: int, sku_id: str, *, correlation_id: Optional[str] = None) -> bool:
    """Consume a free generation if available."""
    result = await check_and_consume_free_generation(user_id, sku_id, correlation_id=correlation_id)
    return result.get("status") == "ok"


async def is_free_generation_available(user_id: int, sku_id: str) -> bool:
    """Check if free generation is available for this user and model."""
    from app.pricing.free_policy import is_sku_free_daily

    if not is_sku_free_daily(sku_id):
        return False
    status = await get_free_generation_status(user_id)
    return int(status.get("total_remaining", 0)) > 0


def _format_free_counter_line(remaining: int, limit_per_day: int, next_refill_in: int, user_lang: str) -> str:
    return format_free_counter_block(
        remaining,
        limit_per_day,
        next_refill_in,
        user_lang=user_lang,
    )


def _append_free_counter_text(text: str, line: str) -> str:
    if not line:
        return text
    return f"{text}\n\n{line}"


def _ensure_session_task_registry(session: Dict[str, Any], key: str) -> Set[str]:
    registry = session.get(key)
    if isinstance(registry, set):
        return registry
    if isinstance(registry, list):
        registry = set(registry)
    else:
        registry = set()
    session[key] = registry
    return registry


async def _commit_post_delivery_charge(
    *,
    session: Dict[str, Any],
    user_id: int,
    chat_id: Optional[int],
    task_id: Optional[str],
    sku_id: str,
    price: float,
    is_free: bool,
    is_admin_user: bool,
    correlation_id: Optional[str],
    model_id: Optional[str],
) -> Dict[str, Any]:
    outcome: Dict[str, Any] = {"charged": False, "free_consumed": False}
    task_key = task_id or "task-unknown"

    if is_free:
        registry = _ensure_session_task_registry(session, "free_consumed_task_ids")
        if task_key in registry:
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="FREE_DEDUCT_COMMIT",
                action_path="delivery",
                model_id=model_id,
                stage="FREE_DEDUCT",
                outcome="duplicate_skip",
                param={"task_id": task_id, "sku_id": sku_id, "delivered": True},
            )
            return outcome
        consume_result = await consume_free_generation(
            user_id,
            sku_id,
            correlation_id=correlation_id,
            source="delivery",
        )
        registry.add(task_key)
        if consume_result.get("status") == "ok":
            outcome["free_consumed"] = True
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="FREE_DEDUCT_COMMIT",
            action_path="delivery",
            model_id=model_id,
            stage="FREE_DEDUCT",
            outcome=consume_result.get("status", "unknown"),
            param={
                "task_id": task_id,
                "sku_id": sku_id,
                "delivered": True,
                "used_today": consume_result.get("used_today"),
                "remaining": consume_result.get("remaining"),
                "limit_per_day": consume_result.get("limit_per_day"),
            },
        )
        return outcome

    if is_admin_user:
        if user_id != ADMIN_ID and price > 0:
            before_spent = get_admin_spent(user_id)
            add_admin_spent(user_id, price)
            after_spent = get_admin_spent(user_id)
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="CHARGE_COMMIT",
                action_path="delivery",
                model_id=model_id,
                stage="CHARGE_COMMIT",
                outcome="admin_limit",
                param={
                    "task_id": task_id,
                    "amount": price,
                    "delivered": True,
                    "charged_before": before_spent,
                    "charged_after": after_spent,
                },
            )
        return outcome

    if user_id == ADMIN_ID or price <= 0:
        return outcome

    registry = _ensure_session_task_registry(session, "charged_task_ids")
    if task_key in registry or session.get("balance_charged"):
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="CHARGE_COMMIT",
            action_path="delivery",
            model_id=model_id,
            stage="CHARGE_COMMIT",
            outcome="duplicate_skip",
            param={"task_id": task_id, "amount": price, "delivered": True},
        )
        return outcome

    before_balance = await get_user_balance_async(user_id)
    success = await subtract_user_balance_async(user_id, price)
    after_balance = await get_user_balance_async(user_id) if success else before_balance
    if success:
        session["balance_charged"] = True
        registry.add(task_key)
        outcome["charged"] = True
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="CHARGE_COMMIT",
            action_path="delivery",
            model_id=model_id,
            stage="CHARGE_COMMIT",
            outcome="charged",
            param={
                "task_id": task_id,
                "amount": price,
                "delivered": True,
                "charged_before": before_balance,
                "charged_after": after_balance,
            },
        )
    else:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="CHARGE_COMMIT",
            action_path="delivery",
            model_id=model_id,
            stage="CHARGE_COMMIT",
            outcome="failed",
            error_code="BALANCE_DEDUCT_FAIL",
            fix_hint="Проверьте доступность storage и повторите.",
            param={
                "task_id": task_id,
                "amount": price,
                "delivered": True,
                "charged_before": before_balance,
                "charged_after": after_balance,
            },
        )
    return outcome


async def _resolve_free_counter_line(
    user_id: int,
    user_lang: str,
    correlation_id: Optional[str],
    action_path: str,
    sku_id: Optional[str] = None,
) -> str:
    try:
        return await get_free_counter_line(
            user_id,
            user_lang=user_lang,
            correlation_id=correlation_id,
            action_path=action_path,
            sku_id=sku_id,
        )
    except Exception as exc:
        logger.warning("Failed to resolve free counter line: %s", exc)
        return ""


async def get_free_counter_line(
    user_id: int,
    *,
    user_lang: str,
    correlation_id: Optional[str],
    action_path: str,
    sku_id: Optional[str] = None,
) -> str:
    if not user_id:
        return ""
    if sku_id is None:
        return ""
    from app.pricing.free_policy import is_sku_free_daily

    if not is_sku_free_daily(sku_id):
        return ""
    snapshot = await get_free_counter_snapshot(user_id)
    line = _format_free_counter_line(
        snapshot["remaining"],
        snapshot["limit_per_day"],
        snapshot["next_refill_in"],
        user_lang,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="FREE_COUNTER_VIEW",
        action_path=action_path,
        outcome="shown",
        error_code="FREE_COUNTER_VIEW_OK",
        fix_hint="Показан счетчик бесплатных генераций.",
        param={
            "remaining": snapshot["remaining"],
            "limit_per_day": snapshot["limit_per_day"],
            "used_today": snapshot["used_today"],
            "next_refill_in": snapshot["next_refill_in"],
        },
    )
    return line


# ==================== Referral System ====================

def get_referrals_data() -> dict:
    """Get referrals data."""
    return load_json_file(REFERRALS_FILE, {})


def save_referrals_data(data: dict):
    """Save referrals data."""
    save_json_file(REFERRALS_FILE, data)


def get_user_referrals(user_id: int) -> list:
    """Get list of users referred by this user."""
    data = get_referrals_data()
    user_key = str(user_id)
    return data.get(user_key, {}).get('referred_users', [])


def get_referrer(user_id: int) -> int:
    """Get the user who referred this user, or None if not referred."""
    data = get_referrals_data()
    user_key = str(user_id)
    return data.get(user_key, {}).get('referred_by')


def add_referral(referrer_id: int, referred_id: int):
    """Add a referral relationship and give bonus to referrer."""
    import time
    data = get_referrals_data()
    referrer_key = str(referrer_id)
    referred_key = str(referred_id)
    
    # Check if already referred
    if referred_key in data and data[referred_key].get('referred_by'):
        return  # Already referred by someone
    
    # Add referral relationship
    if referred_key not in data:
        data[referred_key] = {}
    data[referred_key]['referred_by'] = referrer_id
    data[referred_key]['referred_at'] = int(time.time())
    
    # Add to referrer's list
    if referrer_key not in data:
        data[referrer_key] = {'referred_users': []}
    if 'referred_users' not in data[referrer_key]:
        data[referrer_key]['referred_users'] = []
    
    if referred_id not in data[referrer_key]['referred_users']:
        data[referrer_key]['referred_users'].append(referred_id)
    
    save_referrals_data(data)
    
    # Give bonus generations to referrer
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(add_referral_free_bonus(referrer_id, REFERRAL_BONUS_GENERATIONS))
    else:
        asyncio.run(add_referral_free_bonus(referrer_id, REFERRAL_BONUS_GENERATIONS))


def give_bonus_generations(user_id: int, bonus_count: int):
    """Give bonus free generations to a user (legacy wrapper)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(add_referral_free_bonus(user_id, bonus_count))
    else:
        asyncio.run(add_referral_free_bonus(user_id, bonus_count))


def get_user_referral_link(user_id: int, bot_username: str = None) -> str:
    """Get referral link for user."""
    if bot_username is None:
        bot_username = "Ferixdi_bot_ai_bot"
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def get_fake_online_count() -> int:
    """Generate dynamic fake online user count - changes every time it's called."""
    # Base number around 500
    base = 500
    # Random variation ±80 for more dynamic changes
    variation = random.randint(-80, 80)
    # Time-based variation (slight changes based on time of day)
    current_hour = time.localtime().tm_hour
    # More activity during day hours (9-22)
    if 9 <= current_hour <= 22:
        time_multiplier = random.randint(0, 50)
    else:
        time_multiplier = random.randint(-30, 20)
    
    # Add microsecond-based variation for more randomness
    microsecond_variation = random.randint(-20, 20)
    
    count = base + variation + time_multiplier + microsecond_variation
    # Ensure reasonable bounds (300-700 range)
    return max(300, min(700, count))


# ==================== Promocodes System ====================

def load_promocodes() -> list:
    """Load promocodes from file."""
    data = load_json_file(PROMOCODES_FILE, {})
    return data.get('promocodes', [])


def save_promocodes(promocodes: list):
    """Save promocodes to file."""
    data = {'promocodes': promocodes}
    save_json_file(PROMOCODES_FILE, data)


def get_active_promocode() -> dict:
    """Get the currently active promocode."""
    promocodes = load_promocodes()
    for promo in promocodes:
        if promo.get('active', False):
            return promo
    return None


# ==================== Broadcast System ====================

def get_all_users() -> list:
    """Get list of all user IDs from various sources."""
    user_ids = set()
    
    # From user balances
    balances = load_json_file(BALANCES_FILE, {})
    user_ids.update([int(uid) for uid in balances.keys() if uid.isdigit()])
    
    # From payments
    payments = load_json_file(PAYMENTS_FILE, {})
    for payment in payments.values():
        if 'user_id' in payment:
            user_ids.add(payment['user_id'])
    
    # From referrals
    referrals = get_referrals_data()
    for user_key in referrals.keys():
        if user_key.isdigit():
            user_ids.add(int(user_key))
        # Also get referred users
        referred_users = referrals.get(user_key, {}).get('referred_users', [])
        user_ids.update(referred_users)
    
    # From free generations
    free_gens = get_free_generations_data()
    for user_key in free_gens.keys():
        if user_key.isdigit():
            user_ids.add(int(user_key))
    
    return sorted(list(user_ids))


def save_broadcast(broadcast_data: dict):
    """Save broadcast statistics."""
    broadcasts = load_json_file(BROADCASTS_FILE, {})
    broadcast_id = broadcast_data.get('id', len(broadcasts) + 1)
    broadcasts[str(broadcast_id)] = broadcast_data
    save_json_file(BROADCASTS_FILE, broadcasts)
    return broadcast_id


def get_broadcasts() -> dict:
    """Get all broadcasts."""
    return load_json_file(BROADCASTS_FILE, {})


def get_broadcast(broadcast_id: int) -> dict:
    """Get specific broadcast by ID."""
    broadcasts = get_broadcasts()
    return broadcasts.get(str(broadcast_id), {})


# ==================== Generations History System ====================

def save_generation_to_history(
    user_id: int,
    model_id: str,
    model_name: str,
    params: dict,
    result_urls: list,
    task_id: str,
    price: float = 0.0,
    is_free: bool = False,
    correlation_id: Optional[str] = None,
):
    """Save generation to user history (GitHub JSON storage)."""
    import time
    
    # GitHub JSON storage method
    try:
        # Ensure history file exists
        if not os.path.exists(GENERATIONS_HISTORY_FILE):
            try:
                with open(GENERATIONS_HISTORY_FILE, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                logger.info(f"Created history file {GENERATIONS_HISTORY_FILE}")
            except Exception as e:
                logger.error(f"Error creating history file {GENERATIONS_HISTORY_FILE}: {e}")
        
        history = load_json_file(GENERATIONS_HISTORY_FILE, {})
        user_key = str(user_id)
        
        if user_key not in history:
            history[user_key] = []
            logger.info(f"Created new history entry for user {user_id}")
        
        generation_entry = {
            'id': len(history[user_key]) + 1,
            'timestamp': int(time.time()),
            'model_id': model_id,
            'model_name': model_name,
            'params': params.copy(),
            'result_urls': result_urls.copy() if result_urls else [],
            'task_id': task_id,
            'price': price,
            'is_free': is_free
        }
        
        history[user_key].append(generation_entry)
        
        # Keep only last 100 generations per user
        if len(history[user_key]) > 100:
            history[user_key] = history[user_key][-100:]
        
        # Force immediate save for generations history (critical data)
        # Clear last save time to force immediate write
        if GENERATIONS_HISTORY_FILE in _last_save_time:
            del _last_save_time[GENERATIONS_HISTORY_FILE]
        
        # Ensure directory exists before saving
        dir_path = os.path.dirname(GENERATIONS_HISTORY_FILE)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"✅ Created directory for history file: {dir_path}")
        
        save_json_file(GENERATIONS_HISTORY_FILE, history, use_cache=True)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="PERSIST",
            action_path="save_generation_to_history",
            model_id=model_id,
            task_id=task_id,
            stage="PERSIST",
            outcome="success",
            param={"storage": "github_json", "generation_id": generation_entry.get("id")},
        )
        
        # Verify file was saved and data is correct (with retry)
        max_retries = 3
        for retry in range(max_retries):
            if os.path.exists(GENERATIONS_HISTORY_FILE):
                # Reload to verify
                verify_history = load_json_file(GENERATIONS_HISTORY_FILE, {})
                if user_key in verify_history and len(verify_history[user_key]) > 0:
                    logger.info(f"✅ Saved generation to history: user_id={user_id}, model_id={model_id}, gen_id={generation_entry['id']}, total_for_user={len(verify_history[user_key])}")
                    break
                elif retry < max_retries - 1:
                    logger.warning(f"⚠️ Retry {retry + 1}/{max_retries}: History verification failed, retrying save...")
                    save_json_file(GENERATIONS_HISTORY_FILE, history, use_cache=False)
                    import time
                    time.sleep(0.1)  # Small delay before retry
                else:
                    logger.error(f"❌ History saved but user data not found in file after {max_retries} retries! user_key={user_key}, file_keys={list(verify_history.keys())[:5]}")
            elif retry < max_retries - 1:
                logger.warning(f"⚠️ Retry {retry + 1}/{max_retries}: History file not found, retrying save...")
                save_json_file(GENERATIONS_HISTORY_FILE, history, use_cache=False)
                time.sleep(0.1)  # Small delay before retry
            else:
                logger.error(f"❌ Failed to save generation history file after {max_retries} retries: {GENERATIONS_HISTORY_FILE} does not exist after save!")
        
        return generation_entry['id']
    except Exception as e:
        logger.error(f"Error saving generation to history: {e}", exc_info=True)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="PERSIST",
            action_path="save_generation_to_history",
            model_id=model_id,
            task_id=task_id,
            stage="PERSIST",
            outcome="failed",
            error_code="PERSIST_FAILED",
            fix_hint=str(e),
        )
        return None


def get_user_generations_history(user_id: int, limit: int = 20) -> list:
    """Get user's generation history."""
    try:
        # Check if file exists, create if it doesn't
        if not os.path.exists(GENERATIONS_HISTORY_FILE):
            # Create empty history file
            try:
                with open(GENERATIONS_HISTORY_FILE, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                logger.info(f"Created history file {GENERATIONS_HISTORY_FILE}")
            except Exception as e:
                logger.error(f"Error creating history file {GENERATIONS_HISTORY_FILE}: {e}")
                return []
        
        history = load_json_file(GENERATIONS_HISTORY_FILE, {})
        if not history:
            # Empty history file is normal for new users or first run - use INFO instead of WARNING
            logger.info(f"History file {GENERATIONS_HISTORY_FILE} is empty (normal for new users)")
            return []
        
        # Try both string and integer keys (for compatibility)
        user_key_str = str(user_id)
        user_key_int = user_id
        
        # Debug: log what we're looking for
        logger.info(f"Loading history for user_id={user_id}, trying keys: '{user_key_str}' and {user_key_int}, total_users_in_file={len(history)}")
        
        # Check both string and integer keys
        user_history = None
        if user_key_str in history:
            user_history = history[user_key_str]
            logger.info(f"Found history with string key '{user_key_str}': {len(user_history)} generations")
        elif user_key_int in history:
            user_history = history[user_key_int]
            logger.info(f"Found history with integer key {user_key_int}: {len(user_history)} generations")
            # Migrate to string key for consistency
            history[user_key_str] = user_history
            if user_key_int != user_key_str:
                del history[user_key_int]
            save_json_file(GENERATIONS_HISTORY_FILE, history, use_cache=True)
        else:
            # Try to find by checking all keys
            all_keys = list(history.keys())
            logger.info(f"User {user_id} not found in history file. Available keys (first 20): {all_keys[:20]}")
            
            # Try to find numeric matches
            for key in all_keys:
                try:
                    if int(key) == user_id:
                        user_history = history[key]
                        logger.info(f"Found history with numeric match: key={key}, generations={len(user_history)}")
                        # Migrate to string key
                        history[user_key_str] = user_history
                        if key != user_key_str:
                            del history[key]
                        save_json_file(GENERATIONS_HISTORY_FILE, history, use_cache=True)
                        break
                except (ValueError, TypeError):
                    continue
            
            if user_history is None:
                logger.info(f"No history found for user {user_id} after checking all keys")
                return []
        
        if not user_history:
            logger.info(f"User {user_id} has empty history")
            return []
        
        # Return last N generations, sorted by timestamp (newest first)
        logger.info(f"Returning {min(limit, len(user_history))} generations for user {user_id} (total: {len(user_history)})")
        user_history.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return user_history[:limit]
    except Exception as e:
        logger.error(f"Error loading user generations history: {e}", exc_info=True)
        return []


def get_generation_by_id(user_id: int, generation_id: int) -> dict:
    """Get specific generation by ID."""
    history = load_json_file(GENERATIONS_HISTORY_FILE, {})
    user_key = str(user_id)
    
    if user_key not in history:
        return None
    
    for gen in history[user_key]:
        if gen.get('id') == generation_id:
            return gen
    
    return None


def is_new_user(user_id: int) -> bool:
    """Check if user is new (no balance, no history, no payments)."""
    # Check balance
    balance = get_user_balance(user_id)
    if balance > 0:
        return False
    
    # Check history
    history = get_user_generations_history(user_id, limit=1)
    if history:
        return False
    
    # Check payments
    payments = get_user_payments(user_id)
    if payments:
        return False
    
    return True


async def is_new_user_async(user_id: int) -> bool:
    """Async check if user is new (no balance, no history, no payments)."""
    balance = await get_user_balance_async(user_id)
    if balance > 0:
        return False

    history = get_user_generations_history(user_id, limit=1)
    if history:
        return False

    payments = get_user_payments(user_id)
    if payments:
        return False

    return True


async def send_broadcast(context: ContextTypes.DEFAULT_TYPE, broadcast_id: int, user_ids: list, message_text: str = None, message_photo=None):
    """Send broadcast message to all users."""
    sent = 0
    delivered = 0
    failed = 0
    
    for user_id in user_ids:
        try:
            # Skip blocked users
            if is_user_blocked(user_id):
                continue
            
            # Send message
            if message_photo:
                # Send photo with caption
                try:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=message_photo.file_id,
                        caption=message_text,
                        parse_mode='HTML'
                    )
                    delivered += 1
                except Exception as e:
                    logger.error(f"Error sending broadcast photo to {user_id}: {e}")
                    failed += 1
            else:
                # Send text message
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    delivered += 1
                except Exception as e:
                    logger.error(f"Error sending broadcast message to {user_id}: {e}")
                    failed += 1
            
            sent += 1
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.05)  # 50ms delay between messages
            
        except Exception as e:
            logger.error(f"Error in broadcast to {user_id}: {e}")
            failed += 1
            sent += 1
    
    # Update broadcast statistics
    broadcasts = get_broadcasts()
    if str(broadcast_id) in broadcasts:
        broadcasts[str(broadcast_id)]['sent'] = sent
        broadcasts[str(broadcast_id)]['delivered'] = delivered
        broadcasts[str(broadcast_id)]['failed'] = failed
        save_json_file(BROADCASTS_FILE, broadcasts)
        
        # Notify admin
        try:
            admin_id = ADMIN_ID
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"✅ <b>Рассылка #{broadcast_id} завершена!</b>\n\n"
                    f"📊 <b>Статистика:</b>\n"
                    f"✅ Отправлено: {sent}\n"
                    f"📬 Доставлено: {delivered}\n"
                    f"❌ Ошибок: {failed}\n\n"
                    f"📈 <b>Успешность:</b> {(delivered/sent*100) if sent > 0 else 0:.1f}%"
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error notifying admin about broadcast: {e}")


def is_user_blocked(user_id: int) -> bool:
    """Check if user is blocked."""
    blocked = load_json_file(BLOCKED_USERS_FILE, {})
    return blocked.get(str(user_id), False)


def block_user(user_id: int):
    """Block a user."""
    blocked = load_json_file(BLOCKED_USERS_FILE, {})
    blocked[str(user_id)] = True
    save_json_file(BLOCKED_USERS_FILE, blocked)


def unblock_user(user_id: int):
    """Unblock a user."""
    blocked = load_json_file(BLOCKED_USERS_FILE, {})
    if str(user_id) in blocked:
        del blocked[str(user_id)]
        save_json_file(BLOCKED_USERS_FILE, blocked)


def check_duplicate_payment(screenshot_file_id: str) -> bool:
    """Check if this screenshot was already used for payment."""
    if not screenshot_file_id:
        return False
    payments = load_json_file(PAYMENTS_FILE, {})
    for payment in payments.values():
        if payment.get('screenshot_file_id') == screenshot_file_id:
            return True
    return False


def _persist_payment_record(user_id: int, amount: float, screenshot_file_id: str = None) -> dict:
    """Persist payment record and return payment payload."""
    # Ensure payments file exists
    if not os.path.exists(PAYMENTS_FILE):
        try:
            with open(PAYMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info(f"Created payments file {PAYMENTS_FILE}")
        except Exception as e:
            logger.error(f"Error creating payments file {PAYMENTS_FILE}: {e}")

    payments = load_json_file(PAYMENTS_FILE, {})
    payment_id = len(payments) + 1
    import time
    payment = {
        "id": payment_id,
        "user_id": user_id,
        "amount": amount,
        "timestamp": time.time(),
        "screenshot_file_id": screenshot_file_id,
        "status": "completed"  # Auto-completed
    }
    payments[str(payment_id)] = payment

    # Force immediate save for payments (critical data)
    if PAYMENTS_FILE in _last_save_time:
        del _last_save_time[PAYMENTS_FILE]
    save_json_file(PAYMENTS_FILE, payments, use_cache=True)

    # Verify payment was saved
    if os.path.exists(PAYMENTS_FILE):
        verify_payments = load_json_file(PAYMENTS_FILE, {})
        if str(payment_id) in verify_payments:
            logger.info(f"✅ Saved payment: user_id={user_id}, amount={amount}, payment_id={payment_id}")
        else:
            logger.error(f"❌ Payment saved but not found in file! payment_id={payment_id}")
    else:
        logger.error(f"❌ Failed to save payment file: {PAYMENTS_FILE} does not exist after save!")

    return payment


def add_payment(user_id: int, amount: float, screenshot_file_id: str = None) -> dict:
    """Add a payment record. Returns payment dict with id, timestamp, etc."""
    payment = _persist_payment_record(user_id, amount, screenshot_file_id)

    # Auto-add balance
    add_user_balance(user_id, amount)

    return payment


async def add_payment_async(user_id: int, amount: float, screenshot_file_id: str = None) -> dict:
    """Async add payment with balance credit through async storage."""
    payment = _persist_payment_record(user_id, amount, screenshot_file_id)
    await add_user_balance_async(user_id, amount)
    return payment


def get_all_payments() -> list:
    """Get all payments sorted by timestamp (newest first)."""
    payments = load_json_file(PAYMENTS_FILE, {})
    payment_list = list(payments.values())
    payment_list.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return payment_list


def get_user_payments(user_id: int) -> list:
    """Get all payments for a specific user."""
    all_payments = get_all_payments()
    return [p for p in all_payments if p.get("user_id") == user_id]


def get_payment_stats() -> dict:
    """Get payment statistics."""
    payments = get_all_payments()
    total_amount = sum(p.get("amount", 0) for p in payments)
    total_count = len(payments)
    successful_statuses = {"completed", "approved"}
    successful_payments = [
        p for p in payments if p.get("status", "completed") in successful_statuses
    ]
    successful_amount = sum(p.get("amount", 0) for p in successful_payments)
    return {
        "total_amount": total_amount,
        "total_count": total_count,
        "successful_count": len(successful_payments),
        "successful_amount": successful_amount,
        "payments": payments,
    }


def get_extended_admin_stats() -> dict:
    """Get extended statistics for admin panel."""
    import time
    from datetime import datetime, timedelta
    
    now = time.time()
    today_start = int((datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).timestamp())
    week_start = int((datetime.now() - timedelta(days=7)).timestamp())
    month_start = int((datetime.now() - timedelta(days=30)).timestamp())
    
    # Get all users
    all_users = get_all_users()
    total_users = len(all_users)
    
    # Get active users (users with activity in period)
    history = load_json_file(GENERATIONS_HISTORY_FILE, {})
    active_today = set()
    active_week = set()
    active_month = set()
    
    for user_key, user_history in history.items():
        for gen in user_history:
            timestamp = gen.get('timestamp', 0)
            user_id = int(user_key) if user_key.isdigit() else None
            if user_id:
                if timestamp >= today_start:
                    active_today.add(user_id)
                if timestamp >= week_start:
                    active_week.add(user_id)
                if timestamp >= month_start:
                    active_month.add(user_id)
    
    # Get top models by usage
    model_usage = {}
    for user_key, user_history in history.items():
        for gen in user_history:
            model_id = gen.get('model_id', '')
            if model_id:
                model_usage[model_id] = model_usage.get(model_id, 0) + 1
    
    # Sort models by usage and get top 5
    top_models = sorted(model_usage.items(), key=lambda x: x[1], reverse=True)[:5]
    top_models_list = []
    for model_id, count in top_models:
        model_info = get_model_by_id(model_id)
        model_name = model_info.get('name', model_id) if model_info else model_id
        top_models_list.append({'name': model_name, 'id': model_id, 'count': count})
    
    # Get payment statistics
    payment_stats = get_payment_stats()
    total_revenue = payment_stats.get('total_amount', 0)
    total_payments = payment_stats.get('total_count', 0)
    successful_payments = payment_stats.get('successful_count', 0)
    
    # Calculate conversion rate (users who made at least one payment)
    users_with_payments = set()
    for payment in payment_stats.get('payments', []):
        user_id = payment.get('user_id')
        if user_id:
            users_with_payments.add(user_id)
    
    conversion_rate = (len(users_with_payments) / total_users * 100) if total_users > 0 else 0
    
    # Calculate average check
    avg_check = (total_revenue / total_payments) if total_payments > 0 else 0
    
    # Get revenue for periods
    payments = payment_stats.get('payments', [])
    revenue_today = sum(p.get('amount', 0) for p in payments if p.get('timestamp', 0) >= today_start)
    revenue_week = sum(p.get('amount', 0) for p in payments if p.get('timestamp', 0) >= week_start)
    revenue_month = sum(p.get('amount', 0) for p in payments if p.get('timestamp', 0) >= month_start)
    
    # Total generations count
    total_generations = sum(len(user_history) for user_history in history.values())
    
    return {
        'total_users': total_users,
        'active_today': len(active_today),
        'active_week': len(active_week),
        'active_month': len(active_month),
        'top_models': top_models_list,
        'total_revenue': total_revenue,
        'revenue_today': revenue_today,
        'revenue_week': revenue_week,
        'revenue_month': revenue_month,
        'total_payments': total_payments,
        'successful_payments': successful_payments,
        'conversion_rate': conversion_rate,
        'avg_check': avg_check,
        'total_generations': total_generations
    }


async def render_admin_panel(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    """Render admin panel with extended statistics."""
    if is_callback:
        query = update_or_query
        user_id = query.from_user.id
        message_func = query.edit_message_text
        try:
            await query.answer()
        except Exception:
            pass
    else:
        update = update_or_query
        user_id = update.effective_user.id
        message_func = update.message.reply_text

    if not is_admin(user_id):
        if is_callback:
            await query.answer("❌ Эта функция доступна только администратору.", show_alert=True)
        else:
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return

    generation_types = get_generation_types()
    total_models = len(get_models_sync())

    stats = get_extended_admin_stats()

    kie_balance_info = ""
    correlation_id = get_correlation_id() or uuid.uuid4().hex
    if kie is not None:
        try:
            balance_result = await get_kie_credits_cached(correlation_id=correlation_id)
            if balance_result.get('ok'):
                balance = balance_result.get('credits', 0)
                balance_rub = balance * CREDIT_TO_USD * get_usd_to_rub_rate()
                balance_rub_str = f"{balance_rub:.2f}"
                kie_balance_info = f"💰 <b>Баланс KIE API:</b> {balance_rub_str} ₽ ({balance} кредитов)\n\n"
            else:
                status = balance_result.get("status")
                if status == 404:
                    kie_balance_info = "💰 <b>Баланс KIE API:</b> Баланс KIE недоступен (endpoint 404)\n\n"
                else:
                    kie_balance_info = "💰 <b>Баланс KIE API:</b> временно недоступно\n\n"
                logger.warning(
                    "KIE balance unavailable corr_id=%s status=%s error=%s",
                    balance_result.get("correlation_id", correlation_id),
                    status,
                    balance_result.get("error"),
                )
        except Exception as e:
            logger.error("Error getting KIE balance corr_id=%s error=%s", correlation_id, e)
            kie_balance_info = "💰 <b>Баланс KIE API:</b> временно недоступно\n\n"
    else:
        kie_balance_info = "💰 <b>Баланс KIE API:</b> Клиент не инициализирован\n\n"

    top_models_text = ""
    if stats['top_models']:
        top_models_text = "\n<b>Топ-5 моделей:</b>\n"
        for i, model in enumerate(stats['top_models'], 1):
            top_models_text += f"{i}. {model['name']}: {model['count']} использований\n"
        top_models_text += "\n"
    else:
        top_models_text = "\n<b>Топ-5 моделей:</b> Нет данных\n\n"

    admin_text = (
        f'👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b> 👑\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'{kie_balance_info}'
        f'📊 <b>РАСШИРЕННАЯ СТАТИСТИКА:</b>\n\n'
        f'👥 <b>Пользователи:</b>\n'
        f'   • Всего: <b>{stats["total_users"]}</b>\n'
        f'   • Активных сегодня: <b>{stats["active_today"]}</b>\n'
        f'   • Активных за неделю: <b>{stats["active_week"]}</b>\n'
        f'   • Активных за месяц: <b>{stats["active_month"]}</b>\n\n'
        f'🎨 <b>Генерации:</b>\n'
        f'   • Всего генераций: <b>{stats["total_generations"]}</b>\n'
        f'{top_models_text}'
        f'💰 <b>Финансы:</b>\n'
        f'   • Общий доход: <b>{format_rub_amount(stats["total_revenue"])}</b>\n'
        f'   • Доход сегодня: <b>{format_rub_amount(stats["revenue_today"])}</b>\n'
        f'   • Доход за неделю: <b>{format_rub_amount(stats["revenue_week"])}</b>\n'
        f'   • Доход за месяц: <b>{format_rub_amount(stats["revenue_month"])}</b>\n'
        f'   • Всего пополнений: <b>{stats["total_payments"]}</b>\n'
        f'   • Успешных пополнений: <b>{stats["successful_payments"]}</b>\n'
        f'   • Средний чек: <b>{format_rub_amount(stats["avg_check"])}</b>\n'
        f'   • Конверсия в оплату: <b>{stats["conversion_rate"]:.1f}%</b>\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'📊 <b>СИСТЕМА:</b>\n\n'
        f'✅ <b>{total_models} премиум моделей</b> в арсенале\n'
        f'✅ <b>{len(generation_types)} категорий</b> контента\n'
        f'✅ Безлимитный доступ ко всем генерациям\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'⚙️ <b>АДМИНИСТРАТИВНЫЕ ФУНКЦИИ:</b>\n\n'
        f'📈 Просмотр статистики и аналитики\n'
        f'👥 Управление пользователями\n'
        f'🎁 Управление промокодами\n'
        f'🧪 Тестирование OCR системы\n'
        f'💼 Полный контроль над ботом\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'💫 <b>ВЫБЕРИТЕ ДЕЙСТВИЕ:</b>'
    )

    keyboard = [
        [InlineKeyboardButton("📊 Обновить статистику", callback_data="admin_stats")],
        [InlineKeyboardButton("📚 Просмотр генераций", callback_data="admin_view_generations")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("🔍 Поиск", callback_data="admin_search")],
        [InlineKeyboardButton("📝 Добавить", callback_data="admin_add")],
        [InlineKeyboardButton("🧪 Тест OCR", callback_data="admin_test_ocr")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")],
    ]

    await message_func(
        admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
    )


def get_payment_details() -> str:
    """Get payment details from .env (СБП - Система быстрых платежей)."""
    # Убрано: load_dotenv()
    # Все переменные окружения ТОЛЬКО из ENV (Render Dashboard или системные ENV)
    # Для локальной разработки используйте системные ENV переменные
    
    # Get from environment (works both for .env and Render Environment Variables)
    card_holder = os.getenv('PAYMENT_CARD_HOLDER', '').strip()
    phone = os.getenv('PAYMENT_PHONE', '').strip()
    bank = os.getenv('PAYMENT_BANK', '').strip()
    
    # Enhanced debug logging for troubleshooting
    logger.debug(f"Loading payment details - PAYMENT_PHONE: {'SET' if phone else 'NOT SET'}, PAYMENT_BANK: {'SET' if bank else 'NOT SET'}, PAYMENT_CARD_HOLDER: {'SET' if card_holder else 'NOT SET'}")
    
    # Check if any payment details are missing
    if not phone and not bank and not card_holder:
        logger.warning("Payment details not found in environment variables!")
        logger.warning("Make sure these environment variables are set in Render dashboard:")
        logger.warning("  - PAYMENT_PHONE")
        logger.warning("  - PAYMENT_BANK")
        logger.warning("  - PAYMENT_CARD_HOLDER")
        # Also log all environment variables that start with PAYMENT_ for debugging
        payment_env_vars = {k: v for k, v in os.environ.items() if k.startswith('PAYMENT_')}
        logger.debug(f"All PAYMENT_* environment variables: {payment_env_vars}")
    
    details = "💳 <b>Реквизиты для оплаты (СБП):</b>\n\n"
    
    if phone:
        details += f"📱 <b>Номер телефона:</b> <code>{phone}</code>\n"
    if bank:
        details += f"🏦 <b>Банк:</b> {bank}\n"
    if card_holder:
        details += f"👤 <b>Получатель:</b> {card_holder}\n"
    
    if not phone and not bank and not card_holder:
        details += "⚠️ <b>ВНИМАНИЕ: Реквизиты не настроены!</b>\n\n"
        details += "Администратору необходимо указать следующие переменные окружения:\n"
        details += "• <code>PAYMENT_PHONE</code> - номер телефона для СБП\n"
        details += "• <code>PAYMENT_BANK</code> - название банка\n"
        details += "• <code>PAYMENT_CARD_HOLDER</code> - имя получателя\n\n"
        details += "На Render: добавьте их в разделе Environment Variables\n"
        details += "Локально: добавьте в файл .env\n\n"
    
    details += "\n⚠️ <b>Важно:</b> После оплаты отправьте скриншот перевода в этот чат.\n\n"
    details += "✅ <b>Баланс начислится автоматически</b> после отправки скриншота."
    
    return details


def build_manual_payment_instructions(
    *,
    amount: float,
    user_lang: str,
    payment_details: str,
    method_label: str,
) -> str:
    """Build manual payment instructions for SBP/card transfers."""
    examples_count = int(amount / 0.62)  # free tools price
    video_count = int(amount / 3.86)  # Basic video price
    amount_display = format_rub_amount(amount)
    if user_lang == 'ru':
        return (
            f'💳 <b>ОПЛАТА {amount_display} ({method_label})</b> 💳\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{payment_details}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'💵 <b>Сумма к оплате:</b> {amount_display}\n\n'
            f'🎯 <b>ЧТО ТЫ ПОЛУЧИШЬ:</b>\n'
            f'• ~{examples_count} изображений (free tools)\n'
            f'• ~{video_count} видео (базовая модель)\n'
            f'• Или комбинацию разных моделей!\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'📸 <b>КАК ОПЛАТИТЬ:</b>\n'
            f'1️⃣ Переведи {amount_display} по реквизитам выше\n'
            f'2️⃣ Сделай скриншот перевода\n'
            f'3️⃣ Отправь скриншот сюда\n'
            f'4️⃣ Баланс начислится автоматически! ⚡\n\n'
            f'✅ <b>Все просто и быстро!</b>'
        )
    return (
        f'💳 <b>PAYMENT {amount_display} ({method_label})</b> 💳\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'{payment_details}\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'💵 <b>Amount to pay:</b> {amount_display}\n\n'
        f'🎯 <b>WHAT YOU WILL GET:</b>\n'
        f'• ~{examples_count} images (free tools)\n'
        f'• ~{video_count} videos (basic model)\n'
        f'• Or a combination of different models!\n\n'
        f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'📸 <b>HOW TO PAY:</b>\n'
        f'1️⃣ Transfer {amount_display} using details above\n'
        f'2️⃣ Take a screenshot of the transfer\n'
        f'3️⃣ Send screenshot here\n'
        f'4️⃣ Balance will be added automatically! ⚡\n\n'
        f'✅ <b>Simple and fast!</b>'
    )


def get_support_contact() -> str:
    """Get support contact information from .env (only Telegram)."""
    # Убрано: load_dotenv()
    # Все переменные окружения ТОЛЬКО из ENV (Render Dashboard или системные ENV)
    # Для локальной разработки используйте системные ENV переменные
    
    support_telegram = os.getenv('SUPPORT_TELEGRAM', '').strip()
    support_text = os.getenv('SUPPORT_TEXT', '').strip()
    fallback_telegram = "@ferixdiii"
    
    # Enhanced debug logging for troubleshooting
    logger.debug(f"Loading support contact - SUPPORT_TELEGRAM: {'SET' if support_telegram else 'NOT SET'}, SUPPORT_TEXT: {'SET' if support_text else 'NOT SET'}")
    
    contact = "🆘 <b>Поддержка</b>\n\n"
    
    if support_text:
        contact += f"{support_text}\n\n"
    else:
        contact += "Если у вас возникли вопросы или проблемы, свяжитесь с нами:\n\n"
    
    if support_telegram:
        telegram_username = support_telegram.replace('@', '')
        contact += f"💬 <b>Telegram:</b> @{telegram_username}\n"
    else:
        support_telegram = fallback_telegram
        logger.warning("Support contact not found in environment variables!")
        logger.warning("Make sure these environment variables are set in Render dashboard:")
        logger.warning("  - SUPPORT_TELEGRAM")
        logger.warning("  - SUPPORT_TEXT (optional)")
        # Also log all environment variables that start with SUPPORT_ for debugging
        support_env_vars = {k: v for k, v in os.environ.items() if k.startswith('SUPPORT_')}
        logger.debug(f"All SUPPORT_* environment variables: {support_env_vars}")
        contact += "⚠️ <b>Контактная информация не настроена.</b>\n\n"
        contact += "Администратору необходимо указать SUPPORT_TELEGRAM в файле .env или в настройках Render (Environment Variables).\n\n"
        contact += f"Контакт администратора: {support_telegram}\n"
        contact += "Обратитесь к администратору."
    
    return contact


async def analyze_payment_screenshot(image_data: bytes, expected_amount: float, expected_phone: str = None) -> dict:
    """
    STRICT Payment verification for СБП (Fast Bank Transfer) screenshots.
    
    Verification steps:
    1. Extract text via OCR (Russian+English)
    2. Find exact payment amount (±5% tolerance, stricter than before)
    3. Find payment keywords (успешно, переведено, платеж, сбп, etc.)
    4. Verify phone number if expected
    
    STRICT RULES:
    - Amount MUST be found and match (±5%)
    - CRITICAL keywords must be present (успешно/переведено/отправлено) OR phone must match
    - On OCR failure: REJECT (don't auto-credit)
    - Returns: {valid: bool, amount_found, phone_found, has_critical_keyword, message}
    """
    if not OCR_AVAILABLE or not PIL_AVAILABLE:
        logger.warning(f"⚠️ OCR not available. Payment verification DISABLED - will require manual review")
        return {
            'valid': False,  # STRICT: Reject without OCR
            'amount_found': False,
            'phone_found': False,
            'message': 'ℹ️ <b>OCR недоступен</b>. Проверка платежа требует ручной верификации админист­ратором.\n\n❌ Баланс <b>НЕ начислен</b> автоматически.'
        }
    
    try:
        # Convert bytes to PIL Image
        image = Image.open(BytesIO(image_data))
        logger.info(f"📸 Analyzing payment screenshot ({image.size[0]}x{image.size[1]}px) for amount {expected_amount} RUB")
        
        # Extract text via OCR
        extracted_text = ""
        try:
            extracted_text = pytesseract.image_to_string(image, lang='rus+eng')
            logger.debug(f"✅ OCR successful (rus+eng): {len(extracted_text)} characters")
        except Exception as e:
            logger.warning(f"⚠️ OCR error (rus+eng): {e}")
            # Try English only if Russian fails
            try:
                extracted_text = pytesseract.image_to_string(image, lang='eng')
                logger.debug(f"✅ OCR successful (eng): {len(extracted_text)} characters")
            except Exception as e2:
                logger.warning(f"⚠️ OCR error (eng): {e2}")
                # Try default
                try:
                    extracted_text = pytesseract.image_to_string(image)
                    logger.debug(f"✅ OCR successful (default): {len(extracted_text)} characters")
                except Exception as e3:
                    logger.error(f"❌ OCR completely failed: {e3}")
                    raise
        
        extracted_text_lower = extracted_text.lower()
        logger.info(f"📄 Recognized text (first 300 chars): {extracted_text_lower[:300]}")
        
        # CRITICAL KEYWORDS: Strong indicators of successful payment
        critical_keywords = [
            'успешно',  # Successfully (STRONGEST indicator)
            'переведено',  # Transferred (STRONGEST)
            'отправлено',  # Sent (STRONGEST)
            'сбп',  # SBP system name
        ]
        
        # Additional keywords: Weaker but supporting
        additional_keywords = [
            'перевод', 'платеж', 'payment', 'transfer', 'amount', 'сумма',
            'итого', 'total', 'получатель', 'recipient', 'статус', 'status',
            'квитанция', 'receipt', 'комиссия', 'commission', 'пополнение', 'topup'
        ]
        
        # STRICT: Require at least ONE critical keyword
        has_critical_keyword = any(keyword in extracted_text_lower for keyword in critical_keywords)
        has_additional_keyword = any(keyword in extracted_text_lower for keyword in additional_keywords)
        has_payment_keywords = has_critical_keyword or has_additional_keyword
        
        if has_critical_keyword:
            logger.info(f"✅ CRITICAL PAYMENT INDICATOR FOUND")
        elif has_additional_keyword:
            logger.info(f"✅ Additional payment indicator found")
        else:
            logger.warning(f"⚠️ NO payment indicators found")
        
        # Extract amount from text - STRICT MATCHING
        amount_patterns = [
            # HIGHEST PRIORITY: Numbers with currency symbols (most reliable)
            (r'(\d{2,6})[.,]?(\d{0,2})\s*[₽рубрубль]', 'с рублём'),
            (r'[₽рубрубль]\s*(\d{2,6})[.,]?(\d{0,2})', 'рубль перед'),
            # HIGH PRIORITY: Near payment keywords
            (r'(?:сумма|переведено?|перевел|amount)\s*[=:]\s*(\d{2,6})[.,]?(\d{0,2})\s*[₽рубрубль]?', 'сумма='),
            (r'(?:сумма|переведено?|перевел|amount)[=:]\s*(\d{2,6})', 'ключевое слово'),
            # MEDIUM PRIORITY: Standalone large numbers
            (r'\b(\d{3,6})[.,]?(\d{0,2})\b', 'большое число'),
        ]
        
        amount_found = False
        found_amount = None
        all_found_amounts = []
        
        # Extract amounts using patterns with priority
        for pattern, pattern_name in amount_patterns:
            matches = re.findall(pattern, extracted_text_lower, re.IGNORECASE)
            if matches:
                for match in matches:
                    try:
                        # Handle both single group and multi-group matches
                        if isinstance(match, tuple):
                            # Multi-group: reconstruct number
                            whole = match[0].strip()
                            decimal = match[1].strip() if len(match) > 1 else ''
                            if decimal:
                                amount_str = f"{whole}.{decimal}"
                            else:
                                amount_str = whole
                        else:
                            amount_str = match.strip()
                        
                        amount_val = float(amount_str.replace(',', '.'))
                        # Sanity check: amount should be reasonable (1-500000 RUB)
                        if 1 <= amount_val <= 500000:
                            all_found_amounts.append((amount_val, pattern_name))
                            logger.debug(f"  Found amount: {amount_val} RUB (pattern: {pattern_name})")
                    except (ValueError, IndexError) as e:
                        logger.debug(f"  Failed to parse amount from {match}: {e}")
                        continue
        
        logger.info(f"💰 Total amounts found: {len(all_found_amounts)}: {[a[0] for a in all_found_amounts[:5]]}")
        
        if all_found_amounts:
            # Extract unique amounts and sort by priority (currency symbol patterns first)
            # Group by amount value
            amount_dict = {}  # amount -> count
            for amt, source in all_found_amounts:
                if amt not in amount_dict:
                    amount_dict[amt] = 0
                amount_dict[amt] += 1
            
            # Sort amounts: prefer those that appear multiple times, then largest
            unique_amounts = sorted(amount_dict.keys(), key=lambda x: (-amount_dict[x], -x))
            logger.info(f"🔍 Unique amounts (priority): {unique_amounts[:5]}")
            
            # STRICT: Try to find amount that EXACTLY matches (within 5%)
            for amt in unique_amounts:
                diff = abs(amt - expected_amount)
                diff_percent = (diff / expected_amount) if expected_amount > 0 else 1
                
                logger.info(f"  Check {amt} RUB vs {expected_amount} RUB: diff {diff:.2f} ({diff_percent*100:.1f}%)")
                
                # STRICT: Allow only up to 5% difference for security
                if diff_percent <= 0.05:  # 5% tolerance
                    amount_found = True
                    found_amount = amt
                    logger.info(f"✅ AMOUNT MATCHES: {found_amount} RUB (expected {expected_amount})")
                    break
            
            # If no exact match within 5%, try with 10% tolerance (but log warning)
            if not amount_found:
                for amt in unique_amounts:
                    diff = abs(amt - expected_amount)
                    diff_percent = (diff / expected_amount) if expected_amount > 0 else 1
                    if diff_percent <= 0.10:  # 10% tolerance - RELAXED
                        amount_found = True
                        found_amount = amt
                        logger.warning(f"⚠️ AMOUNT APPROXIMATELY MATCHES: {found_amount} RUB (expected {expected_amount}, diff {diff_percent*100:.1f}%)")
                        break
            
            if not amount_found:
                logger.warning(f"❌ AMOUNT DOESN'T MATCH: closest found {unique_amounts[0] if unique_amounts else 'NONE'} RUB (expected {expected_amount})")
        
        # Extract phone number from text - STRICT MATCHING
        phone_found = False
        phone_status_msg = "телефон не проверяется"
        if expected_phone:
            # Normalize phone (remove +, spaces, dashes, parentheses)
            normalized_expected = re.sub(r'[+\s\-().]', '', str(expected_phone))
            logger.info(f"📱 Looking for phone: {expected_phone} (normalized: {normalized_expected})")
            
            # Look for phone patterns - Russian format
            phone_patterns = [
                r'\+?7\d{10}',  # +7 or 7 followed by 10 digits
                r'8\d{10}',  # 8 followed by 10 digits (Russian format)
                r'\+?7[\s.-]?\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}',  # Formatted: +7(XXX)XXX-XX-XX
                r'\d{11}',  # 11 digit number
            ]
            
            found_phones = []
            for pattern in phone_patterns:
                matches = re.findall(pattern, extracted_text_lower)
                found_phones.extend(matches)
                if matches:
                    logger.debug(f"  Found phones (pattern {pattern}): {matches[:3]}")
            
            if found_phones:
                logger.info(f"📱 Found {len(found_phones)} phone numbers")
                for match in found_phones:
                    normalized_match = re.sub(r'[+\s\-().]', '', match)
                    # Normalize 8 to 7 for comparison (Russian phone standard)
                    if normalized_match.startswith('8'):
                        normalized_match = '7' + normalized_match[1:]
                    
                    logger.debug(f"  Check: {match} -> {normalized_match} vs {normalized_expected}")
                    
                    # STRICT: Require exact match or last 10 digits match
                    if normalized_match == normalized_expected:
                        phone_found = True
                        phone_status_msg = f"✅ номер совпадает ({normalized_match[-10:]})"
                        logger.info(f"✅ PHONE MATCHES: {match}")
                        break
                    elif normalized_match[-10:] == normalized_expected[-10:]:
                        phone_found = True
                        phone_status_msg = f"✅ номер совпадает (последние 10 цифр)"
                        logger.info(f"✅ PHONE MATCHES (last 10 digits): {match}")
                        break
                
                if not phone_found:
                    logger.warning(f"⚠️ PHONE DOESN'T MATCH: found {found_phones[0]} vs expected {expected_phone}")
                    phone_status_msg = f"❌ номер не совпадает"
            else:
                logger.warning(f"❌ PHONE NOT FOUND in screenshot")
                phone_status_msg = f"❌ номер не найден"
        
        # STRICT VALIDATION SYSTEM
        # Require: AMOUNT + (KEYWORDS or PHONE) to pass
        logger.info(f"\n✔️ VALIDATION RESULTS:")
        logger.info(f"  1. Amount found: {amount_found} ({found_amount} vs {expected_amount})")
        logger.info(f"  2. Critical keywords: {has_critical_keyword}")
        logger.info(f"  3. {phone_status_msg}")
        
        # CRITICAL RULE: Amount MUST be found
        if not amount_found:
            logger.warning(f"❌ VALIDATION REJECTED: amount not found or doesn't match")
            valid = False
        # If amount found, check supporting evidence
        elif not has_critical_keyword and not phone_found:
            # Amount found but no supporting keywords or phone
            logger.warning(f"⚠️ WARNING: amount found but no supporting indicators")
            # Still allow if amount is perfect match
            if amount_found:
                valid = True
                logger.info(f"✅ Amount perfectly matches, allowing payment despite missing supporting indicators")
            else:
                valid = False
        else:
            # Amount found + at least one supporting evidence (keywords or phone)
            valid = True
            logger.info(f"✅ VALIDATION SUCCESS: all checks passed")
        
        # Build user-friendly message
        message_parts = []
        message_parts.append("🔍 <b>РЕЗУЛЬТАТЫ ПРОВЕРКИ ПЛАТЕЖА:</b>")
        message_parts.append("")
        
        if amount_found and found_amount:
            message_parts.append(f"✅ <b>Сумма:</b> {format_rub_amount(found_amount)} RUB")
        else:
            message_parts.append(f"❌ <b>Сумма:</b> не найдена в скриншоте (ожидалось {format_rub_amount(expected_amount)})")
        
        if expected_phone:
            if phone_found:
                message_parts.append(f"✅ <b>Номер телефона:</b> подтвержден")
            else:
                message_parts.append(f"⚠️ <b>Номер телефона:</b> не найден или не совпадает")
        
        if has_critical_keyword:
            message_parts.append("✅ <b>Статус:</b> платеж подтвержден (успешно/переведено)")
        elif has_additional_keyword:
            message_parts.append("✅ <b>Статус:</b> обнаружены признаки платежа")
        else:
            message_parts.append("❌ <b>Статус:</b> признаки платежа не обнаружены")
        
        if valid:
            message_parts.append("")
            message_parts.append("🎉 <b>Проверка пройдена! Баланс будет начислен.</b>")
        else:
            message_parts.append("")
            message_parts.append("⚠️ <b>Проверка не пройдена. Обратитесь к администратору.</b>")
        
        logger.info(f"\n📋 FINAL RESULT: valid={valid}, amount={found_amount}, phone={phone_found}\n")
        
        return {
            'valid': valid,
            'amount_found': amount_found,
            'phone_found': phone_found if expected_phone else None,
            'has_critical_keyword': has_critical_keyword,
            'has_payment_keywords': has_payment_keywords,
            'found_amount': found_amount,
            'message': '\n'.join(message_parts)
        }
        
    except Exception as e:
        logger.error(f"❌ Error analyzing payment screenshot: {e}", exc_info=True)
        # STRICT: On exception, REJECT (don't auto-credit)
        return {
            'valid': False,  # STRICT: Fail closed
            'amount_found': False,
            'phone_found': False,
            'message': f'❌ <b>Ошибка анализа изображения:</b> {str(e)}.\n\nПроверка платежа требует <b>ручной верификации</b> администратором.\n\n⚠️ Баланс <b>НЕ начислен</b> автоматически.'
        }


# ==================== End Payment System Functions ====================


async def upload_image_to_hosting(image_data: bytes, filename: str = "image.jpg") -> str:
    """
    Upload image to public hosting and return public URL.
    
    🔴 КРИТИЧЕСКОЕ ПРАВИЛО: ЭТА ФУНКЦИЯ ДОЛЖНА БЫТЬ ЗАМЕНЕНА НА KIE AI FILE UPLOAD API!
    
    ВСЕ файлы (изображения, видео, аудио) ДОЛЖНЫ загружаться через KIE AI File Upload API:
    - Base URL: https://kieai.redpandaai.co
    - Endpoints:
      * POST /api/file-stream-upload - для локальных файлов (рекомендуется)
      * POST /api/file-base64-upload - для маленьких файлов (≤10MB)
      * POST /api/file-url-upload - для удаленных файлов
    - Authentication: Authorization: Bearer YOUR_API_KEY
    - Документация: https://docs.kie.ai/file-upload-api
    
    ⚠️ НЕ использовать внешние хостинги (0x0.st, catbox.moe, transfer.sh)!
    ⚠️ Файлы в KIE AI File Upload API автоматически удаляются через 3 дня!
    
    NOTE: заменить эту функцию на использование KIE AI File Upload API
    """
    if not image_data or len(image_data) == 0:
        logger.error("Empty image data provided")
        return None

    request_timeout = aiohttp.ClientTimeout(total=20, sock_connect=6, sock_read=12)
    user_agent_header = {"User-Agent": "TRTBot/1.0 (+https://github.com/ferixdi-png/TRT)"}
    
    # 🔴 ВРЕМЕННОЕ РЕШЕНИЕ: Используются внешние хостинги
    # NOTE: заменить на KIE AI File Upload API (https://kieai.redpandaai.co/api/file-stream-upload)
    # Try multiple hosting services
    hosting_services = [
        # 0x0.st - simple file hosting (most reliable)
        {
            'url': 'https://0x0.st',
            'method': 'POST',
            'data_type': 'form',
            'field_name': 'file'
        },
        # catbox.moe - image hosting
        {
            'url': 'https://catbox.moe/user/api.php',
            'method': 'POST',
            'data_type': 'form',
            'field_name': 'fileToUpload',
            'extra_params': {'reqtype': 'fileupload'}
        },
        # transfer.sh - file sharing
        {
            'url': f'https://transfer.sh/{filename}',
            'method': 'PUT',
            'data_type': 'raw',
            'field_name': None
        }
    ]
    
    for service in hosting_services:
        try:
            logger.info(f"Trying to upload to {service['url']}")
            try:
                session = await get_http_client()
            except Exception as e:
                log_structured_event(
                    correlation_id=get_correlation_id(None, None),
                    action="IMAGE_UPLOAD",
                    action_path="image_upload>hosting",
                    stage="image_upload",
                    outcome="http_client_uninitialized",
                    error_code="IMAGE_HOSTING_HTTP_CLIENT_NOT_INITIALIZED",
                    fix_hint="declare_global_http_client_and_init_aiohttp_session",
                )
                logger.error(
                    "HTTP client not initialized for image hosting upload: %s",
                    e,
                    exc_info=True,
                )
                return None
            if service['data_type'] == 'form':
                data = aiohttp.FormData()
                # Add extra params if needed
                if 'extra_params' in service:
                    for key, value in service['extra_params'].items():
                        data.add_field(key, value)
                
                # Add file
                data.add_field(
                    service['field_name'],
                    BytesIO(image_data),
                    filename=filename,
                    content_type='image/jpeg'
                )
                
                async with session.post(
                    service['url'],
                    data=data,
                    timeout=request_timeout,
                    headers=user_agent_header,
                ) as resp:
                    status = resp.status
                    text = await resp.text()
                    logger.info(f"Response from {service['url']}: status={status}, text={text[:100]}")
                    
                    if status in [200, 201]:
                        text = text.strip()
                        # For catbox.moe, response is direct URL
                        if 'catbox.moe' in service['url']:
                            if text.startswith('http'):
                                logger.info("Upload succeeded via catbox.moe")
                                return text
                        # For 0x0.st, response is direct URL
                        elif text.startswith('http'):
                            logger.info("Upload succeeded via 0x0.st")
                            return text
                    else:
                        logger.warning(f"Upload to {service['url']} failed with status {status}: {text[:200]}")
            else:  # raw
                    headers = {
                        'Content-Type': 'image/jpeg',
                        'Max-Downloads': '1',
                        'Max-Days': '7',
                        **user_agent_header,
                    }
                    async with session.put(
                        service['url'],
                        data=image_data,
                        headers=headers,
                        timeout=request_timeout,
                    ) as resp:
                        status = resp.status
                        text = await resp.text()
                        logger.info(f"Response from {service['url']}: status={status}, text={text[:100]}")
                        
                        if status in [200, 201]:
                            text = text.strip()
                            if text.startswith('http'):
                                logger.info("Upload succeeded via transfer.sh")
                                return text
                        else:
                            logger.warning(f"Upload to {service['url']} failed with status {status}: {text[:200]}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout uploading to {service['url']}")
            continue
        except Exception as e:
            logger.error(f"Exception uploading to {service['url']}: {e}", exc_info=True)
            continue
    
    # If all services fail, return None
    logger.error("All image hosting services failed. Image size: {} bytes".format(len(image_data)))
    return None


async def upload_image_to_kie_file_api(image_data: bytes, filename: str = "image.jpg") -> str:
    """Upload image directly to KIE AI File Upload API and return fileUrl."""
    api_key = os.getenv("KIE_API_KEY", "").strip()
    if not api_key:
        logger.warning("KIE_API_KEY not set; skipping KIE file upload fallback.")
        return None

    base_url = os.getenv("KIE_FILE_UPLOAD_BASE_URL", "https://kieai.redpandaai.co").rstrip("/")
    url = f"{base_url}/api/file-stream-upload"

    try:
        session = await get_http_client()
    except Exception as e:
        log_structured_event(
            correlation_id=get_correlation_id(None, None),
            action="IMAGE_UPLOAD",
            action_path="image_upload>kie_file_api",
            stage="image_upload",
            outcome="http_client_uninitialized",
            error_code="IMAGE_HOSTING_HTTP_CLIENT_NOT_INITIALIZED",
            fix_hint="declare_global_http_client_and_init_aiohttp_session",
        )
        logger.error("HTTP client not initialized for KIE file upload: %s", e, exc_info=True)
        return None

    data = aiohttp.FormData()
    data.add_field(
        "file",
        BytesIO(image_data),
        filename=filename,
        content_type="image/jpeg",
    )
    data.add_field("uploadPath", "images")

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with session.post(url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            payload_text = await resp.text()
            if resp.status not in {200, 201}:
                logger.error(
                    "KIE file upload failed: status=%s payload=%s",
                    resp.status,
                    payload_text[:200],
                )
                return None
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                logger.error("KIE file upload response is not JSON: %s", payload_text[:200])
                return None
            if not payload.get("success"):
                logger.error("KIE file upload unsuccessful: %s", payload)
                return None
            file_url = payload.get("data", {}).get("fileUrl")
            if not file_url:
                logger.error("KIE file upload missing fileUrl: %s", payload)
                return None
            logger.info("Upload succeeded via KIE file API")
            return file_url
    except asyncio.TimeoutError:
        logger.warning("Timeout uploading image to KIE file API.")
        return None
    except Exception as e:
        logger.error("Exception uploading image to KIE file API: %s", e, exc_info=True)
        return None


async def upload_image_with_fallback(image_data: bytes, filename: str = "image.jpg") -> str:
    """Try public hosting first, fall back to KIE file upload API."""
    public_url = await upload_image_to_hosting(image_data, filename=filename)
    if public_url:
        return public_url
    logger.warning("Public hosting unavailable; trying KIE file upload API fallback.")
    return await upload_image_to_kie_file_api(image_data, filename=filename)


MAIN_MENU_TEXT_FALLBACK = "Главное меню"


def _get_release_version() -> str:
    env_version = os.getenv("BOT_RELEASE_VERSION", "").strip()
    if env_version:
        return env_version
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "1.0.0"


def _get_release_date() -> str:
    env_date = os.getenv("BOT_RELEASE_DATE", "").strip()
    if env_date:
        return env_date
    return datetime.now().strftime("%d.%m.%Y")


def _get_whats_new_lines(user_lang: str) -> list[str]:
    env_lines = os.getenv("BOT_WHATS_NEW", "").strip()
    if env_lines:
        return [line.strip("• ").strip() for line in env_lines.splitlines() if line.strip()]
    if user_lang == "en":
        return [
            "Welcome screen and main menu restored",
            "GitHub storage stability improvements",
            "Catalog and pricing flow synchronized",
        ]
    return [
        "Возвращено приветствие и главное меню",
        "Устойчивый GitHub storage без падений",
        "Синхронизирован каталог моделей и цены",
    ]


def _format_refill_eta(seconds: int, user_lang: str) -> str:
    safe_seconds = max(0, int(seconds))
    if safe_seconds < 60:
        return f"{safe_seconds} сек" if user_lang == "ru" else f"{safe_seconds}s"
    minutes = int((safe_seconds + 59) / 60)
    return f"{minutes} мин" if user_lang == "ru" else f"{minutes} min"


def _build_release_block(user_lang: str) -> str:
    version_label = "Version" if user_lang == "en" else "Версия"
    date_label = "Date" if user_lang == "en" else "Дата"
    whats_new_label = "What's new" if user_lang == "en" else "Что нового"
    lines = _get_whats_new_lines(user_lang)
    bullets = "\n".join(f"• {line}" for line in lines)
    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>{version_label}:</b> {_get_release_version()}\n"
        f"📅 <b>{date_label}:</b> {_get_release_date()}\n"
        f"🆕 <b>{whats_new_label}:</b>\n"
        f"{bullets}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )


async def _build_main_menu_sections(update: Update, *, correlation_id: Optional[str] = None) -> tuple[str, str]:
    user = update.effective_user
    user_id = user.id if user else None
    user_lang = "ru"
    if user_id:
        try:
            from app.services.user_service import get_user_language as get_user_language_async
            user_lang = await get_user_language_async(user_id)
        except Exception as exc:
            logger.warning("Failed to resolve user language: %s", exc)
            user_lang = "ru"

    generation_types = get_generation_types()
    total_models = len(get_models_sync())
    remaining_free = FREE_GENERATIONS_PER_DAY
    if user_id:
        try:
            from app.services.user_service import get_user_free_generations_remaining as get_free_remaining_async
            remaining_free = await get_free_remaining_async(user_id)
        except Exception as exc:
            logger.warning("Failed to resolve free generations: %s", exc)

    is_new = await is_new_user_async(user_id) if user_id else True
    referral_link = get_user_referral_link(user_id) if user_id else ""
    referrals_count = len(get_user_referrals(user_id)) if user_id else 0
    online_count = get_fake_online_count()

    if user_lang == "en":
        name = user.mention_html() if user else "friend"
    else:
        name = user.mention_html() if user else "друг"

    if is_new:
        header_text = t(
            "welcome_new",
            lang=user_lang,
            name=name,
            free=remaining_free if remaining_free > 0 else FREE_GENERATIONS_PER_DAY,
            free_limit=FREE_GENERATIONS_PER_DAY,
            models=total_models,
            types=len(generation_types),
            online=online_count,
            ref_bonus=REFERRAL_BONUS_GENERATIONS,
            ref_link=referral_link,
        )
        referral_bonus_text = ""
    else:
        referral_bonus_text = ""
        if referrals_count > 0:
            referral_bonus_text = t(
                "msg_referral_bonus",
                lang=user_lang,
                count=referrals_count,
                bonus=referrals_count * REFERRAL_BONUS_GENERATIONS,
            )

        header_text = t(
            "welcome_returning",
            lang=user_lang,
            name=name,
            online=online_count,
            free=remaining_free if remaining_free > 0 else FREE_GENERATIONS_PER_DAY,
            free_limit=FREE_GENERATIONS_PER_DAY,
            models=total_models,
            types=len(generation_types),
        )

    if user_lang == "en":
        header_text += "\n👇 Select a section from the menu below."
    else:
        header_text += "\n👇 Выберите раздел в меню ниже."

    from app.utils.singleton_lock import get_lock_admin_notice, get_lock_mode, is_lock_degraded

    is_admin_user = get_is_admin(user_id) if user_id else False
    admin_lock_notice = get_lock_admin_notice(user_lang) if is_admin_user else ""
    if admin_lock_notice:
        header_text += f"\n\n{admin_lock_notice}"
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else user_id,
        update_id=update.update_id,
        action="LOCK_STATUS",
        action_path="menu:lock_status",
        stage="UI_ROUTER",
        outcome="observed",
        param={
            "lock_mode": get_lock_mode(),
            "lock_degraded": is_lock_degraded(),
            "lock_notice": admin_lock_notice or None,
        },
    )

    details_parts = []
    if referral_bonus_text:
        details_parts.append(referral_bonus_text.strip())
    details_parts.append(
        t(
            "msg_full_functionality",
            lang=user_lang,
            remaining=remaining_free,
            total=FREE_GENERATIONS_PER_DAY,
            ref_bonus=REFERRAL_BONUS_GENERATIONS,
            ref_link=referral_link,
            models=total_models,
            types=len(generation_types),
        )
    )
    details_parts.append(_build_release_block(user_lang))
    details_text = "\n\n".join(part for part in details_parts if part)

    return header_text, details_text


def _split_text_by_delimiters(text: str, limit: int, delimiters: List[str]) -> List[str]:
    if len(text) <= limit:
        return [text]
    if not delimiters:
        return [text[i:i + limit] for i in range(0, len(text), limit)]

    delimiter = delimiters[0]
    parts = text.split(delimiter)
    chunks: List[str] = []
    current = ""

    for index, part in enumerate(parts):
        prefix = delimiter if index > 0 else ""
        segment = f"{prefix}{part}"
        if len(segment) > limit:
            if current:
                chunks.append(current)
                current = ""
            subchunks = _split_text_by_delimiters(part, limit, delimiters[1:])
            if prefix:
                if subchunks:
                    subchunks[0] = f"{prefix}{subchunks[0]}"
                else:
                    subchunks = [prefix]
            chunks.extend(subchunks)
            continue
        if len(current) + len(segment) <= limit:
            current += segment
        else:
            if current:
                chunks.append(current)
            current = segment

    if current:
        chunks.append(current)
    return chunks


def _find_split_index(text: str, max_len: int, delimiters: List[str]) -> int:
    for delimiter in delimiters:
        index = text.rfind(delimiter, 0, max_len + 1)
        if index != -1:
            return index + len(delimiter)
    return -1


def _split_html_text(text: str, limit: int, delimiters: List[str]) -> List[str]:
    tag_pattern = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)?>")
    void_tags = {"br", "img", "hr"}

    tokens: List[tuple[str, str]] = []
    last_end = 0
    for match in tag_pattern.finditer(text):
        if match.start() > last_end:
            tokens.append(("text", text[last_end:match.start()]))
        tokens.append(("tag", match.group(0)))
        last_end = match.end()
    if last_end < len(text):
        tokens.append(("text", text[last_end:]))

    stack: List[tuple[str, str]] = []
    chunks: List[str] = []
    current = ""

    def closing_len() -> int:
        return sum(len(f"</{name}>") for name, _ in stack)

    def flush_chunk() -> None:
        nonlocal current
        if not current:
            return
        closing_tags = "".join(f"</{name}>" for name, _ in reversed(stack))
        chunks.append(current + closing_tags)
        current = "".join(tag for _, tag in stack)

    for token_type, token_value in tokens:
        if token_type == "text":
            remaining = token_value
            while remaining:
                available = limit - len(current) - closing_len()
                if available <= 0:
                    flush_chunk()
                    continue
                if len(remaining) <= available:
                    current += remaining
                    break
                split_index = _find_split_index(remaining, available, delimiters)
                if split_index <= 0:
                    split_index = available
                segment = remaining[:split_index]
                current += segment
                remaining = remaining[split_index:]
                flush_chunk()
            continue

        match = tag_pattern.match(token_value)
        if not match:
            current += token_value
            continue
        is_closing = match.group(1) == "/"
        tag_name = match.group(2).lower()
        is_self_closing = token_value.endswith("/>") or tag_name in void_tags

        if is_closing and not any(name == tag_name for name, _ in stack):
            continue

        projected_stack = list(stack)
        if not is_self_closing:
            if is_closing:
                for index in range(len(projected_stack) - 1, -1, -1):
                    if projected_stack[index][0] == tag_name:
                        del projected_stack[index]
                        break
            else:
                projected_stack.append((tag_name, token_value))

        projected_closing_len = sum(len(f"</{name}>") for name, _ in projected_stack)
        if len(current) + len(token_value) + projected_closing_len > limit and current:
            flush_chunk()

        current += token_value
        if not is_self_closing:
            if is_closing:
                for index in range(len(stack) - 1, -1, -1):
                    if stack[index][0] == tag_name:
                        del stack[index]
                        break
            else:
                stack.append((tag_name, token_value))

    if current:
        flush_chunk()

    return chunks


def _is_safe_html_chunk(text: str) -> bool:
    if text.count("<") != text.count(">"):
        return False

    tag_pattern = re.compile(r"<(/?)([a-zA-Z0-9]+)(?:\\s[^>]*)?>")
    stack: List[str] = []
    for match in tag_pattern.finditer(text):
        tag = match.group(2).lower()
        if tag in {"br"}:
            continue
        if match.group(1) == "/":
            if not stack or stack[-1] != tag:
                return False
            stack.pop()
        else:
            stack.append(tag)
    return not stack


async def send_long_message(
    bot,
    chat_id: int,
    text: str,
    *,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    **kwargs: Any,
) -> List[Any]:
    if not text:
        return []

    if parse_mode == "HTML":
        chunks = _split_html_text(
            text,
            TELEGRAM_CHUNK_LIMIT,
            ["\n\n", "\n", " "],
        )
    else:
        chunks = _split_text_by_delimiters(
            text,
            TELEGRAM_CHUNK_LIMIT,
            ["\n\n", "\n", " "],
        )
    sent_messages = []
    total_chunks = len(chunks)

    for index, chunk in enumerate(chunks):
        message_kwargs = dict(kwargs)
        if disable_web_page_preview is not None:
            message_kwargs["disable_web_page_preview"] = disable_web_page_preview
        if index == total_chunks - 1 and reply_markup is not None:
            message_kwargs["reply_markup"] = reply_markup

        if parse_mode:
            message_kwargs["parse_mode"] = parse_mode

        sent_messages.append(
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                **message_kwargs,
            )
        )

    return sent_messages


async def ensure_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source: str,
    correlation_id: Optional[str] = None,
    prefer_edit: bool = True,
) -> dict:
    """Гарантирует MAIN_MENU и якорную клавиатуру после любых выходов."""
    result = await show_main_menu(
        update,
        context,
        source=source,
        correlation_id=correlation_id,
        prefer_edit=prefer_edit,
    )
    log_structured_event(
        correlation_id=result.get("correlation_id"),
        user_id=result.get("user_id"),
        chat_id=result.get("chat_id"),
        update_id=result.get("update_id"),
        action="MENU_ANCHOR_RENDER",
        action_path=f"menu_anchor:{source}",
        stage="UI_ROUTER",
        outcome="render",
        param={
            "source": source,
            "ui_context_before": result.get("ui_context_before"),
            "ui_context_after": result.get("ui_context_after"),
            "used_edit": result.get("used_edit"),
            "fallback_send": result.get("fallback_send"),
            "message_id": result.get("message_id"),
        },
    )
    return result


async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source: str = "unknown",
    *,
    correlation_id: Optional[str] = None,
    prefer_edit: bool = True,
) -> dict:
    """Показывает единое главное меню для всех входов."""
    user_id = update.effective_user.id if update.effective_user else None
    user_lang = "ru"
    if user_id:
        try:
            from app.services.user_service import get_user_language as get_user_language_async
            user_lang = await get_user_language_async(user_id)
        except Exception as exc:
            logger.warning("Failed to resolve user language: %s", exc)
    correlation_id = correlation_id or ensure_correlation_id(update, context)
    chat_id = None
    if update.effective_chat:
        chat_id = update.effective_chat.id
    elif user_id:
        chat_id = user_id
    ui_context_before = None
    if user_id and user_id in user_sessions:
        ui_context_before = user_sessions[user_id].get("ui_context")
    if user_id:
        reset_session_context(
            user_id,
            reason=f"show_main_menu:{source}",
            clear_gen_type=True,
            correlation_id=correlation_id,
            update_id=update.update_id,
            chat_id=chat_id,
        )
        set_session_context(
            user_id,
            to_context=UI_CONTEXT_MAIN_MENU,
            reason=f"show_main_menu:{source}",
            correlation_id=correlation_id,
            update_id=update.update_id,
            chat_id=chat_id,
        )
    reply_markup = InlineKeyboardMarkup(
        await build_main_menu_keyboard(user_id, user_lang=user_lang, is_new=False)
    )
    header_text, _details_text = await _build_main_menu_sections(update, correlation_id=correlation_id)
    welcome_hash = _safe_text_hash(header_text)
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="MENU_RENDER",
        action_path=f"menu:{source}",
        stage="UI_ROUTER",
        outcome="render",
        text_length=len(header_text) if header_text else 0,
        text_hash=welcome_hash,
        param={
            "ui_context": UI_CONTEXT_MAIN_MENU,
            "welcome_version": welcome_hash,
        },
    )
    logger.info(f"MAIN_MENU_SHOWN source={source} user_id={user_id}")

    used_edit = False
    fallback_send = False
    message_id = None

    if update.callback_query and prefer_edit:
        query = update.callback_query
        if len(header_text) <= TELEGRAM_TEXT_LIMIT:
            try:
                edit_result = await query.edit_message_text(
                    header_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
                used_edit = True
                message_id = getattr(edit_result, "message_id", None) or (
                    query.message.message_id if query.message else None
                )
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update.update_id,
                    action="MENU_RENDER",
                    action_path=f"menu:{source}",
                    stage="UI_ROUTER",
                    outcome="edit_ok",
                    text_hash=welcome_hash,
                    param={
                        "ui_context": UI_CONTEXT_MAIN_MENU,
                        "welcome_version": welcome_hash,
                    },
                )
                return {
                    "correlation_id": correlation_id,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "update_id": update.update_id,
                    "ui_context_before": ui_context_before,
                    "ui_context_after": UI_CONTEXT_MAIN_MENU,
                    "used_edit": used_edit,
                    "fallback_send": fallback_send,
                    "message_id": message_id,
                }
            except Exception as exc:
                fallback_send = True
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update.update_id,
                    action="MENU_RENDER",
                    action_path=f"menu:{source}",
                    stage="UI_ROUTER",
                    outcome="edit_failed",
                    error_code="MENU_EDIT_FAIL",
                    fix_hint=str(exc),
                    text_hash=welcome_hash,
                    param={
                        "ui_context": UI_CONTEXT_MAIN_MENU,
                        "welcome_version": welcome_hash,
                    },
                )

    if chat_id:
        send_result = await context.bot.send_message(
            chat_id=chat_id,
            text=header_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        message_id = getattr(send_result, "message_id", None)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="MENU_RENDER",
            action_path=f"menu:{source}",
            stage="UI_ROUTER",
            outcome="send_ok",
            text_hash=welcome_hash,
            param={
                "ui_context": UI_CONTEXT_MAIN_MENU,
                "welcome_version": welcome_hash,
            },
        )
    return {
        "correlation_id": correlation_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "update_id": update.update_id,
        "ui_context_before": ui_context_before,
        "ui_context_after": UI_CONTEXT_MAIN_MENU,
        "used_edit": used_edit,
        "fallback_send": fallback_send,
        "message_id": message_id,
    }


async def respond_price_undefined(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session: dict,
    user_lang: str,
    model_id: Optional[str],
    gen_type: Optional[str],
    sku_id: Optional[str],
    price_quote: Optional[dict],
    free_remaining: Optional[int],
    correlation_id: Optional[str],
    action_path: str,
    source: str = "price_undefined",
    prefer_edit: bool = True,
) -> None:
    """Respond to price undefined guard-block with warning logs and anchored main menu."""
    from app.pricing.free_policy import is_sku_free_daily

    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else user_id
    storage_mode = os.getenv("STORAGE_MODE", "unknown")
    free_remaining_value = free_remaining if free_remaining is not None else 0
    free_eligible = bool(sku_id and is_sku_free_daily(sku_id))
    price_quote_missing = price_quote is None

    if free_remaining_value > 0 and free_eligible and price_quote_missing:
        reason_code = "FREE_BYPASS_EXPECTED_BUT_MISSING_QUOTE"
        fix_hint = (
            "BUG: free_should_bypass_price=true but price_quote_missing=true; "
            "price_quote is None; run quote resolve; check YAML price mapping."
        )
    elif not sku_id:
        reason_code = "MODEL_HAS_NO_SKU"
        fix_hint = "model_id/gen_type did not resolve sku_id; check catalog mapping."
    elif "price_quote" not in session:
        reason_code = "QUOTE_RESOLVER_NOT_CALLED"
        fix_hint = "price_quote missing in session; ensure quote resolver is invoked."
    elif free_remaining_value == 0 and price_quote_missing:
        reason_code = "PAID_NO_QUOTE"
        fix_hint = "paid flow missing quote; check pricing resolver and YAML mappings."
    else:
        reason_code = "PRICE_MAP_MISSING_FOR_SKU"
        fix_hint = "price mapping missing for sku_id; check pricing catalog."

    param_snapshot = {
        "gen_type": gen_type,
        "model_id": model_id,
        "sku_id": sku_id,
        "ui_context": session.get("ui_context"),
        "waiting_for": session.get("waiting_for"),
        "free_remaining": free_remaining_value,
        "storage_mode": storage_mode,
    }
    welcome_version = session.get("welcome_version") if isinstance(session, dict) else None

    _log_structured_warning(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="PRICE_UNDEFINED",
        action_path=action_path,
        model_id=model_id,
        gen_type=gen_type,
        sku_id=sku_id,
        stage="PRICE_RESOLVE",
        outcome="blocked",
        error_code=reason_code,
        fix_hint=fix_hint,
        param={
            "reason_code": reason_code,
            "param_snapshot": param_snapshot,
            "free_eligible": free_eligible,
            "free_remaining": free_remaining_value,
            "storage_mode": storage_mode,
            "welcome_version": welcome_version,
        },
    )
    _log_structured_warning(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="GUARD_BLOCK",
        action_path=action_path,
        model_id=model_id,
        gen_type=gen_type,
        sku_id=sku_id,
        stage="PRICE_RESOLVE",
        outcome="blocked",
        error_code=reason_code,
        fix_hint=fix_hint,
        param={
            "reason_code": reason_code,
            "reason": "price_undefined",
            "param_snapshot": param_snapshot,
        },
    )

    message_text = (
        "❌ <b>Цена не определена</b>\n\n"
        "Причина: цена для модели не найдена.\n"
        "Пожалуйста, выберите другую модель или попробуйте позже."
        if user_lang == "ru"
        else (
            "❌ <b>Price is unavailable</b>\n\n"
            "Reason: pricing for this model is missing.\n"
            "Please select another model or try again later."
        )
    )

    sent = False
    if update.callback_query and prefer_edit:
        try:
            await update.callback_query.edit_message_text(message_text, parse_mode="HTML")
            sent = True
        except Exception as exc:
            logger.warning("Price undefined edit failed: %s", exc)
    if not sent:
        if update.message:
            await update.message.reply_text(message_text, parse_mode="HTML")
        elif chat_id:
            await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode="HTML")

    await ensure_main_menu(
        update,
        context,
        source=source,
        correlation_id=correlation_id,
        prefer_edit=False,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единый стартовый UX: главное меню."""
    start_ts = time.monotonic()
    try:
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        upsert_user_registry_entry(update.effective_user)
        correlation_id = ensure_correlation_id(update, context)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="COMMAND_START",
            action_path="command:/start",
            outcome="received",
        )
        if _should_dedupe_update(
            update,
            context,
            action="COMMAND_START",
            action_path="command:/start",
            user_id=user_id,
            chat_id=chat_id,
        ):
            return
        logger.info(f"🔥 /start command received from user_id={user_id if user_id else 'None'}")
        try:
            await show_main_menu(update, context, source="/start")
        except Exception as exc:
            logger.error("❌ /start handler failed: %s", exc, exc_info=True)
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update.update_id,
                action="COMMAND_START",
                action_path="command:/start",
                stage="UI_ROUTER",
                outcome="failed",
                error_code="ERR_TG_START_HANDLER",
                fix_hint="Проверьте обработчик /start и доступность меню.",
            )
            message = (
                "❌ <b>Не удалось открыть меню</b>\n\n"
                "Что случилось: ошибка обработки команды /start.\n"
                "Что сделать: попробуйте снова через /start.\n"
                "Код: <code>ERR_TG_START_HANDLER</code>"
            )
            if update.message:
                await update.message.reply_text(message, parse_mode="HTML")
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(message, parse_mode="HTML")
    finally:
        _log_handler_latency("start", start_ts, update)


async def reset_wizard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Safely reset wizard state and return to main menu."""
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    correlation_id = ensure_correlation_id(update, context)
    if user_id:
        clear_user_session(user_id, reason="command:/reset")
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="COMMAND_RESET",
        action_path="command:/reset",
        outcome="processed",
    )
    await show_main_menu(update, context, source="/reset")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        '📋 <b>Доступные команды:</b>\n\n'
        '/start - Начать работу с ботом\n'
        '/models - Показать список доступных моделей\n'
        '/generate - Начать генерацию контента\n'
        '/balance - Проверить баланс\n'
        '/cancel - Отменить текущую операцию\n'
        '/search [запрос] - Поиск в базе знаний\n'
        '/ask [вопрос] - Задать вопрос\n'
        '/add [знание] - Добавить знание в базу\n\n'
        '💡 <b>Как использовать:</b>\n'
        '1. Используйте /models чтобы увидеть доступные модели\n'
        '2. Используйте /balance чтобы проверить баланс\n'
        '3. Используйте /generate чтобы начать генерацию\n'
        '4. Выберите модель из списка\n'
        '5. Введите необходимые параметры\n'
        '6. Получите результат!',
        parse_mode='HTML'
    )


async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available models from static menu."""
    user_id = update.effective_user.id
    
    # Get models grouped by category
    categories = get_categories_from_registry()
    
    # Create category selection keyboard
    keyboard = []
    for category in categories:
        models_in_category = get_models_by_category_from_registry(category)
        emoji = models_in_category[0]["emoji"] if models_in_category else "📦"
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {category} ({len(models_in_category)})",
            callback_data=f"category:{category}"
        )])
    
    user_lang = get_user_language(update.effective_user.id)
    keyboard.append([InlineKeyboardButton(t('btn_all_models_short', lang=user_lang), callback_data="all_models")])
    keyboard.append([
        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
    ])
    keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    models_text = "📋 <b>Доступные модели:</b>\n\n"
    models_text += "Выберите категорию или просмотрите все модели:\n\n"
    for category in categories:
        models_in_category = get_models_by_category_from_registry(category)
        models_text += f"<b>{category}</b>: {len(models_in_category)} моделей\n"
    
    await update.message.reply_text(
        models_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def start_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the generation process."""
    start_ts = time.monotonic()
    try:
        global kie
        user_id = update.effective_user.id
        
        # Check if KIE API is configured (initialize if needed)
        if kie is None:
            kie = get_client()
        if not kie.api_key:
            await update.message.reply_text(
                '❌ API не настроен. Укажите API ключ в файле .env'
            )
            return
        
        await update.message.reply_text(
            '🚀 Начинаем генерацию!\n\n'
            'Сначала выберите модель из списка:',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Показать модели", callback_data="show_models")
            ]])
        )
        
        return SELECTING_MODEL
    finally:
        _log_handler_latency("start_generation", start_ts, update)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Latency wrapper for button callbacks."""
    start_ts = time.monotonic()
    query = update.callback_query
    update_id = getattr(update, "update_id", None)
    callback_answered = False
    try:
        if query:
            try:
                await query.answer()
                callback_answered = True
                if update_id is not None:
                    track_outgoing_action(update_id, action_type="answerCallbackQuery")
            except Exception as answer_error:
                logger.warning("Could not answer callback query quickly: %s", answer_error)

        acquired = False
        if _callback_semaphore:
            try:
                await asyncio.wait_for(
                    _callback_semaphore.acquire(),
                    timeout=CALLBACK_CONCURRENCY_TIMEOUT_SECONDS,
                )
                acquired = True
            except asyncio.TimeoutError:
                user_id = update.effective_user.id if update.effective_user else None
                user_lang = get_user_language(user_id) if user_id else "ru"
                busy_text = (
                    "⏳ <b>Сервер занят</b>\n\nПопробуйте снова через пару секунд."
                    if user_lang == "ru"
                    else "⏳ <b>Server busy</b>\n\nPlease try again in a few seconds."
                )
                reply_markup = build_back_to_menu_keyboard(user_lang)
                if query and query.message:
                    try:
                        await query.message.reply_text(
                            busy_text,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                        if update_id is not None:
                            track_outgoing_action(update_id, action_type="send_message")
                    except Exception:
                        logger.warning("Failed to send busy response to user", exc_info=True)
                return ConversationHandler.END
        try:
            return await _button_callback_impl(update, context, callback_answered=callback_answered)
        finally:
            if acquired and _callback_semaphore:
                _callback_semaphore.release()
    finally:
        _log_handler_latency("button_callback", start_ts, update)


async def show_admin_generation(query, context, gen: dict, current_index: int, total_count: int):
    """Show admin generation with navigation."""
    try:
        from datetime import datetime
        
        gen_id = gen.get('id', 0)
        user_id = gen.get('user_id', 0)
        model_id = gen.get('model_id', 'Unknown')
        model_name = gen.get('model_name', model_id)
        timestamp = gen.get('timestamp', 0)
        price = gen.get('price', 0)
        is_free = gen.get('is_free', False)
        result_urls = gen.get('result_urls', [])
        params = gen.get('params', {})
        
        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        else:
            date_str = "Неизвестно"
        
        user_link = f"tg://user?id={user_id}"
        user_lang = get_user_language(query.from_user.id)
        
        if user_lang == 'ru':
            gen_text = (
                f"📚 <b>Генерация #{gen_id}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <a href=\"{user_link}\">Пользователь {user_id}</a>\n"
                f"📅 <b>Дата:</b> {date_str}\n"
                f"🤖 <b>Модель:</b> {model_name}\n"
                f"💰 <b>Стоимость:</b> {'🎁 Бесплатно' if is_free else format_rub_amount(price)}\n"
                f"📦 <b>Результатов:</b> {len(result_urls)}\n\n"
            )
            
            if params:
                params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in list(params.items())[:5]])
                gen_text += f"⚙️ <b>Параметры:</b>\n{params_text}\n\n"
            
            gen_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            gen_text += f"📄 {current_index + 1} из {total_count}"
        else:
            gen_text = (
                f"📚 <b>Generation #{gen_id}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <a href=\"{user_link}\">User {user_id}</a>\n"
                f"📅 <b>Date:</b> {date_str}\n"
                f"🤖 <b>Model:</b> {model_name}\n"
                f"💰 <b>Cost:</b> {'🎁 Free' if is_free else format_rub_amount(price)}\n"
                f"📦 <b>Results:</b> {len(result_urls)}\n\n"
            )
            
            if params:
                params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in list(params.items())[:5]])
                gen_text += f"⚙️ <b>Parameters:</b>\n{params_text}\n\n"
            
            gen_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            gen_text += f"📄 {current_index + 1} of {total_count}"
        
        keyboard = []
        
        # Navigation buttons
        if total_count > 1:
            keyboard.append([
                InlineKeyboardButton(t('btn_previous', lang=user_lang), callback_data=f"admin_gen_nav:prev"),
                InlineKeyboardButton(t('btn_next', lang=user_lang), callback_data=f"admin_gen_nav:next")
            ])
        
        # View result button
        if result_urls:
            keyboard.append([
                InlineKeyboardButton(t('btn_view_result', lang=user_lang), callback_data=f"admin_gen_view:{current_index}")
            ])
        
        # Back button
        keyboard.append([
            InlineKeyboardButton(t('btn_back_to_admin', lang=user_lang), callback_data="admin_stats")
        ])
        
        await query.edit_message_text(
            gen_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=False
        )
    except Exception as e:
        logger.error(f"Error showing admin generation: {e}", exc_info=True)
        user_lang = get_user_language(query.from_user.id)
        await query.answer(t('error_display_generation', lang=user_lang), show_alert=True)


async def show_payment_screenshot(query, payment: dict, current_index: int, total_count: int):
    """Show payment screenshot with navigation."""
    try:
        import datetime
        
        payment_id = payment.get('id', 0)
        user_id = payment.get('user_id', 0)
        amount = payment.get('amount', 0)
        timestamp = payment.get('timestamp', 0)
        screenshot_file_id = payment.get('screenshot_file_id')
        
        if not screenshot_file_id:
            await query.edit_message_text("❌ Скриншот не найден для этого платежа.")
            return
        
        # Format payment info
        amount_str = format_rub_amount(amount)
        if timestamp:
            dt = datetime.datetime.fromtimestamp(timestamp)
            date_str = dt.strftime("%d.%m.%Y %H:%M")
        else:
            date_str = "Неизвестно"
        
        user_link = f"tg://user?id={user_id}"
        caption = (
            f"📸 <b>Скриншот платежа #{payment_id}</b>\n\n"
            f"👤 <a href=\"{user_link}\">Пользователь {user_id}</a>\n"
            f"💵 Сумма: {amount_str}\n"
            f"📅 Дата: {date_str}\n\n"
            f"📄 {current_index + 1} из {total_count}"
        )
        
        # Create navigation keyboard
        keyboard = []
        nav_row = []
        
        if total_count > 1:
            if current_index > 0:
                nav_row.append(InlineKeyboardButton("◀️ Предыдущий", callback_data="payment_screenshot_nav:prev"))
            if current_index < total_count - 1:
                nav_row.append(InlineKeyboardButton("Следующий ▶️", callback_data="payment_screenshot_nav:next"))
            
            if nav_row:
                keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("📊 Назад к платежам", callback_data="admin_payments_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Send photo with caption
        try:
            # Edit original message first to show we're loading
            await query.edit_message_text(
                f"📸 <b>Загрузка скриншота...</b>\n\n"
                f"Платеж #{payment_id}",
                parse_mode='HTML'
            )
            
            # Send photo as new message
            await query.message.reply_photo(
                photo=screenshot_file_id,
                caption=caption,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error sending payment screenshot: {e}")
            await query.edit_message_text(
                f"❌ <b>Ошибка при загрузке скриншота</b>\n\n"
                f"Платеж #{payment_id}\n"
                f"Пользователь: {user_id}\n"
                f"Сумма: {amount_str} ₽\n"
                f"Дата: {date_str}\n\n"
                f"⚠️ Скриншот недоступен (возможно, файл удален или недоступен)",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in show_payment_screenshot: {e}", exc_info=True)
        try:
            await query.edit_message_text("❌ Произошла ошибка при отображении скриншота.")
        except:
            pass


async def _button_callback_impl(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    callback_answered: bool = False,
):
    """Handle button callbacks. CRITICAL: Always calls query.answer() to prevent button hanging."""
    import time
    start_time = time.time()
    query = None
    user_id = None
    data = None
    user_lang = 'ru'
    is_admin_user = False
    session_store = get_session_store(context)
    
    # ==================== NO-SILENCE GUARD: Track outgoing actions ====================
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action
    guard = get_no_silence_guard()
    update_id = update.update_id
    correlation_id = ensure_correlation_id(update, context)
    # ==================== END NO-SILENCE GUARD ====================
    
    # 🔥 MAXIMUM LOGGING: Log entry point
    try:
        query = update.callback_query
        user_id = query.from_user.id if query and query.from_user else None
        data = query.data if query else None
        if query and query.from_user:
            upsert_user_registry_entry(query.from_user)
        correlation_id = ensure_correlation_id(update, context)
        chat_id = query.message.chat_id if query and query.message else None
        message_id = query.message.message_id if query and query.message else None
        guard.set_trace_context(
            update,
            context,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            message_id=message_id,
            update_type="callback",
            correlation_id=correlation_id,
            action="CALLBACK",
            action_path=build_action_path(data),
            stage="UI_ROUTER",
        )
        trace_event(
            "info",
            correlation_id,
            event="TRACE_IN",
            stage="UI_ROUTER",
            update_type="callback",
            action="CALLBACK",
            action_path=build_action_path(data),
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            callback_data=data,
            route_decision="button_callback",
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="CALLBACK",
            action_path=build_action_path(data),
            outcome="received",
        )
        session = get_session_cached(context, session_store, user_id, update_id, default={}) if user_id is not None else {}
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="UX_CLICK",
            action_path=build_action_path(data),
            model_id=session.get("model_id") if isinstance(session, dict) else None,
            param={
                "waiting_for": session.get("waiting_for") if isinstance(session, dict) else None,
                "current_param": session.get("current_param") if isinstance(session, dict) else None,
                "callback_data": data,
            },
            outcome="received",
            error_code="UX_CLICK_OK",
            fix_hint="Обработано нажатие кнопки.",
        )
        session_get_count = get_session_get_count(context, update_id)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="SESSION_GET_COUNT",
            action_path=build_action_path(data),
            stage="SESSION_CACHE",
            outcome="count",
            param={"count": session_get_count},
        )
        logger.debug(f"🔥🔥🔥 BUTTON_CALLBACK ENTRY: user_id={user_id}, data={data}, query_id={query.id if query else 'None'}, message_id={query.message.message_id if query and query.message else 'None'}")
    except Exception as e:
        logger.error(f"❌❌❌ ERROR in button_callback entry logging: {e}", exc_info=True)
    
    # CRITICAL: Always answer callback query to prevent button hanging
    # This must be done FIRST, before any other operations
    try:
        query = update.callback_query
        if not query:
            logger.error("No callback_query in update")
            return ConversationHandler.END
        
        user_id = update.effective_user.id if update.effective_user else None
        data = query.data if query else None
        is_admin_user = get_is_admin(user_id) if user_id else False
        
        # ALWAYS answer callback immediately to prevent button hanging
        # This is critical - if we don't answer, button will hang
        if not callback_answered:
            try:
                await query.answer()
                callback_answered = True
                # NO-SILENCE GUARD: Track outgoing action
                track_outgoing_action(update_id, action_type="answerCallbackQuery")
            except Exception as answer_error:
                logger.warning(f"Could not answer callback query: {answer_error}")
                try:
                    if context and query and query.id:
                        await context.bot.answer_callback_query(query.id)
                except Exception:
                    pass
                # Continue anyway - better to process than to fail completely
        
        if _should_dedupe_update(
            update,
            context,
            action="CALLBACK",
            action_path=build_action_path(data),
            user_id=user_id,
            chat_id=query.message.chat_id if query and query.message else None,
        ):
            return ConversationHandler.END

        logger.info(f"Button callback received: user_id={user_id}, data='{data}'")
        
        if not data:
            logger.error("No data in callback_query")
            try:
                user_lang = get_user_language(user_id) if user_id else 'ru'
                await query.answer(t('error_no_data', lang=user_lang), show_alert=True)
            except:
                try:
                    await query.answer("❌ Ошибка: нет данных в кнопке", show_alert=True)
                except:
                    pass
            return ConversationHandler.END
        
        # Get user language early for error messages
        try:
            user_lang = get_user_language(user_id) if user_id else 'ru'
        except:
            user_lang = 'ru'

        if context and getattr(context, "user_data", None) is not None:
            context.user_data["last_callback_handled_update_id"] = update_id

        if data.startswith("type_header:"):
            model_type = data.split(":", 1)[1] if ":" in data else ""
            user_lang = get_user_language(user_id) if user_id else "ru"
            from app.helpers.models_menu import build_models_menu_for_type, get_type_label

            keyboard_markup, models_count = build_models_menu_for_type(user_lang, model_type)
            type_label = get_type_label(model_type, user_lang)
            if user_lang == "ru":
                header_text = (
                    f"📂 <b>Раздел:</b> {type_label}\n\n"
                    f"Доступно моделей: <b>{models_count}</b>\n\n"
                    "Выберите модель ниже."
                )
            else:
                header_text = (
                    f"📂 <b>Section:</b> {type_label}\n\n"
                    f"Available models: <b>{models_count}</b>\n\n"
                    "Select a model below."
                )
            try:
                await query.edit_message_text(
                    header_text,
                    reply_markup=keyboard_markup,
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning("Failed to render type filter menu: %s", exc)
                try:
                    await query.message.reply_text(
                        header_text,
                        reply_markup=keyboard_markup,
                        parse_mode="HTML",
                    )
                except Exception:
                    await query.answer("⚠️ Не удалось открыть раздел", show_alert=True)
            return SELECTING_MODEL

        if data == "other_models":
            try:
                await query.answer()
            except Exception as exc:
                logger.warning("Error answering callback for other_models: %s", exc)
            user_lang = get_user_language(user_id) if user_id else "ru"
            reset_session_context(
                user_id,
                reason="other_models",
                clear_gen_type=True,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            set_session_context(
                user_id,
                to_context=UI_CONTEXT_MODEL_MENU,
                reason="other_models",
                clear_gen_type=True,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            try:
                from app.helpers.models_menu_handlers import handle_model_callback
                await handle_model_callback(
                    query,
                    user_id,
                    user_lang,
                    "model:sora-watermark-remover",
                )
                return SELECTING_MODEL
            except Exception as exc:
                logger.error("Error in other_models handler: %s", exc, exc_info=True)
                fallback_text = (
                    "❌ Не удалось открыть модель. Попробуйте позже."
                    if user_lang == "ru"
                    else "❌ Unable to open model. Please try again later."
                )
                try:
                    await query.answer(fallback_text, show_alert=True)
                except Exception:
                    pass
                await show_main_menu(update, context, source="other_models_error")
                return ConversationHandler.END

        if data == "reset_step":
            session_store.clear(user_id)
            await show_main_menu(update, context, source="reset_step")
            track_outgoing_action(update_id, action_type="edit_message_text")
            return ConversationHandler.END

        if data == "reset_wizard":
            session_store.clear(user_id)
            await show_main_menu(update, context, source="reset_wizard")
            track_outgoing_action(update_id, action_type="edit_message_text")
            return ConversationHandler.END

        # 🔥🔥🔥 SUPER-DETAILED CONTEXT LOGGING
        try:
            session = get_session_cached(context, session_store, user_id, update_id, default=None) if user_id else None
            session_keys = list(session.keys()) if session else []
            session_model_id = session.get('model_id') if session else None
            session_waiting_for = session.get('waiting_for') if session else None
            session_current_param = session.get('current_param') if session else None
            session_params_keys = list(session.get('params', {}).keys()) if session else []
            session_required = session.get('required', []) if session else []
            session_properties_keys = list(session.get('properties', {}).keys()) if session else []
            chat_id = query.message.chat_id if query and query.message else None
            message_id = query.message.message_id if query and query.message else None
            if DEBUG_VERBOSE_LOGS:
                logger.info(
                    "BUTTON_CALLBACK_CONTEXT "
                    "user_id=%s data=%s chat_id=%s message_id=%s update_id=%s user_lang=%s "
                    "session_exists=%s model_id=%s waiting_for=%s current_param=%s "
                    "params_keys=%s required=%s properties_keys=%s session_keys=%s",
                    user_id,
                    data,
                    chat_id,
                    message_id,
                    update_id,
                    user_lang,
                    bool(session),
                    session_model_id,
                    session_waiting_for,
                    session_current_param,
                    session_params_keys[:15],
                    session_required[:15],
                    session_properties_keys[:15],
                    session_keys[:15],
                )
            try:
                trace_event(
                    "info",
                    correlation_id,
                    event="TRACE_IN",
                    stage="SESSION_LOAD",
                    update_type="callback",
                    action="CALLBACK",
                    action_path=build_action_path(data),
                    user_id=user_id,
                    chat_id=chat_id,
                    session_exists=bool(session),
                    model_id=session_model_id,
                    waiting_for=session_waiting_for,
                    current_param=session_current_param,
                    params_keys=session_params_keys[:15],
                    required=session_required[:15],
                    param_order=session.get("param_order")[:15] if session and session.get("param_order") else None,
                )
            except Exception as trace_exc:
                logger.warning("TRACE session load failed: %s", trace_exc, exc_info=True)
            try:
                correlation_id = None
                if context and getattr(context, "user_data", None) is not None:
                    if context.user_data.get("correlation_update_id") == update_id:
                        correlation_id = context.user_data.get("correlation_id")
                    if not correlation_id:
                        correlation_id = get_correlation_id(update_id, user_id)
                        context.user_data["correlation_id"] = correlation_id
                        context.user_data["correlation_update_id"] = update_id
                else:
                    correlation_id = get_correlation_id(update_id, user_id)

                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update_id,
                    action="CALLBACK",
                    action_path=build_action_path(data),
                    model_id=session_model_id,
                    gen_type=session.get('gen_type') if session else None,
                    stage="router",
                    waiting_for=session_waiting_for,
                    param=session_current_param,
                    outcome="received",
                    duration_ms=int((time.time() - start_time) * 1000),
                    error_code=None,
                    fix_hint=None,
                )
            except Exception as structured_log_error:
                logger.warning(
                    f"STRUCTURED_LOG error: {structured_log_error}",
                    exc_info=True,
                )
        except Exception as log_error:
            logger.error(f"❌❌❌ ERROR in BUTTON_CALLBACK CONTEXT logging: {log_error}", exc_info=True)
            
    except Exception as e:
        logger.error(f"Error in button_callback setup: {e}", exc_info=True)
        # Try to answer anyway if we have query
        if query:
            try:
                await query.answer("❌ Ошибка обработки кнопки. Попробуйте /start", show_alert=True)
            except:
                pass
        return ConversationHandler.END
    
    # Wrap all callback handling in try-except for error handling
    try:
        # Initialize common variables that might be used in multiple handlers
        # This prevents UnboundLocalError if variable is assigned in one branch but used in another
        categories = None
        total_models = None
        tutorial_text = None
        help_text = None
        referral_text = None
        history_text = None
        model_info_text = None
        prompt_text = None
        admin_text = None
        settings_text = None
        promocodes_text = None
        broadcast_text = None
        stats_text = None
        
        # Handle claim gift
        if data == "claim_gift":
            if has_claimed_gift(user_id):
                user_lang = get_user_language(user_id)
                await query.answer(t('error_already_claimed', lang=user_lang), show_alert=True)
                return ConversationHandler.END
            
            user_lang = get_user_language(user_id)
            
            # Show initial spinning message
            await query.answer(t('msg_spinning_wheel', lang=user_lang))
            if user_lang == 'ru':
                spin_message = await query.edit_message_text(
                    "🎰 <b>КОЛЕСО ФОРТУНЫ</b> 🎰\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🎲 <b>Крутим колесо...</b>\n\n"
                    "⏳ Подождите, определяем ваш выигрыш...",
                    parse_mode='HTML'
                )
            else:
                spin_message = await query.edit_message_text(
                    "🎰 <b>WHEEL OF FORTUNE</b> 🎰\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🎲 <b>Spinning the wheel...</b>\n\n"
                    "⏳ Please wait, determining your prize...",
                    parse_mode='HTML'
                )
            
            # Animate wheel spinning with different sectors
            wheel_sectors = [
                ("🎯", "🎪", "🎨", "🎭", "🎪", "🎯"),
                ("💰", "💎", "🎁", "⭐", "💎", "💰"),
                ("🎰", "🎲", "🎯", "🎪", "🎲", "🎰"),
                ("💫", "✨", "🌟", "⭐", "✨", "💫"),
                ("🎊", "🎉", "🎈", "🎁", "🎉", "🎊")
            ]
            
            progress_steps = [
                ("🔄", "🔄", "🔄", "🔄", "🔄", "🔄"),
                ("⚡", "⚡", "⚡", "⚡", "⚡", "⚡"),
                ("✨", "✨", "✨", "✨", "✨", "✨"),
                ("💫", "💫", "💫", "💫", "💫", "💫"),
                ("🎯", "🎯", "🎯", "🎯", "🎯", "🎯")
            ]
            
            # Show spinning animation
            for i in range(8):
                await asyncio.sleep(0.25)
                sector_idx = i % len(wheel_sectors)
                progress_idx = min(i, len(progress_steps) - 1)
                
                wheel_display = " ".join(wheel_sectors[sector_idx])
                progress_display = " ".join(progress_steps[progress_idx])
                
                # Progress bar simulation
                progress_percent = min((i + 1) * 12.5, 100)
                progress_bar = "█" * int(progress_percent / 5) + "░" * (20 - int(progress_percent / 5))
                
                try:
                    if user_lang == 'ru':
                        await spin_message.edit_text(
                            f"🎰 <b>КОЛЕСО ФОРТУНЫ</b> 🎰\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{wheel_display}\n\n"
                            f"<b>Крутим...</b> {progress_display}\n\n"
                            f"📊 [{progress_bar}] {progress_percent:.0f}%\n\n"
                            f"⏳ Подождите, определяем ваш выигрыш...",
                            parse_mode='HTML'
                        )
                    else:
                        await spin_message.edit_text(
                            f"🎰 <b>WHEEL OF FORTUNE</b> 🎰\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{wheel_display}\n\n"
                            f"<b>Spinning...</b> {progress_display}\n\n"
                            f"📊 [{progress_bar}] {progress_percent:.0f}%\n\n"
                            f"⏳ Please wait, determining your prize...",
                            parse_mode='HTML'
                        )
                except:
                    pass
            
            # Final spin - slow down
            await asyncio.sleep(0.4)
            
            # Get the gift amount
            amount = spin_gift_wheel()
            await add_user_balance_async(user_id, amount)
            set_gift_claimed(user_id)
            
            # Show result with celebration
            if user_lang == 'ru':
                gift_text = (
                    f'🎉 <b>ПОЗДРАВЛЯЕМ!</b> 🎉\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'🎰 <b>КОЛЕСО ОСТАНОВИЛОСЬ!</b> 🎰\n\n'
                    f'🎁 <b>Ваш выигрыш:</b>\n\n'
                    f'💰 <b>{format_rub_amount(amount)}</b>\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'✅ <b>Сумма автоматически зачислена на ваш баланс!</b>\n\n'
                    f'💡 <b>Что дальше:</b>\n'
                    f'• Начните генерацию контента прямо сейчас\n'
                    f'• Используйте любую модель из каталога\n'
                    f'• Наслаждайтесь премиум возможностями!\n\n'
                    f'✨ <b>Удачи в создании контента!</b>'
                )
            else:
                gift_text = (
                    f'🎉 <b>CONGRATULATIONS!</b> 🎉\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'🎰 <b>WHEEL STOPPED!</b> 🎰\n\n'
                    f'🎁 <b>Your prize:</b>\n\n'
                    f'💰 <b>{format_rub_amount(amount)}</b>\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'✅ <b>Amount automatically added to your balance!</b>\n\n'
                    f'💡 <b>What\'s next:</b>\n'
                    f'• Start content generation right now\n'
                    f'• Use any model from the catalog\n'
                    f'• Enjoy premium features!\n\n'
                    f'✨ <b>Good luck creating content!</b>'
                )
            
            keyboard = [
                [InlineKeyboardButton(t('btn_check_balance', lang=user_lang), callback_data="check_balance")],
                [InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")]
            ]
            
            await spin_message.edit_text(
                gift_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        # Handle admin user mode toggle (MUST be first, before any other checks)
        if data == "admin_user_mode":
            # Toggle user mode for admin
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            session = ensure_session_cached(context, session_store, user_id, update_id)
            
            current_mode = session.get('admin_user_mode', False)
            session['admin_user_mode'] = not current_mode
            
            if not current_mode:
                # Switching to user mode - send new message directly
                user_lang = get_user_language(user_id)
                await query.answer(t('msg_user_mode_enabled', lang=user_lang))
                user = update.effective_user
                categories = get_categories_from_registry()
                total_models = len(get_models_sync())
                
                remaining_free = await get_user_free_generations_remaining(user_id)
                free_info = ""
                if remaining_free > 0:
                    free_info = f"\n🎁 <b>Бесплатно:</b> {remaining_free} генераций бесплатных моделей\n"
                
                welcome_text = (
                    f'✨ <b>ПРЕМИУМ AI MARKETPLACE</b> ✨\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'👋 Привет, {user.mention_html()}!\n\n'
                    f'🚀 <b>Топовые нейросети без VPN</b>\n'
                    f'📦 <b>{total_models} моделей</b> | <b>{len(categories)} категорий</b>{free_info}\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💎 <b>Преимущества:</b>\n'
                    f'• Прямой доступ к мировым AI\n'
                    f'• Профессиональное качество 2K/4K\n'
                    f'• Мгновенная генерация\n\n'
                    f'🎯 <b>Выберите категорию или все модели</b>'
                )
                
                keyboard = []
                # All models button first
                keyboard.append([
                    InlineKeyboardButton("📋 Все модели", callback_data="all_models")
                ])
                
                keyboard.append([])
                for category in categories:
                    models_in_category = get_models_by_category_from_registry(category)
                    emoji = models_in_category[0]["emoji"] if models_in_category else "📦"
                    keyboard.append([InlineKeyboardButton(
                        f"{emoji} {category} ({len(models_in_category)})",
                        callback_data=f"category:{category}"
                    )])
                
                keyboard.append([
                    InlineKeyboardButton("💳 Пополнить баланс", callback_data="topup_balance")
                ])
                keyboard.append([
                    InlineKeyboardButton("🔙 Вернуться в админ-панель", callback_data="admin_back_to_admin")
                ])
                keyboard.append([
                    InlineKeyboardButton("🆘 Помощь", callback_data="help_menu"),
                    InlineKeyboardButton("💬 Поддержка", callback_data="support_contact")
                ])
                
                await query.message.reply_text(
                    welcome_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            else:
                # Switching back to admin mode - send new message with full admin panel
                session = ensure_session_cached(context, session_store, user_id, update_id)
                session['admin_user_mode'] = False
                user_lang = get_user_language(user_id)
                await query.answer(t('msg_returning_to_admin', lang=user_lang))
                user = update.effective_user
                generation_types = get_generation_types()
                total_models = len(get_models_sync())
                
                welcome_text = (
                    f'👑 ✨ <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b> ✨\n\n'
                    f'Привет, {user.mention_html()}! 👋\n\n'
                    f'🎯 <b>ПОЛНЫЙ КОНТРОЛЬ НАД AI MARKETPLACE</b>\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'📊 <b>СТАТИСТИКА СИСТЕМЫ:</b>\n\n'
                    f'✅ <b>{total_models} премиум моделей</b> в арсенале\n'
                    f'✅ <b>{len(generation_types)} категорий</b> контента\n'
                    f'✅ Безлимитный доступ ко всем генерациям\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'🔥 <b>ТОПОВЫЕ МОДЕЛИ В СИСТЕМЕ:</b>\n\n'
                    f'🎨 <b>Google Imagen 4 Ultra</b> - Флагман от Google DeepMind\n'
                    f'   💰 Безлимит (цена: 4.63 ₽)\n'
                    f'   ⭐️ Максимальное качество для тестирования\n\n'
                    f'🍌 <b>Nano Banana Pro</b> - 4K от Google\n'
                    f'   💰 Безлимит (1K/2K: 6.95 ₽, 4K: 9.27 ₽)\n'
                    f'   🎯 Профессиональная генерация 2K/4K\n\n'
                    f'🎥 <b>Sora 2</b> - Видео от OpenAI\n'
                    f'   💰 Безлимит (цена: 11.58 ₽) за 10-секундное видео\n'
                    f'   🎬 Кинематографические видео с аудио\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'⚙️ <b>АДМИНИСТРАТИВНЫЕ ВОЗМОЖНОСТИ:</b>\n\n'
                    f'📈 Просмотр статистики и аналитики\n'
                    f'👥 Управление пользователями\n'
                    f'🎁 Управление промокодами\n'
                    f'🧪 Тестирование OCR системы\n'
                    f'💼 Полный контроль над ботом\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💫 <b>НАЧНИТЕ УПРАВЛЕНИЕ ИЛИ ТЕСТИРОВАНИЕ!</b>'
                )
                
                keyboard = []
                # All models button first
                keyboard.append([
                    InlineKeyboardButton("📋 Все модели", callback_data="all_models")
                ])
                
                keyboard.append([])
                for category in categories:
                    models_in_category = get_models_by_category_from_registry(category)
                    emoji = models_in_category[0]["emoji"] if models_in_category else "📦"
                    keyboard.append([InlineKeyboardButton(
                        f"{emoji} {category} ({len(models_in_category)})",
                        callback_data=f"category:{category}"
                    )])
                
                keyboard.append([
                    InlineKeyboardButton("📋 Все модели", callback_data="all_models")
                ])
                keyboard.append([
                    InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
                    InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")
                ])
                keyboard.append([
                    InlineKeyboardButton("🔍 Поиск", callback_data="admin_search"),
                    InlineKeyboardButton("📝 Добавить", callback_data="admin_add")
                ])
                keyboard.append([
                    InlineKeyboardButton("🧪 Тест OCR", callback_data="admin_test_ocr")
                ])
                keyboard.append([
                    InlineKeyboardButton("👤 Режим пользователя", callback_data="admin_user_mode")
                ])
                keyboard.append([InlineKeyboardButton("🆘 Помощь", callback_data="help_menu")])
                
                await query.message.reply_text(
                    welcome_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
        
        if data == "admin_back_to_admin":
            # Return to admin mode - send new message directly
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            session = ensure_session_cached(context, session_store, user_id, update_id)
            session['admin_user_mode'] = False
            await query.answer("Возврат в админ-панель")
            user = update.effective_user
            categories = get_categories_from_registry()
            total_models = len(KIE_MODELS)
            
            welcome_text = (
                f'👑 <b>Панель администратора</b>\n\n'
                f'Привет, {user.mention_html()}! 👋\n\n'
                f'🚀 <b>Расширенное меню управления</b>\n\n'
                f'📊 <b>Статистика:</b>\n'
                f'✅ <b>{total_models} моделей</b> доступно\n'
                f'✅ <b>{len(categories)} категорий</b>\n\n'
                f'⚙️ <b>Административные функции доступны</b>'
            )
            
            keyboard = []
            
            # All models button first
            keyboard.append([
                InlineKeyboardButton("📋 Все модели", callback_data="all_models")
            ])
            
            keyboard.append([])
            for category in categories:
                models_in_category = get_models_by_category_from_registry(category)
                emoji = models_in_category[0]["emoji"] if models_in_category else "📦"
                keyboard.append([InlineKeyboardButton(
                    f"{emoji} {category} ({len(models_in_category)})",
                    callback_data=f"category:{category}"
                )])
            
            keyboard.append([
                InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")
            ])
            keyboard.append([
                InlineKeyboardButton("🔍 Поиск", callback_data="admin_search"),
                InlineKeyboardButton("📝 Добавить", callback_data="admin_add")
            ])
            keyboard.append([
                InlineKeyboardButton("🧪 Тест OCR", callback_data="admin_test_ocr")
            ])
            keyboard.append([InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")])
            
            await query.message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        if data == "back_to_menu":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            await ensure_main_menu(update, context, source="back", prefer_edit=True)
            return ConversationHandler.END
        
    
        if data == "generate_again":
            # Generate again - restore model and show model info, then ask for new prompt
            await query.answer()  # Acknowledge the callback
            
            logger.info(f"Generate again requested by user {user_id}")
            
            if user_id not in saved_generations:
                logger.warning(f"No saved generation data for user {user_id}")
                await query.edit_message_text(
                    "❌ <b>Данные для повторной генерации не найдены</b>\n\n"
                    "Начните новую генерацию через меню.",
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            saved_data = saved_generations[user_id]
            logger.info(f"Restoring generation data for user {user_id}, model: {saved_data.get('model_id')}")
            
            # Restore session with model info, but clear params to start fresh
            session = ensure_session_cached(context, session_store, user_id, update_id)
            
            model_id = saved_data['model_id']
            model_info = saved_data['model_info']
            
            # Restore model info but clear params - user will enter new prompt
            session.update({
                'model_id': model_id,
                'model_info': model_info,
                'properties': saved_data['properties'].copy(),
                'required': saved_data['required'].copy(),
                'params': {}  # Clear params - start fresh
            })
            
            # Get user balance and calculate available generations (same as select_model)
            user_balance = await get_user_balance_async(user_id)
            is_admin = get_is_admin(user_id)
            
            # Calculate price for default parameters (minimum price)
            default_params = {}
            if model_id == "nano-banana-pro":
                default_params = {"resolution": "1K"}  # Cheapest option
            elif model_id == "seedream/4.5-text-to-image" or model_id == "seedream/4.5-edit":
                default_params = {"quality": "basic"}  # Basic quality (same price, but for consistency)
            
            min_price = get_from_price_value(model_id)
            price_text = format_price_rub(min_price, is_admin) if min_price is not None else "💰 <b>от — ₽</b>"
            
            # Calculate how many generations available
            if is_admin:
                available_count = "Безлимит"
            elif min_price and user_balance >= min_price:
                available_count = int(user_balance / min_price)
            else:
                available_count = 0
            
            # Show model info with price and available generations (improved format)
            model_name = model_info.get('name', model_id)
            model_emoji = model_info.get('emoji', '🤖')
            model_desc = model_info.get('description', '')
            
            # Получаем категорию модели для контекста
            model_category = model_info.get('category', '')
            gen_type = model_info.get('generation_type', '')

            model_info_text = (
                f"{model_emoji} <b>{model_name}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            
            if model_category:
                model_info_text += f"📁 <b>Категория:</b> {model_category}\n"
            if gen_type:
                gen_type_display = gen_type.replace('_', ' ').replace('-', ' ').title()
                model_info_text += f"🎯 <b>Тип:</b> {gen_type_display}\n"
            
            if model_category or gen_type:
                model_info_text += "\n"
            
            if model_desc:
                model_info_text += f"ℹ️ <b>Описание:</b>\n{model_desc}\n\n"
            
            model_info_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            model_info_text += f"💰 <b>Стоимость генерации:</b> {price_text}\n"
            
            if is_admin:
                model_info_text += t('msg_unlimited_available', lang=user_lang) + "\n\n"
            else:
                if available_count > 0:
                    model_info_text += t('msg_available_generations', lang=user_lang, 
                                        count=available_count, 
                                        balance=format_price_rub(user_balance, is_admin)) + "\n\n"
                else:
                    # Not enough balance - show warning
                    model_info_text += t('msg_insufficient_funds', lang=user_lang,
                                        balance=format_price_rub(user_balance, is_admin),
                                        required=price_text)
                    
                    keyboard = [
                        [InlineKeyboardButton(t('btn_top_up_balance', lang=user_lang), callback_data="topup_balance")],
                        [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
                    ]
                    
                    await query.edit_message_text(
                        model_info_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return ConversationHandler.END
            
            # Check balance before starting generation
            if not is_admin and user_balance < min_price:
                user_lang = get_user_language(user_id)
                keyboard = [
                    [InlineKeyboardButton(t('btn_top_up_balance', lang=user_lang), callback_data="topup_balance")],
                    [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
                ]
                
                needed = min_price - user_balance
                needed_str = format_rub_amount(needed)
                remaining_free = await get_user_free_generations_remaining(user_id)
                
                if user_lang == 'ru':
                    insufficient_msg = (
                        f"❌ <b>Недостаточно средств для генерации</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💳 <b>Ваш баланс:</b> {format_price_rub(user_balance, is_admin)}\n"
                        f"💵 <b>Требуется минимум:</b> {price_text}\n"
                        f"❌ <b>Не хватает:</b> {needed_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>Что делать:</b>\n"
                        f"• Пополните баланс через кнопку ниже\n"
                    )
                    
                    if remaining_free > 0:
                        insufficient_msg += f"• Используйте бесплатные генерации бесплатных моделей ({remaining_free} доступно)\n"
                    
                    insufficient_msg += (
                        f"• Пригласите друга и получите бонусы\n\n"
                        f"🔄 После пополнения попробуйте генерацию снова."
                    )
                else:
                    insufficient_msg = (
                        f"❌ <b>Insufficient Funds for Generation</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💳 <b>Your balance:</b> {format_price_rub(user_balance, is_admin)}\n"
                        f"💵 <b>Minimum required:</b> {price_text}\n"
                        f"❌ <b>Need:</b> {needed_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>What to do:</b>\n"
                        f"• Top up balance via button below\n"
                    )
                    
                    if remaining_free > 0:
                        insufficient_msg += f"• Use free models generations ({remaining_free} available)\n"
                    
                    insufficient_msg += (
                        f"• Invite a friend and get bonuses\n\n"
                        f"🔄 After topping up, try generation again."
                    )
                
                await query.edit_message_text(
                    _append_free_counter_text(insufficient_msg, free_counter_line),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            # Get input parameters from model info
            input_params = model_info.get('input_params', {})
            from app.kie_catalog import get_model
            model_spec = get_model(model_id) if model_id else None
            forced_media_required: List[str] = []
            if model_spec:
                input_params, required_params, forced_media_required = _apply_media_required_overrides(
                    model_spec,
                    input_params,
                )
            else:
                required_params = [p for p, info in input_params.items() if info.get('required', False)]
            
            if not input_params:
                # If no params defined, ask for simple text input
                await query.edit_message_text(
                    f"{model_info_text}"
                    f"Введите текст для генерации:",
                    parse_mode='HTML'
                )
                session['params'] = {}
                session['waiting_for'] = 'text'
                return INPUTTING_PARAMS
            
            # Store session data
            prefill_params = session.pop("prefill_params", {}) if isinstance(session, dict) else {}
            session['params'] = dict(prefill_params or {})
            session['properties'] = input_params
            session['required'] = required_params
            session['required_forced_media'] = forced_media_required
            session['skipped_params'] = set()
            session['current_param'] = None
            # NOTE: model_id and model_info are already stored above at lines 8449-8450
            
            primary_input = _determine_primary_input(model_info, input_params)
            logger.info(
                "🔥🔥🔥 SELECT_MODEL CHECK: model_id=%s primary_input=%s input_params_keys=%s user_id=%s",
                model_id,
                primary_input,
                list(input_params.keys()),
                user_id,
            )

            if primary_input and primary_input["type"] == "image":
                logger.debug("🔥🔥🔥 SELECT_MODEL: Model requires image first! user_id=%s", user_id)
                image_param_name = primary_input["param"]
                user_lang = get_user_language(user_id)
                keyboard = [
                    [
                        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                    ],
                    [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                    [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                ]
                if user_lang == 'en':
                    step_text = "📷 <b>Step 1: Upload image</b>\n\n"
                    if model_id == "recraft/remove-background":
                        step_text += "Send a photo to remove the background.\n\n"
                    elif model_id == "recraft/crisp-upscale":
                        step_text += "Send a photo to enhance quality.\n\n"
                    elif model_id == "ideogram/v3-reframe":
                        step_text += "Send a photo to reframe and change aspect ratio.\n\n"
                    elif model_id == "topaz/image-upscale":
                        step_text += "Send a photo to upscale and enhance resolution.\n\n"
                    else:
                        step_text += "Send a photo to use as reference or for transformation.\n\n"
                    if 'prompt' in input_params:
                        step_text += "💡 <i>After uploading the image, you can enter a prompt</i>"
                else:
                    step_text = (
                        "📷 <b>Шаг 1: Загрузите изображение</b>\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "Отправьте изображение в сообщении.\n"
                        "Поддерживаются форматы: PNG, JPG, JPEG, WEBP\n"
                        "Максимальный размер: 10 MB"
                    )
                    if 'prompt' in input_params:
                        step_text += "\n\n✅ <b>После загрузки:</b> вы сможете ввести промпт"

                free_counter_line = await _resolve_free_counter_line(
                    user_id,
                    user_lang,
                    correlation_id,
                    action_path=f"param_prompt:{image_param_name}",
                    sku_id=session.get("sku_id"),
                )
                step_text = _append_free_counter_text(step_text, free_counter_line)
                await query.edit_message_text(
                    f"{model_info_text}\n\n{step_text}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                session['current_param'] = image_param_name
                session['waiting_for'] = image_param_name
                if image_param_name not in session:
                    session[image_param_name] = []
                await query.answer()
                logger.info(
                    "🔥🔥🔥 SELECT_MODEL: Image input setup complete! model_id=%s user_id=%s waiting_for=%s",
                    model_id,
                    user_id,
                    image_param_name,
                )
                elapsed = time.time() - start_time
                logger.debug("🔥🔥🔥 SELECT_MODEL: Total time=%0.3fs user_id=%s", elapsed, user_id)
                return INPUTTING_PARAMS

            if primary_input and primary_input["type"] == "audio":
                logger.debug("🔥🔥🔥 SELECT_MODEL: Model requires audio first! user_id=%s", user_id)
                audio_param_name = primary_input["param"]
                user_lang = get_user_language(user_id)
                keyboard = [
                    [
                        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                    ],
                    [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                    [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                ]
                if user_lang == 'en':
                    audio_text = (
                        f"{model_info_text}\n\n"
                        f"🎤 <b>Step 1: Upload audio</b>\n\n"
                        f"Send an audio file (MP3, WAV, OGG, M4A, FLAC, AAC, WMA, MPEG).\n"
                        f"Maximum size: 200 MB"
                    )
                else:
                    audio_text = (
                        f"{model_info_text}\n\n"
                        f"🎤 <b>Шаг 1: Загрузите аудио</b>\n\n"
                        f"Отправьте аудио-файл (MP3, WAV, OGG, M4A, FLAC, AAC, WMA, MPEG).\n"
                        f"Максимальный размер: 200 MB"
                    )
                price_line = _build_current_price_line(
                    session,
                    user_lang=user_lang,
                    model_id=model_id,
                    mode_index=_resolve_mode_index(model_id, session.get("params", {}), user_id),
                    gen_type=session.get("gen_type"),
                    params=session.get("params", {}),
                    correlation_id=correlation_id,
                    update_id=update_id,
                    action_path=f"param_prompt:{audio_param_name}",
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    is_admin=get_is_admin(user_id),
                )
                audio_text += f"\n\n{price_line}"
                free_counter_line = await _resolve_free_counter_line(
                    user_id,
                    user_lang,
                    correlation_id,
                    action_path=f"param_prompt:{audio_param_name}",
                    sku_id=session.get("sku_id"),
                )
                audio_text = _append_free_counter_text(audio_text, free_counter_line)
                await query.edit_message_text(
                    audio_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                session['current_param'] = audio_param_name
                session['waiting_for'] = audio_param_name
                await query.answer()
                return INPUTTING_PARAMS
            
            # Special case: sora-2-pro-image-to-video starts with image_urls first
            if model_id == "sora-2-pro-image-to-video" and 'image_urls' in input_params and input_params['image_urls'].get('required', False):
                # Start with image_urls first for sora-2-pro-image-to-video
                has_image_input = True
                image_param_name = 'image_urls'
                keyboard = [
                    [
                        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                    ],
                    [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                    [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                ]
                image_text = (
                    f"{model_info_text}\n\n"
                    f"📷 <b>Шаг 1: Загрузите изображение</b>\n\n"
                    f"Отправьте фото, которое будет использовано как первый кадр видео.\n\n"
                    f"💡 <i>После загрузки изображения вы сможете ввести промпт</i>"
                )
                price_line = _build_current_price_line(
                    session,
                    user_lang=user_lang,
                    model_id=model_id,
                    mode_index=_resolve_mode_index(model_id, session.get("params", {}), user_id),
                    gen_type=session.get("gen_type"),
                    params=session.get("params", {}),
                    correlation_id=correlation_id,
                    update_id=update_id,
                    action_path=f"param_prompt:{image_param_name}",
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    is_admin=get_is_admin(user_id),
                )
                image_text += f"\n\n{price_line}"
                free_counter_line = await _resolve_free_counter_line(
                    user_id,
                    user_lang,
                    correlation_id,
                    action_path=f"param_prompt:{image_param_name}",
                    sku_id=session.get("sku_id"),
                )
                image_text = _append_free_counter_text(image_text, free_counter_line)
                await query.edit_message_text(
                    image_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                session['current_param'] = 'image_urls'
                session['waiting_for'] = 'image_urls'
                if 'image_urls' not in session:
                    session['image_urls'] = []  # Initialize as array
                await query.answer()
                return INPUTTING_PARAMS
            
            # Start with prompt parameter first (default behavior)
            if 'prompt' in input_params:
                # Check if model supports image input (image_input or image_urls)
                # BUT: z-image does NOT support image input (text-to-image only)
                # AND: text-to-video models do NOT require image input (text-to-video only)
                is_text_to_video = "text-to-video" in model_id.lower()
                has_image_input = (model_id != "z-image" and 
                                 not is_text_to_video and
                                 ('image_input' in input_params or 'image_urls' in input_params))
                
                prompt_text = (
                    f"{model_info_text}"
                )
                
                # Determine if this is a video or audio model
                is_video = is_video_model(model_id)
                is_audio = is_audio_model(model_id)
                
                if has_image_input:
                    ref_hint = "реф-картинку" if session.get("image_ref_prompt") else "изображение"
                    if is_video:
                        prompt_text += (
                            f"📝 <b>Шаг 1: Введите промпт</b>\n\n"
                            f"Опишите видео, которое хотите сгенерировать.\n\n"
                            f"💡 <i>После ввода промпта вы сможете добавить {ref_hint} (опционально)</i>"
                        )
                    else:
                        prompt_text += (
                            f"📝 <b>Шаг 1: Введите промпт</b>\n\n"
                            f"Опишите изображение, которое хотите сгенерировать.\n\n"
                            f"💡 <i>После ввода промпта вы сможете добавить {ref_hint} (опционально)</i>"
                        )
                else:
                    if is_video:
                        prompt_text += (
                            f"📝 <b>Шаг 1: Введите промпт</b>\n\n"
                            f"Опишите видео, которое хотите сгенерировать:"
                        )
                    elif is_audio:
                        prompt_text += (
                            f"📝 <b>Шаг 1: Введите промпт</b>\n\n"
                            f"Опишите контент для обработки:"
                        )
                    else:
                        prompt_text += (
                            f"📝 <b>Шаг 1: Введите промпт</b>\n\n"
                            f"Опишите изображение, которое хотите сгенерировать:"
                        )
                price_line = _build_current_price_line(
                    session,
                    user_lang=user_lang,
                    model_id=model_id,
                    mode_index=_resolve_mode_index(model_id, session.get("params", {}), user_id),
                    gen_type=session.get("gen_type"),
                    params=session.get("params", {}),
                    correlation_id=correlation_id,
                    update_id=update_id,
                    action_path="param_prompt:prompt",
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    is_admin=get_is_admin(user_id),
                )
                prompt_text += f"\n\n{price_line}"
                
                # Add keyboard with "Главное меню" and "Отмена" buttons
                free_counter_line = await _resolve_free_counter_line(
                    user_id,
                    user_lang,
                    correlation_id,
                    action_path="param_prompt:prompt",
                    sku_id=session.get("sku_id"),
                )
                prompt_text = _append_free_counter_text(prompt_text, free_counter_line)
                keyboard = [
                    [
                        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                    ],
                    [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                    [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                ]
                
                await query.edit_message_text(
                    prompt_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                session['current_param'] = 'prompt'
                session['waiting_for'] = 'prompt'
                session['has_image_input'] = has_image_input
            else:
                # If no prompt, start with first required parameter
                await start_next_parameter(update, context, user_id)
            
            return INPUTTING_PARAMS
        
        if data.startswith("set_language:"):
            # Handle language selection
            parts = data.split(":", 1)
            if len(parts) < 2:
                user_lang = get_user_language(query.from_user.id)
                await query.answer(t('error_invalid_format', lang=user_lang), show_alert=True)
                return ConversationHandler.END
            lang = parts[1]
            if lang in ['ru', 'en']:
                set_user_language(user_id, lang)
                await query.answer(t('language_set', lang))
                # Show main menu after language selection
                await start(update, context)
                return ConversationHandler.END
            else:
                await query.answer("Неверный язык / Invalid language")
            return ConversationHandler.END
        
        if data == "cancel":
            user_lang = get_user_language(user_id)
            await query.answer(t('btn_cancel', lang=user_lang).replace('❌ ', ''))
            session_store.clear(user_id)
            try:
                await query.edit_message_text(
                    t('msg_operation_cancelled', lang=user_lang),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Error editing message on cancel: {e}")
                try:
                    await query.message.reply_text(
                        t('msg_operation_cancelled', lang=user_lang),
                        parse_mode="HTML",
                    )
                except:
                    pass
            await ensure_main_menu(update, context, source="cancel", prefer_edit=False)
            return ConversationHandler.END
        
        if data.startswith("retry_generate:"):
            # Retry generation with same parameters
            await query.answer("Повторяю попытку...")
            
            session = get_session_cached(context, session_store, user_id, update_id, default=None)
            if not session:
                await query.edit_message_text("❌ Сессия не найдена. Начните заново.")
                return ConversationHandler.END
            
            # Show confirmation again with same parameters
            model_name = session.get('model_info', {}).get('name', 'Unknown')
            params = session.get('params', {})
            params_text = "\n".join([f"  • {k}: {str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in params.items()])
            
            user_lang = get_user_language(user_id)
            keyboard = [
                [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                [
                    InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                    InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                ],
                [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
            ]
            
            await query.edit_message_text(
                f"🔄 <b>Повторная попытка:</b>\n\n"
                f"Модель: <b>{model_name}</b>\n"
                f"Параметры:\n{params_text}\n\n"
                f"Продолжить генерацию?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return CONFIRMING_GENERATION

        if data.startswith("retry_delivery:"):
            task_id = data.split(":", 1)[1] if ":" in data else ""
            await query.answer("Повторяю доставку...")

            async with pending_deliveries_lock:
                payload = pending_deliveries.get((user_id, task_id))

            if not payload:
                await query.edit_message_text(
                    "❌ Не нашёл результат для повторной доставки. Попробуйте заново через меню.",
                    parse_mode="HTML",
                )
                return ConversationHandler.END

            from app.generations.telegram_sender import deliver_result

            delivered = False
            try:
                delivered = bool(
                    await deliver_result(
                        context.bot,
                        payload["chat_id"],
                        payload["media_type"],
                        payload["urls"],
                        payload.get("text"),
                        model_id=payload.get("model_id"),
                        gen_type=payload.get("gen_type"),
                        correlation_id=payload.get("correlation_id"),
                        params=payload.get("params"),
                        model_label=payload.get("model_label"),
                    )
                )
            except Exception as exc:
                log_structured_event(
                    correlation_id=payload.get("correlation_id"),
                    user_id=user_id,
                    chat_id=payload.get("chat_id"),
                    action="DELIVERY_FAIL",
                    action_path="retry_delivery",
                    model_id=payload.get("model_id"),
                    stage="TG_DELIVER",
                    outcome="failed",
                    error_code="TG_DELIVER_EXCEPTION",
                    fix_hint=str(exc),
                    param={"task_id": task_id},
                )

            if delivered:
                async with pending_deliveries_lock:
                    pending_deliveries.pop((user_id, task_id), None)
                dry_run = is_dry_run() or not allow_real_generation()
                if not dry_run:
                    await _commit_post_delivery_charge(
                        session=payload.get("session", {}),
                        user_id=user_id,
                        chat_id=payload.get("chat_id"),
                        task_id=payload.get("task_id"),
                        sku_id=payload.get("sku_id", ""),
                        price=float(payload.get("price", 0)),
                        is_free=bool(payload.get("is_free")),
                        is_admin_user=bool(payload.get("is_admin_user")),
                        correlation_id=payload.get("correlation_id"),
                        model_id=payload.get("model_id"),
                    )
                await query.edit_message_text(
                    "✅ <b>Доставка завершена</b>\n\nРезультат успешно отправлен.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]]
                    ),
                    parse_mode="HTML",
                )
                return ConversationHandler.END

            retry_keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔁 Повторить доставку", callback_data=f"retry_delivery:{task_id}")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
                ]
            )
            await query.edit_message_text(
                "⚠️ <b>Доставка снова не удалась</b>\n\n"
                "Попробуйте ещё раз чуть позже или используйте главное меню.",
                reply_markup=retry_keyboard,
                parse_mode="HTML",
            )
            return ConversationHandler.END
        
        # Handle category selection (can be called from main menu)
        if data.startswith("gen_type:"):
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            reset_session_context(
                user_id,
                reason="gen_type",
                clear_gen_type=False,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            
            # User selected a generation type
            parts = data.split(":", 1)
            if len(parts) < 2:
                try:
                    await query.answer("Ошибка: неверный формат запроса", show_alert=True)
                except:
                    pass
                try:
                    await query.edit_message_text("❌ Ошибка: неверный формат запроса.")
                except:
                    try:
                        await query.message.reply_text("❌ Ошибка: неверный формат запроса.")
                    except:
                        pass
                return ConversationHandler.END
            gen_type = parts[1]
            session = ensure_session_cached(context, session_store, user_id, update_id)
            session["active_gen_type"] = gen_type
            session["gen_type"] = gen_type
            set_session_context(
                user_id,
                to_context=UI_CONTEXT_MODEL_MENU,
                reason="gen_type",
                active_gen_type=gen_type,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=before_get_info", user_id, gen_type)
            gen_info = get_generation_type_info(gen_type)
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=before_get_models", user_id, gen_type)
            models = get_visible_models_by_generation_type(gen_type)
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=got_models count=%s", user_id, gen_type, len(models) if models else 0)
            
            if not models:
                user_lang = get_user_language(user_id)
                error_text = t('msg_gen_type_no_models', lang=user_lang)
                try:
                    await query.edit_message_text(
                        error_text,
                        parse_mode='HTML'
                    )
                except:
                    try:
                        await query.message.reply_text(
                            error_text,
                            parse_mode='HTML'
                        )
                    except:
                        pass
                return ConversationHandler.END
            
            # Get admin status for price calculations
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=before_get_admin", user_id, gen_type)
            is_admin = get_is_admin(user_id)
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=after_get_admin is_admin=%s", user_id, gen_type, is_admin)
            
            # Show generation type info and models with marketing text
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=before_get_free_remaining", user_id, gen_type)
            remaining_free = await get_user_free_generations_remaining(user_id)
            logger.info("GEN_TYPE_HANDLER user_id=%s gen_type=%s step=got_free_remaining remaining=%s", user_id, gen_type, remaining_free)
            user_lang = get_user_language(user_id)
            free_counter_line = ""
            try:
                free_counter_line = await get_free_counter_line(
                    user_id,
                    user_lang=user_lang,
                    correlation_id=correlation_id,
                    action_path="gen_type_menu",
                )
            except Exception as exc:
                logger.warning("Failed to resolve free counter line: %s", exc)
            
            # Get translated name and description
            gen_type_key = f'gen_type_{gen_type.replace("-", "_")}'
            gen_type_name = t(gen_type_key, lang=user_lang, default=gen_info.get('name', gen_type))
            gen_desc_key = f'gen_type_desc_{gen_type.replace("-", "_")}'
            gen_type_description = t(gen_desc_key, lang=user_lang, default=gen_info.get('description', ''))
            
            gen_type_text = (
                f"{t('msg_gen_type_title', lang=user_lang, name=gen_type_name)}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{t('msg_gen_type_description', lang=user_lang, description=gen_type_description)}\n\n"
            )
            
            if remaining_free > 0 and gen_type == "text-to-image":
                gen_type_text += (
                    f"{t('msg_gen_type_free', lang=user_lang, remaining=remaining_free)}\n"
                    f"💡 {t('btn_invite_friend', lang=user_lang, bonus=REFERRAL_BONUS_GENERATIONS)}\n\n"
                )
            
            gen_type_text += (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{t('msg_gen_type_models_available', lang=user_lang, count=len(models))}\n\n"
                f"{t('msg_gen_type_select_model', lang=user_lang)}"
            )
            gen_type_text = _append_free_counter_text(gen_type_text, free_counter_line)
            
            # Create keyboard with models (2 per row for compact display)
            keyboard = []
            
            if gen_type == "text-to-image":
                user_lang = get_user_language(user_id)
                if user_lang == 'ru':
                    button_text = f"🆓 Бесплатные модели ({remaining_free}/{FREE_GENERATIONS_PER_DAY})"
                else:
                    button_text = f"🆓 Free tools ({remaining_free}/{FREE_GENERATIONS_PER_DAY})"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data="free_tools")
                ])
                
                # Add referral button
                if user_lang == 'ru':
                    keyboard.append([
                        InlineKeyboardButton(f"🎁 Пригласи друга → получи +{REFERRAL_BONUS_GENERATIONS} бесплатных!", callback_data="referral_info")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton(f"🎁 Invite friend → get +{REFERRAL_BONUS_GENERATIONS} free!", callback_data="referral_info")
                    ])
                
                keyboard.append([])  # Empty row
            
            # Show models in compact format with prices (2 per row)
            model_rows = []
            for i, model in enumerate(models):
                model_name = model.get('name', model.get('id', 'Unknown'))
                model_emoji = model.get('emoji', '🤖')
                model_id = model.get('id')

                # Get price for the model (show price in gen_type menus)
                from app.pricing.price_ssot import get_min_price
                min_price = get_min_price(model_id)
                
                if min_price is not None:
                    # Format price with RUB symbol
                    price_formatted = format_rub_amount(float(min_price))
                    button_text = f"{model_emoji} {model_name} • {price_formatted}"
                else:
                    button_text = f"{model_emoji} {model_name}"
                
                if len(button_text.encode("utf-8")) > 60:
                    # Truncate name to fit price
                    max_name_length = 25 if min_price else 40
                    truncated = model_name[:max_name_length].rstrip()
                    if min_price is not None:
                        button_text = f"{model_emoji} {truncated}... • {price_formatted}"
                    else:
                        button_text = f"{model_emoji} {truncated}..."
                
                # Ensure callback_data is not too long (Telegram limit: 64 bytes)
                callback_data = f"select_model:{model_id}"
                if len(callback_data.encode('utf-8')) > 64:
                    logger.error(f"Callback data too long for model {model_id}: {len(callback_data.encode('utf-8'))} bytes")
                    # Use shorter model_id if possible
                    callback_data = f"sel:{model_id[:50]}"
                
                if i % 2 == 0:
                    # First button in row
                    model_rows.append([InlineKeyboardButton(
                        button_text,
                        callback_data=callback_data
                    )])
                else:
                    # Second button in row - add to last row
                    if model_rows:
                        model_rows[-1].append(InlineKeyboardButton(
                            button_text,
                            callback_data=callback_data
                        ))
                    else:
                        model_rows.append([InlineKeyboardButton(
                            button_text,
                            callback_data=callback_data
                        )])
            
            keyboard.extend(model_rows)
            keyboard.append([InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")])
            
            try:
                await query.edit_message_text(
                    gen_type_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except BadRequest as exc:
                if "Message is not modified" in str(exc):
                    await query.answer()
                    return SELECTING_MODEL
                logger.error(f"Error editing message in gen_type: {exc}", exc_info=True)
                try:
                    await query.message.reply_text(
                        gen_type_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as e2:
                    logger.error(f"Error sending new message in gen_type: {e2}", exc_info=True)
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
            
            # IMPORTANT: Return SELECTING_MODEL state so that select_model: buttons work
            # If we return END, the buttons won't be clickable
            return SELECTING_MODEL
        
        if data.startswith("category:"):
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            parts = data.split(":", 1)
            if len(parts) < 2:
                try:
                    await query.answer("Ошибка: неверный формат запроса", show_alert=True)
                except:
                    pass
                try:
                    await query.edit_message_text("❌ Ошибка: неверный формат запроса.")
                except:
                    try:
                        await query.message.reply_text("❌ Ошибка: неверный формат запроса.")
                    except:
                        pass
                return ConversationHandler.END
            category = parts[1]
            models = get_models_by_category_from_registry(category)
            
            if not models:
                try:
                    await query.edit_message_text(f"❌ В категории {category} нет моделей.")
                except:
                    try:
                        await query.message.reply_text(f"❌ В категории {category} нет моделей.")
                    except:
                        pass
                return ConversationHandler.END
            
            keyboard = []
            for model in models:
                model_name = model.get('name', model.get('id', 'Unknown'))
                model_emoji = model.get('emoji', '🤖')
                model_id = model.get('id')
                button_text = f"{model_emoji} {model_name}"
                if len(button_text.encode("utf-8")) > 60:
                    truncated = model_name[:40].rstrip()
                    button_text = f"{model_emoji} {truncated}..."
                
                # Ensure callback_data is not too long (Telegram limit: 64 bytes)
                callback_data = f"select_model:{model_id}"
                if len(callback_data.encode('utf-8')) > 64:
                    logger.error(f"Callback data too long for model {model_id}: {len(callback_data.encode('utf-8'))} bytes")
                    callback_data = f"sel:{model_id[:50]}"
                
                keyboard.append([InlineKeyboardButton(
                    button_text,
                    callback_data=callback_data
                )])
            user_lang = get_user_language(query.from_user.id)
            keyboard.append([InlineKeyboardButton(t('btn_back_to_categories', lang=user_lang), callback_data="show_models")])
            keyboard.append([InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")])
            
            # Premium formatted header
            category_emoji = {
                "Видео": "🎬",
                "Изображения": "🖼️",
                "Редактирование": "✏️"
            }.get(category, "📁")
            
            models_text = (
                f"✨ <b>ПРЕМИУМ КАТАЛОГ</b> ✨\n\n"
                f"{category_emoji} <b>Категория: {category}</b>\n"
                f"📦 <b>Доступно моделей:</b> {len(models)}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💡 <i>Выберите модель из списка ниже</i>\n"
                f"<i>Подробная информация отобразится при выборе</i>"
            )
            
            await query.edit_message_text(
                models_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return SELECTING_MODEL
        
        if data == "free_tools":
            # Answer callback immediately
            try:
                await query.answer()
            except Exception as e:
                logger.error(f"Error answering callback for free_tools: {e}")
                pass
            reset_session_context(
                user_id,
                reason="free_tools",
                clear_gen_type=True,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            set_session_context(
                user_id,
                to_context=UI_CONTEXT_FREE_TOOLS_MENU,
                reason="free_tools",
                clear_gen_type=True,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            logger.info(f"User {user_id} clicked 'free_tools' button")
            
            # Get free tools from pricing SSOT (fixed order)
            free_sku_ids = get_free_tools_model_ids()
            from app.pricing.ssot_catalog import (
                get_sku_by_id,
                get_sku_param_summary,
                encode_sku_callback,
            )
            models_map = {model.get('id'): model for model in get_models_sync()}
            free_skus = [get_sku_by_id(sku_id) for sku_id in free_sku_ids]
            free_skus = [sku for sku in free_skus if sku and sku.model_id in models_map]

            if not free_skus:
                user_lang = get_user_language(user_id)
                keyboard = [[InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]]
                if user_lang == 'ru':
                    await query.edit_message_text(
                        "ℹ️ <b>Нет доступных бесплатных SKU</b>\n\n"
                        "В прайс-SSOT пока нет бесплатных вариантов.\n\n"
                        "Пока можно выбрать модель из каталога.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                else:
                    await query.edit_message_text(
                        "ℹ️ <b>No free SKUs available</b>\n\n"
                        "Pricing SSOT does not include free variants yet.\n\n"
                        "You can pick a model from the catalog.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                return ConversationHandler.END
            
            user_lang = get_user_language(user_id)
            free_counter_line = ""
            try:
                free_counter_line = await get_free_counter_line(
                    user_id,
                    user_lang=user_lang,
                    correlation_id=correlation_id,
                    action_path="free_tools_menu",
                    sku_id=free_sku_ids[0] if free_sku_ids else None,
                )
            except Exception as exc:
                logger.warning("Failed to resolve free counter line: %s", exc)
            if free_counter_line:
                if user_lang == "en":
                    free_counter_line = f"{free_counter_line}\n🔄 Limit refreshes once per day."
                else:
                    free_counter_line = f"{free_counter_line}\n🔄 Лимит обновляется раз в день."
            if user_lang == 'ru':
                free_tools_text = (
                    f"🆓 <b>БЕСПЛАТНЫЕ ИНСТРУМЕНТЫ</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 <b>Все инструменты в этом разделе полностью бесплатны!</b>\n\n"
                    f"🤖 <b>Доступные инструменты ({len(free_skus)}):</b>\n\n"
                    f"💡 <b>Выберите инструмент ниже</b>"
                )
            else:
                free_tools_text = (
                    f"🆓 <b>FREE TOOLS</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 <b>All tools in this section are completely free!</b>\n\n"
                    f"🤖 <b>Available tools ({len(free_skus)}):</b>\n\n"
                    f"💡 <b>Select a tool below</b>"
                )
            free_tools_text = _append_free_counter_text(free_tools_text, free_counter_line)
            
            # Create keyboard with free models (2 per row)
            keyboard = []
            model_rows = []
            for i, sku in enumerate(free_skus):
                model = models_map.get(sku.model_id, {})
                model_name = model.get('name', sku.model_id)
                model_emoji = model.get('emoji', '🆓')
                option_summary = get_sku_param_summary(sku)
                
                # Compact button text
                max_name_length = 25
                button_text = f"{model_emoji} {model_name} ({option_summary})"
                if len(button_text) > max_name_length:
                    button_text = f"{model_emoji} {model_name[:max_name_length-4]}..."
                
                # Ensure callback_data is not too long
                callback_data = encode_sku_callback(sku.sku_id)
                
                if i % 2 == 0:
                    # First button in row
                    model_rows.append([InlineKeyboardButton(
                        button_text,
                        callback_data=callback_data
                    )])
                else:
                    # Second button in row
                    if model_rows:
                        model_rows[-1].append(InlineKeyboardButton(
                            button_text,
                            callback_data=callback_data
                        ))
                    else:
                        model_rows.append([InlineKeyboardButton(
                            button_text,
                            callback_data=callback_data
                        )])
            
            keyboard.extend(model_rows)
            keyboard.append([InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")])
            
            try:
                await query.edit_message_text(
                    free_tools_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message in free_tools: {e}", exc_info=True)
                try:
                    await query.message.reply_text(
                        free_tools_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as e2:
                    logger.error(f"Error sending new message in free_tools: {e2}", exc_info=True)
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
            
            # Return SELECTING_MODEL state so that select_model: buttons work
            return SELECTING_MODEL
        
        if data == "show_models" or data == "all_models":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except Exception as e:
                logger.error(f"Error answering callback for show_models/all_models: {e}")
                pass
            
            logger.info(f"User {user_id} clicked 'show_models' or 'all_models' button (data: {data})")
            reset_session_context(
                user_id,
                reason="show_models",
                clear_gen_type=True,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            set_session_context(
                user_id,
                to_context=UI_CONTEXT_GEN_TYPE_MENU,
                reason="show_models",
                clear_gen_type=True,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            
            # Show generation types instead of all models with marketing text
            generation_types = get_generation_types()
            visible_models_by_type = {
                gen_type: len(get_visible_models_by_generation_type(gen_type))
                for gen_type in generation_types
            }
            visible_generation_types = [
                gen_type for gen_type, count in visible_models_by_type.items() if count > 0
            ]
            remaining_free = await get_user_free_generations_remaining(user_id)
            user_lang = get_user_language(user_id)
            free_counter_line = ""
            try:
                free_counter_line = await get_free_counter_line(
                    user_id,
                    user_lang=user_lang,
                    correlation_id=correlation_id,
                    action_path="models_menu",
                )
            except Exception as exc:
                logger.warning("Failed to resolve free counter line: %s", exc)
            
            models_text = (
                f"🤖 <b>ВЫБЕРИТЕ НЕЙРОСЕТЬ</b> 🤖\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💡 <b>КАК ЭТО РАБОТАЕТ:</b>\n"
                f"1️⃣ Выберите тип генерации (текст→фото, фото→видео и т.д.)\n"
                f"2️⃣ Выберите нейросеть из списка\n"
                f"3️⃣ Создавайте контент! 🚀\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            
            if remaining_free > 0:
                models_text += (
                    f"🎁 <b>БЕСПЛАТНО:</b> {remaining_free} генераций бесплатных моделей доступно!\n"
                    f"💡 Пригласи друга → получи +{REFERRAL_BONUS_GENERATIONS} генераций\n\n"
                )
            
            visible_models_count = len(_get_visible_model_ids())
            models_text += (
                f"📦 <b>Доступно:</b> {len(visible_generation_types)} типов генерации\n"
                f"🤖 <b>Моделей:</b> {visible_models_count} топовых нейросетей"
            )
            models_text = _append_free_counter_text(models_text, free_counter_line)
            
            keyboard = []
            
            if user_lang == 'ru':
                button_text = f"🆓 Бесплатные модели ({remaining_free}/{FREE_GENERATIONS_PER_DAY})"
            else:
                button_text = f"🆓 Free tools ({remaining_free}/{FREE_GENERATIONS_PER_DAY})"
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data="free_tools")
            ])
            
            # Add referral button
            referral_link = get_user_referral_link(user_id)
            if user_lang == 'ru':
                keyboard.append([
                    InlineKeyboardButton(f"🎁 Пригласи друга → получи +{REFERRAL_BONUS_GENERATIONS} бесплатных!", callback_data="referral_info")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(f"🎁 Invite friend → get +{REFERRAL_BONUS_GENERATIONS} free!", callback_data="referral_info")
                ])
            
            keyboard.append([])  # Empty row
            
            # Generation types buttons (2 per row for compact display)
            # Find text-to-image type and add it after free generation button
            text_to_image_type = None
            gen_type_rows = []
            gen_type_index = 0  # Separate index for non-text-to-image types
            
            for gen_type in generation_types:
                gen_info = get_generation_type_info(gen_type)
                models_count = visible_models_by_type.get(gen_type, 0)
                
                # Skip if no models in this type
                if models_count == 0:
                    logger.warning(f"No models found for generation type: {gen_type}")
                    continue
                
                # Identify text-to-image type (will be added separately)
                if gen_type == 'text-to-image':
                    text_to_image_type = gen_type
                    continue
                
                # Get translated name for generation type
                gen_type_key = f'gen_type_{gen_type.replace("-", "_")}'
                gen_type_name = t(gen_type_key, lang=user_lang, default=gen_info.get('name', gen_type))
                button_text = f"{gen_type_name} ({models_count})"
                
                # Add buttons in pairs (2 per row)
                if gen_type_index % 2 == 0:
                    gen_type_rows.append([InlineKeyboardButton(
                        button_text,
                        callback_data=f"gen_type:{gen_type}"
                    )])
                else:
                    if gen_type_rows:
                        gen_type_rows[-1].append(InlineKeyboardButton(
                            button_text,
                            callback_data=f"gen_type:{gen_type}"
                        ))
                    else:
                        gen_type_rows.append([InlineKeyboardButton(
                            button_text,
                            callback_data=f"gen_type:{gen_type}"
                        )])
                
                gen_type_index += 1
            
            # Add text-to-image button after free generation (if it exists and has models)
            if text_to_image_type:
                gen_info = get_generation_type_info(text_to_image_type)
                models_count = visible_models_by_type.get(text_to_image_type, 0)
                if models_count > 0:
                    gen_type_key = f'gen_type_{text_to_image_type.replace("-", "_")}'
                    gen_type_name = t(gen_type_key, lang=user_lang, default=gen_info.get('name', text_to_image_type))
                    button_text = f"{gen_type_name} ({models_count})"
                    keyboard.append([
                        InlineKeyboardButton(button_text, callback_data=f"gen_type:{text_to_image_type}")
                    ])
                    keyboard.append([])  # Empty row for spacing
            
            # Add other generation types
            keyboard.extend(gen_type_rows)

            # Add free tools button (always visible, prominent)
            keyboard.append([])  # Empty row for spacing
            if user_lang == 'ru':
                keyboard.append([
                    InlineKeyboardButton("🆓 БЕСПЛАТНЫЕ ИНСТРУМЕНТЫ", callback_data="free_tools")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("🆓 FREE TOOLS", callback_data="free_tools")
                ])

            # Add "Other models" shortcut
            if user_lang == 'ru':
                keyboard.append([
                    InlineKeyboardButton("🧩 Другие модели", callback_data="other_models")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("🧩 Other models", callback_data="other_models")
                ])

            # Add button to show all models directly (without grouping by type)
            keyboard.append([])  # Empty row for spacing
            if user_lang == 'ru':
                keyboard.append([
                    InlineKeyboardButton(f"📋 Показать все {visible_models_count} моделей", callback_data="show_all_models_list")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(f"📋 Show all {visible_models_count} models", callback_data="show_all_models_list")
                ])
            
            user_lang = get_user_language(user_id)
            keyboard.append([
                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
            ])
            keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
            keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
            
            try:
                await query.edit_message_text(
                    models_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except BadRequest as exc:
                if "Message is not modified" in str(exc):
                    await query.answer()
                    return SELECTING_MODEL
                logger.error(f"Error editing message in show_models: {exc}", exc_info=True)
                try:
                    await query.message.reply_text(
                        models_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except:
                    pass
            return SELECTING_MODEL
        
        if data == "show_all_models_list":
            # Answer callback immediately
            try:
                await query.answer()
            except Exception as e:
                logger.error(f"Error answering callback for show_all_models_list: {e}")
                pass
            
            logger.info(f"User {user_id} clicked 'show_all_models_list' button")
            
            # Используем новый каталог
            try:
                from app.helpers.models_menu_handlers import handle_show_all_models_list
                user_lang = get_user_language(user_id)
                reset_session_context(
                    user_id,
                    reason="show_all_models_list",
                    clear_gen_type=True,
                    correlation_id=correlation_id,
                    update_id=update_id,
                    chat_id=query.message.chat_id if query.message else None,
                )
                set_session_context(
                    user_id,
                    to_context=UI_CONTEXT_MODEL_MENU,
                    reason="show_all_models_list",
                    clear_gen_type=True,
                    correlation_id=correlation_id,
                    update_id=update_id,
                    chat_id=query.message.chat_id if query.message else None,
                )
                await handle_show_all_models_list(
                    query,
                    user_id,
                    user_lang,
                    default_model_id="sora-watermark-remover",
                )
                return SELECTING_MODEL
            except Exception as e:
                logger.error(f"Error in handle_show_all_models_list: {e}", exc_info=True)
                user_lang = get_user_language(user_id)
                if user_lang == 'ru':
                    error_msg = "❌ Ошибка при загрузке моделей. Попробуйте позже."
                else:
                    error_msg = "❌ Error loading models. Please try later."
                await query.answer(error_msg, show_alert=True)
                return SELECTING_MODEL
            
            try:
                await query.edit_message_text(
                    models_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error showing all models: {e}", exc_info=True)
                await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
            
            return SELECTING_MODEL
        
        if data == "add_image":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            session = user_sessions.get(user_id, {})
            # Determine which parameter name to use (image_input or image_urls)
            model_info = session.get('model_info', {})
            input_params = model_info.get('input_params', {})
            if 'image_urls' in input_params:
                image_param_name = 'image_urls'
            else:
                image_param_name = 'image_input'
            session['waiting_for'] = image_param_name
            session['current_param'] = image_param_name
            if image_param_name not in session:
                session[image_param_name] = []  # Initialize as array
            free_counter_line = await _resolve_free_counter_line(
                user_id,
                user_lang,
                correlation_id,
                action_path=f"param_prompt:{image_param_name}",
                sku_id=session.get("sku_id"),
            )
            prompt_text = _append_free_counter_text(
                "📷 <b>Загрузите изображение</b>\n\n"
                "Отправьте фото, которое хотите использовать как референс или для трансформации.\n"
                "Можно загрузить до 8 изображений.",
                free_counter_line,
            )
            keyboard = [
                [
                    InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                    InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                ],
                [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
            ]
            await query.edit_message_text(
                prompt_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return INPUTTING_PARAMS
        
        if data == "image_done":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            if user_id not in user_sessions:
                await query.edit_message_text("❌ Сессия не найдена.")
                return ConversationHandler.END
            session = user_sessions[user_id]
            waiting_for = session.get('waiting_for', 'image_input')
            # Normalize: if waiting_for is 'image', use the actual parameter name from properties
            if waiting_for == 'image':
                properties = session.get('properties', {})
                if 'image_input' in properties:
                    image_param_name = 'image_input'
                elif 'image_urls' in properties:
                    image_param_name = 'image_urls'
                else:
                    image_param_name = 'image_input'  # Default fallback
            else:
                image_param_name = waiting_for
            
            if image_param_name in session and session[image_param_name]:
                if 'params' not in session:
                    session['params'] = {}
                session['params'][image_param_name] = session[image_param_name]
                await query.edit_message_text(
                    f"✅ Добавлено изображений: {len(session[image_param_name])}\n\n"
                    f"Продолжаю..."
                )
            session['waiting_for'] = None
            
            # Move to next parameter
            try:
                next_param_result = await start_next_parameter(update, context, user_id)
                if next_param_result:
                    return next_param_result
                else:
                    # All parameters collected
                    model_name = session.get('model_info', {}).get('name', 'Unknown')
                    params = session.get('params', {})
                    params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in params.items()])
                    
                    user_lang = get_user_language(user_id)
                    keyboard = [
                        [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                        [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                        [
                            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                        ],
                        [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                    ]
                    
                    # Calculate price for confirmation message
                    is_admin_user = get_is_admin(user_id)
                    price = calculate_price_rub(model_id, params, is_admin_user)
                    if price is None:
                        blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
                        await query.edit_message_text(blocked_text, parse_mode="HTML")
                        return ConversationHandler.END
                    sku_id = session.get("sku_id", "")
                    is_free = await is_free_generation_available(user_id, sku_id)
                    if price is None:
                        blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
                        await query.edit_message_text(blocked_text, parse_mode="HTML")
                        return ConversationHandler.END
                    if is_free:
                        price = 0.0
                    price_str = format_rub_amount(price)
                    
                    # Prepare price info
                    if is_free:
                        remaining = await get_user_free_generations_remaining(user_id)
                        price_info = f"🎁 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ!</b>\nОсталось бесплатных: {remaining}/{FREE_GENERATIONS_PER_DAY} в день"
                    else:
                        price_info = f"💰 <b>Стоимость:</b> {price_str}"

                    free_counter_line = ""
                    try:
                        free_counter_line = await get_free_counter_line(
                            user_id,
                            user_lang=user_lang,
                            correlation_id=correlation_id,
                            action_path="confirm_screen",
                            sku_id=sku_id,
                        )
                    except Exception as exc:
                        logger.warning("Failed to resolve free counter line: %s", exc)

                    free_counter_line = ""
                    try:
                        free_counter_line = await get_free_counter_line(
                            user_id,
                            user_lang=user_lang,
                            correlation_id=correlation_id,
                            action_path="confirm_screen",
                            sku_id=sku_id,
                        )
                    except Exception as exc:
                        logger.warning("Failed to resolve free counter line: %s", exc)

                    free_counter_line = ""
                    try:
                        free_counter_line = await get_free_counter_line(
                            user_id,
                            user_lang=user_lang,
                            correlation_id=correlation_id,
                            action_path="confirm_screen",
                            sku_id=sku_id,
                        )
                    except Exception as exc:
                        logger.warning("Failed to resolve free counter line: %s", exc)
                    
                    # Format improved confirmation message with price
                    if user_lang == 'ru':
                        confirm_msg = _append_free_counter_text(
                            (
                            f"📋 <b>Подтверждение генерации</b>\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🤖 <b>Модель:</b> {model_name}\n\n"
                            f"⚙️ <b>Параметры:</b>\n{params_text}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{price_info}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💡 <b>Что будет дальше:</b>\n"
                            f"• Генерация начнется после подтверждения\n"
                            f"• Результат придет автоматически\n"
                            f"• Обычно это занимает от 10 секунд до 2 минут\n\n"
                            f"🚀 <b>Готовы начать?</b>"
                            ),
                            free_counter_line,
                        )
                    else:
                        price_info_en = f"🎁 <b>FREE GENERATION!</b>\nRemaining free: {remaining}/{FREE_GENERATIONS_PER_DAY} per day" if is_free else f"💰 <b>Cost:</b> {price_str}"
                        confirm_msg = _append_free_counter_text(
                            (
                            f"📋 <b>Generation Confirmation</b>\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🤖 <b>Model:</b> {model_name}\n\n"
                            f"⚙️ <b>Parameters:</b>\n{params_text}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{price_info_en}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💡 <b>What's next:</b>\n"
                            f"• Generation will start after confirmation\n"
                            f"• Result will come automatically\n"
                            f"• Usually takes from 10 seconds to 2 minutes\n\n"
                            f"🚀 <b>Ready to start?</b>"
                            ),
                            free_counter_line,
                        )
                    
                    logger.info(f"✅ [UX IMPROVEMENT] Sending improved confirmation message to user {user_id}")
                    await query.edit_message_text(
                        confirm_msg,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return CONFIRMING_GENERATION
            except Exception as e:
                logger.error(f"Error after image done: {e}")
                await query.edit_message_text("❌ Ошибка при переходе к следующему параметру.")
                return INPUTTING_PARAMS
        
        if data == "add_audio":
            # User wants to add audio file
            await query.answer()
            if user_id not in user_sessions:
                await query.edit_message_text("❌ Ошибка: сессия не найдена. Начните заново.")
                return ConversationHandler.END
            
            session = user_sessions.get(user_id, {})
            if not session:
                user_lang = get_user_language(query.from_user.id)
                await query.edit_message_text(t('error_session_empty', lang=user_lang))
                return ConversationHandler.END
            model_info = session.get('model_info', {})
            input_params = model_info.get('input_params', {})
            
            audio_param_name = 'audio_url' if 'audio_url' in input_params else 'audio_input'
            user_lang = get_user_language(query.from_user.id)
            
            keyboard = [
                [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")],
                [InlineKeyboardButton(t('btn_skip', lang=user_lang), callback_data="skip_audio")]
            ]
            
            await query.edit_message_text(
                "🎤 <b>Загрузите аудио-файл</b>\n\n"
                "Отправьте аудио-файл для транскрибации.\n\n"
                "Поддерживаемые форматы: MP3, WAV, OGG, M4A, FLAC, AAC, WMA, MPEG\n"
                "Максимальный размер: 200 MB",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
            session['waiting_for'] = audio_param_name
            session['current_param'] = audio_param_name
            return INPUTTING_PARAMS
        
        if data == "skip_audio":
            # User wants to skip audio upload
            await query.answer("Аудио пропущено")
            if user_id not in user_sessions:
                await query.edit_message_text("❌ Ошибка: сессия не найдена. Начните заново.")
                return ConversationHandler.END
            
            session = user_sessions[user_id]
            session['waiting_for'] = None
            session['current_param'] = None
            
            # Move to next parameter
            try:
                next_param_result = await start_next_parameter(update, context, user_id)
                if next_param_result:
                    return next_param_result
                else:
                    # All parameters collected, show confirmation
                    model_name = session.get('model_info', {}).get('name', 'Unknown')
                    params = session.get('params', {})
                    params_text = "\n".join([f"  • {k}: {str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in params.items()])
                    
                    user_lang = get_user_language(user_id)
                    keyboard = [
                        [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                        [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                        [
                            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                        ],
                        [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                    ]
                    
                    # Calculate price for confirmation message
                    is_admin_user = get_is_admin(user_id)
                    sku_id = session.get("sku_id", "")
                    is_free = await is_free_generation_available(user_id, sku_id)
                    price = calculate_price_rub(model_id, params, is_admin_user)
                    if is_free:
                        price = 0.0
                    price_str = format_rub_amount(price)
                    
                    # Prepare price info
                    if is_free:
                        remaining = await get_user_free_generations_remaining(user_id)
                        price_info = f"🎁 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ!</b>\nОсталось бесплатных: {remaining}/{FREE_GENERATIONS_PER_DAY} в день"
                    else:
                        price_info = f"💰 <b>Стоимость:</b> {price_str}"
                    
                    # Format improved confirmation message with price
                    if user_lang == 'ru':
                        confirm_msg = _append_free_counter_text(
                            (
                            f"📋 <b>Подтверждение генерации</b>\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🤖 <b>Модель:</b> {model_name}\n\n"
                            f"⚙️ <b>Параметры:</b>\n{params_text}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{price_info}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💡 <b>Что будет дальше:</b>\n"
                            f"• Генерация начнется после подтверждения\n"
                            f"• Результат придет автоматически\n"
                            f"• Обычно это занимает от 10 секунд до 2 минут\n\n"
                            f"🚀 <b>Готовы начать?</b>"
                            ),
                            free_counter_line,
                        )
                    else:
                        price_info_en = f"🎁 <b>FREE GENERATION!</b>\nRemaining free: {remaining}/{FREE_GENERATIONS_PER_DAY} per day" if is_free else f"💰 <b>Cost:</b> {price_str}"
                        confirm_msg = _append_free_counter_text(
                            (
                            f"📋 <b>Generation Confirmation</b>\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🤖 <b>Model:</b> {model_name}\n\n"
                            f"⚙️ <b>Parameters:</b>\n{params_text}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"{price_info_en}\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"💡 <b>What's next:</b>\n"
                            f"• Generation will start after confirmation\n"
                            f"• Result will come automatically\n"
                            f"• Usually takes from 10 seconds to 2 minutes\n\n"
                            f"🚀 <b>Ready to start?</b>"
                            ),
                            free_counter_line,
                        )
                    
                    logger.info(f"✅ [UX IMPROVEMENT] Sending improved confirmation message to user {user_id}")
                    await query.edit_message_text(
                        confirm_msg,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return CONFIRMING_GENERATION
            except Exception as e:
                logger.error(f"Error after skipping audio: {e}", exc_info=True)
                await query.edit_message_text("❌ Ошибка при переходе к следующему параметру.")
            
            return INPUTTING_PARAMS
        
        if data == "skip_image":
            await query.answer("Изображение пропущено")
            # Move to next parameter
            try:
                next_param_result = await start_next_parameter(update, context, user_id)
                if next_param_result:
                    return next_param_result
                else:
                    # All parameters collected
                    if user_id not in user_sessions:
                        await query.edit_message_text("❌ Сессия не найдена.")
                        return ConversationHandler.END
                    session = user_sessions[user_id]
                    model_name = session.get('model_info', {}).get('name', 'Unknown')
                    params = session.get('params', {})
                    params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in params.items()])
                    
                    user_lang = get_user_language(user_id)
                    sku_id = session.get("sku_id")
                    free_counter_line = ""
                    try:
                        free_counter_line = await get_free_counter_line(
                            user_id,
                            user_lang=user_lang,
                            correlation_id=correlation_id,
                            action_path="confirm_screen",
                            sku_id=sku_id,
                        )
                    except Exception as exc:
                        logger.warning("Failed to resolve free counter line: %s", exc)
                    keyboard = [
                        [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                        [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                        [
                            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                        ],
                        [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                    ]
                
                await query.edit_message_text(
                    _append_free_counter_text(
                        (
                            f"📋 <b>Подтверждение:</b>\n\n"
                            f"Модель: <b>{model_name}</b>\n"
                            f"Параметры:\n{params_text}\n\n"
                            f"Продолжить генерацию?"
                        ),
                        free_counter_line,
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return CONFIRMING_GENERATION
            except Exception as e:
                logger.error(f"Error after skipping image: {e}")
                await query.edit_message_text("❌ Ошибка при переходе к следующему параметру.")
                return INPUTTING_PARAMS

        if data == "show_parameters":
            await query.answer()
            if user_id not in user_sessions:
                await query.edit_message_text("❌ Сессия не найдена.")
                return ConversationHandler.END

            session = user_sessions[user_id]
            properties = session.get('properties', {})
            params = session.get('params', {})
            param_order = session.get('param_order', list(properties.keys()))
            skipped_params = session.get('skipped_params', set())
            user_lang = get_user_language(user_id)
            keyboard = []

            for param_name in param_order:
                if param_name not in properties:
                    continue
                param_info = properties.get(param_name, {})
                default_value = param_info.get('default')
                if param_name in params:
                    value_text = str(params[param_name])
                elif param_name in skipped_params:
                    value_text = "по умолчанию" if user_lang == "ru" else "default"
                elif default_value is not None:
                    value_text = f"{default_value}"
                else:
                    value_text = "—"
                if len(value_text) > 30:
                    value_text = value_text[:30] + "…"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{param_name}: {value_text}",
                        callback_data=f"edit_param:{param_name}"
                    )
                ])

            back_label = "◀️ Назад" if user_lang == 'ru' else "◀️ Back"
            keyboard.append([InlineKeyboardButton(back_label, callback_data="back_to_confirmation")])
            keyboard.append([InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")])
            keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])

            text = (
                "⚙️ <b>Параметры модели</b>\n\n"
                "Нажмите на параметр, чтобы изменить его значение."
                if user_lang == 'ru'
                else "⚙️ <b>Model parameters</b>\n\nTap a parameter to change its value."
            )
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            logger.info(
                "🧭 PARAMS_MENU: action_path=show_parameters model_id=%s waiting_for=%s current_param=%s outcome=shown",
                session.get('model_id'),
                session.get('waiting_for'),
                session.get('current_param'),
            )
            return INPUTTING_PARAMS

        if data.startswith("edit_param:"):
            await query.answer()
            if user_id not in user_sessions:
                await query.edit_message_text("❌ Сессия не найдена.")
                return ConversationHandler.END
            session = user_sessions[user_id]
            param_name = data.split(":", 1)[1]
            session.setdefault('param_history', [])
            skipped_params = session.get("skipped_params", set())
            if param_name in skipped_params:
                skipped_params.discard(param_name)
            if 'params' in session:
                session['params'].pop(param_name, None)
            session['waiting_for'] = param_name
            session['current_param'] = param_name
            return await prompt_for_specific_param(update, context, user_id, param_name, source="edit_param")

        if data.startswith("confirm_param:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                await query.answer("Ошибка: неверный формат параметра", show_alert=True)
                return ConversationHandler.END
            if user_id not in user_sessions:
                await query.edit_message_text("❌ Сессия не найдена.")
                return ConversationHandler.END
            session = user_sessions[user_id]
            param_name = parts[1]
            pending = session.pop("pending_param", None)
            pending_params = session.pop("pending_params", None)
            session.pop("pending_price", None)
            if not pending or pending.get("name") != param_name or not isinstance(pending_params, dict):
                await query.edit_message_text("❌ Параметр не найден для подтверждения.")
                return ConversationHandler.END
            skip_param = pending.get("skip", False)
            session['params'] = pending_params
            skipped_params = session.setdefault("skipped_params", set())
            if skip_param:
                skipped_params.add(param_name)
            else:
                skipped_params.discard(param_name)
            _record_param_history(session, param_name)
            session['current_param'] = None
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
                update_id=update_id,
                action="PARAM_CONFIRM",
                action_path="button_callback.confirm_param",
                param={"param_name": param_name, "source": "callback"},
                outcome="confirmed",
            )
            model_id = session.get("model_id", "")
            mode_index = _resolve_mode_index(model_id, session.get("params", {}), user_id)
            _update_price_quote(
                session,
                model_id=model_id,
                mode_index=mode_index,
                gen_type=session.get("gen_type"),
                params=session.get("params", {}),
                correlation_id=correlation_id,
                update_id=update_id,
                action_path="button_callback.confirm_param",
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
                is_admin=get_is_admin(user_id),
            )

            required = session.get('required', [])
            params = session.get('params', {})
            missing = [p for p in required if p not in params]

            if missing:
                price_line = _build_current_price_line(
                    session,
                    user_lang=user_lang,
                    model_id=model_id,
                    mode_index=mode_index,
                    gen_type=session.get("gen_type"),
                    params=session.get("params", {}),
                    correlation_id=correlation_id,
                    update_id=update_id,
                    action_path="button_callback.confirm_param",
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    is_admin=get_is_admin(user_id),
                )
                await query.edit_message_text(f"✅ {param_name} сохранён.\n{price_line}")
                next_param_result = await start_next_parameter(update, context, user_id)
                if next_param_result:
                    return next_param_result
                return INPUTTING_PARAMS

            session['waiting_for'] = None
            if not model_id:
                logger.error(f"❌ model_id not found in session for user_id={user_id}")
                await query.edit_message_text("❌ Ошибка: модель не найдена в сессии.")
                return ConversationHandler.END
            return await send_confirmation_message(update, context, user_id, source="confirm_param_complete")

        if data == "back_to_confirmation":
            await query.answer()
            return await send_confirmation_message(update, context, user_id, source="back_to_confirmation")
        
        if data.startswith("set_param:"):
            # Handle parameter setting via button
            parts = data.split(":", 2)
            if len(parts) != 3:
                await query.answer("Ошибка: неверный формат параметра", show_alert=True)
                return ConversationHandler.END

            param_name = parts[1]
            param_value = parts[2]
            skip_param = False

            if user_id not in user_sessions:
                await query.edit_message_text("❌ Сессия не найдена.")
                return ConversationHandler.END

            session = user_sessions[user_id]
            properties = session.get('properties', {})
            param_info = properties.get(param_name, {})
            param_type = param_info.get('type', 'string')

            # 🔴 ВАЛИДАЦИЯ ENUM ЗНАЧЕНИЙ: Проверяем, что значение находится в списке допустимых
            enum_values = _normalize_enum_values(param_info)
            if enum_values and param_value not in enum_values and param_value not in {SKIP_PARAM_VALUE, "custom"}:
                # Недопустимое enum значение
                user_lang = get_user_language(user_id) if user_id else 'ru'
                error_text = (
                    f"❌ <b>Недопустимое значение</b>\n\n"
                    f"Допустимые значения: {', '.join(enum_values)}\n"
                    f"Введено: {param_value}"
                ) if user_lang == 'ru' else (
                    f"❌ <b>Invalid value</b>\n\n"
                    f"Allowed values: {', '.join(enum_values)}\n"
                    f"Entered: {param_value}"
                )
                await query.answer(error_text, show_alert=True)
                return ConversationHandler.END

            if param_value == SKIP_PARAM_VALUE:
                if param_info.get('required', False):
                    user_lang = get_user_language(user_id) if user_id else 'ru'
                    error_text = (
                        "❌ Этот параметр обязателен и не может быть пропущен."
                        if user_lang == 'ru'
                        else "❌ This parameter is required and cannot be skipped."
                    )
                    await query.answer(error_text, show_alert=True)
                    return INPUTTING_PARAMS
                user_lang = get_user_language(user_id) if user_id else 'ru'
                if 'params' in session and param_name in session['params']:
                    session['params'].pop(param_name, None)
                skipped_params = session.setdefault("skipped_params", set())
                skipped_params.add(param_name)
                session['current_param'] = None
                session['waiting_for'] = None
                _record_param_history(session, param_name)
                skip_param = True
                param_label = _humanize_param_name(param_name, user_lang)
                skip_text = (
                    f"✅ {param_label}: по умолчанию"
                    if user_lang == "ru"
                    else f"✅ {param_label}: default applied"
                )
                mode_index = _resolve_mode_index(session.get("model_id", ""), session.get("params", {}), user_id)
                price_line = _build_current_price_line(
                    session,
                    user_lang=user_lang,
                    model_id=session.get("model_id", ""),
                    mode_index=mode_index,
                    gen_type=session.get("gen_type"),
                    params=session.get("params", {}),
                    correlation_id=correlation_id,
                    update_id=update_id,
                    action_path="button_callback.set_param",
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    is_admin=get_is_admin(user_id),
                )
                await query.edit_message_text(f"{skip_text}\n{price_line}")
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    update_id=update_id,
                    action="PARAM_SKIPPED",
                    action_path="button_callback.set_param",
                    param={"param_name": param_name, "source": "callback"},
                    outcome="skipped",
                )
                try:
                    next_param_result = await start_next_parameter(update, context, user_id)
                    if next_param_result:
                        return next_param_result
                    return INPUTTING_PARAMS
                except Exception as e:
                    logger.error(f"Error starting next parameter after skip: {e}")
                    await query.edit_message_text("❌ Ошибка при переходе к следующему параметру.")
                    return INPUTTING_PARAMS

            if param_value == "custom" and param_name == "language_code":
                session['current_param'] = param_name
                session['waiting_for'] = param_name
                session['language_code_custom'] = True
                await query.edit_message_text(
                    "✏️ Введите код языка (например: en, ru, de, fr).",
                )
                return INPUTTING_PARAMS

            # Convert boolean string to actual boolean
            if param_type == 'boolean':
                if param_value.lower() == 'true':
                    param_value = True
                elif param_value.lower() == 'false':
                    param_value = False
                else:
                    # Use default if invalid
                    param_value = param_info.get('default', True)

            if 'params' not in session:
                session['params'] = {}
            candidate_params = dict(session.get("params", {}))
            display_value = param_value
            if skip_param:
                default_value = param_info.get("default")
                if default_value is not None:
                    candidate_params[param_name] = default_value
                    display_value = default_value
                else:
                    candidate_params.pop(param_name, None)
            else:
                candidate_params[param_name] = param_value

            from app.pricing.price_resolver import resolve_price_quote
            from app.config import get_settings
            model_id = session.get("model_id", "")
            mode_index = _resolve_mode_index(model_id, candidate_params, user_id)
            quote = resolve_price_quote(
                model_id=model_id,
                mode_index=mode_index,
                gen_type=session.get("gen_type"),
                selected_params=candidate_params,
                settings=get_settings(),
                is_admin=get_is_admin(user_id),
            )
            if quote is None:
                user_lang = get_user_language(user_id) if user_id else 'ru'
                blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
                await query.edit_message_text(blocked_text, parse_mode="HTML")
                return ConversationHandler.END

            session["pending_param"] = {
                "name": param_name,
                "value": param_value,
                "skip": skip_param,
            }
            session["pending_params"] = candidate_params
            session["pending_price"] = float(quote.price_rub)
            option_label = _humanize_param_name(param_name, user_lang)
            confirm_text = build_option_confirm_text(
                user_lang,
                option_label,
                str(display_value),
                float(quote.price_rub),
            )
            confirm_button = "✅ Подтвердить" if user_lang == "ru" else "✅ Confirm"
            back_button = "↩️ Назад" if user_lang == "ru" else "↩️ Back"
            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(confirm_button, callback_data=f"confirm_param:{param_name}:{param_value}")],
                    [InlineKeyboardButton(back_button, callback_data=f"edit_param:{param_name}")],
                ]
            )
            await query.edit_message_text(confirm_text, reply_markup=keyboard, parse_mode="HTML")
            return INPUTTING_PARAMS

            # Check if there are more parameters
            required = session.get('required', [])
            params = session.get('params', {})
            missing = [p for p in required if p not in params]

            if missing:
                mode_index = _resolve_mode_index(model_id, session.get("params", {}), user_id)
                price_line = _build_current_price_line(
                    session,
                    user_lang=user_lang,
                    model_id=model_id,
                    mode_index=mode_index,
                    gen_type=session.get("gen_type"),
                    params=session.get("params", {}),
                    correlation_id=correlation_id,
                    update_id=update_id,
                    action_path="button_callback.set_param",
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    is_admin=get_is_admin(user_id),
                )
                await query.edit_message_text(f"✅ {param_name} установлен: {param_value}\n{price_line}")
                # Move to next parameter
                try:
                    next_param_result = await start_next_parameter(update, context, user_id)
                    if next_param_result:
                        return next_param_result
                    return INPUTTING_PARAMS
                except Exception as e:
                    logger.error(f"Error starting next parameter: {e}")
                    await query.edit_message_text("❌ Ошибка при переходе к следующему параметру.")
                    return INPUTTING_PARAMS

            # All parameters collected
            session['waiting_for'] = None
            # Get model_id from session (CRITICAL: must be defined before use)
            model_id = session.get('model_id', '')
            if not model_id:
                logger.error(f"❌ model_id not found in session for user_id={user_id}")
                await query.edit_message_text("❌ Ошибка: модель не найдена в сессии.")
                return ConversationHandler.END
            return await send_confirmation_message(update, context, user_id, source="set_param_complete")
        
        # Handle back to previous step
        if data == "back_to_previous_step":
            await query.answer("◀️ Возвращаюсь назад...")
            user_lang = get_user_language(user_id)
            
            if user_id not in user_sessions:
                await query.edit_message_text(
                    t('error_try_start', lang=user_lang),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            session = user_sessions[user_id]
            try:
                history = session.setdefault('param_history', [])
                params = session.get('params', {})
                if not history:
                    logger.info(
                        "🧭 BACK: action_path=back_to_previous_step model_id=%s waiting_for=%s current_param=%s outcome=no_history",
                        session.get('model_id'),
                        session.get('waiting_for'),
                        session.get('current_param'),
                    )
                    log_structured_event(
                        correlation_id=ensure_correlation_id(update, context),
                        user_id=user_id,
                        chat_id=query.message.chat_id if query and query.message else None,
                        update_id=update.update_id,
                        action="BACK_TO_PREVIOUS_STEP",
                        action_path="back_to_previous_step",
                        model_id=session.get("model_id"),
                        stage="UI_ROUTER",
                        outcome="no_history",
                        error_code="UX_NO_HISTORY",
                        fix_hint="No previous steps in history; show menu options or continue current step.",
                        param={"waiting_for": session.get("waiting_for"), "current_param": session.get("current_param")},
                    )
                    no_history_text = (
                        "ℹ️ <b>Нечего возвращать</b>\n\n"
                        "Вы на первом шаге.\n"
                        "Код: <code>UX_NO_HISTORY</code>\n\n"
                        "Выберите действие ниже."
                        if user_lang == "ru"
                        else (
                            "ℹ️ <b>Nothing to return</b>\n\n"
                            "You are on the first step.\n"
                            "Code: <code>UX_NO_HISTORY</code>\n\n"
                            "Choose an action below."
                        )
                    )
                    keyboard = InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")],
                            [InlineKeyboardButton(t('btn_all_models_short', lang=user_lang), callback_data="show_models")],
                            [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")],
                        ]
                    )
                    await query.edit_message_text(
                        no_history_text,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    return INPUTTING_PARAMS

                previous_param = history.pop()
                if previous_param in params:
                    params.pop(previous_param, None)
                session['params'] = params
                session['waiting_for'] = previous_param
                session['current_param'] = previous_param
                logger.info(
                    "🧭 BACK: action_path=back_to_previous_step model_id=%s waiting_for=%s current_param=%s outcome=rewind",
                    session.get('model_id'),
                    session.get('waiting_for'),
                    session.get('current_param'),
                )
                next_param_result = await prompt_for_specific_param(
                    update,
                    context,
                    user_id,
                    previous_param,
                    source="back_to_previous_step",
                )
                if next_param_result:
                    return next_param_result
                return INPUTTING_PARAMS
            except Exception as e:
                logger.error(f"Error in back_to_previous_step: {e}", exc_info=True)
                # Fallback: return to model selection
                await query.edit_message_text(
                    t('error_try_start', lang=user_lang),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
        
        if data == "check_balance":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            reset_session_on_navigation(user_id, reason="check_balance")
            
            # Check user's personal balance (используем helpers для устранения дублирования)
            try:
                user_lang = get_user_language(user_id)
                balance_info = await get_balance_info(user_id, user_lang)
                balance_text = await format_balance_message(balance_info, user_lang)
                keyboard = get_balance_keyboard(balance_info, user_lang)
                
                try:
                    await query.edit_message_text(
                        balance_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error editing message in check_balance: {e}", exc_info=True)
                    try:
                        await query.message.reply_text(
                            balance_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error in check_balance: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка при проверке баланса", show_alert=True)
                except:
                    pass
            return ConversationHandler.END
        
        if data == "topup_balance":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            
            # Check if user is blocked
            if is_user_blocked(user_id):
                await query.edit_message_text(
                    "❌ <b>Ваш аккаунт заблокирован</b>\n\n"
                    "Обратитесь к администратору для разблокировки.",
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            # Get payment details to show immediately
            payment_details = get_payment_details()
            user_lang = get_user_language(user_id)
            
            # Show amount selection - focus on small amounts with marketing
            keyboard = [
                [
                    InlineKeyboardButton("💎 50 ₽", callback_data="topup_amount:50"),
                    InlineKeyboardButton("💎 100 ₽", callback_data="topup_amount:100"),
                    InlineKeyboardButton("💎 150 ₽", callback_data="topup_amount:150")
                ],
                [
                    InlineKeyboardButton(t('btn_custom_amount', lang=user_lang), callback_data="topup_custom")
                ],
                [InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")]
            ]
            
            current_balance = await get_user_balance_async(user_id)
            balance_str = format_rub_amount(current_balance)
            
            await query.edit_message_text(
                f'💳 <b>ПОПОЛНЕНИЕ БАЛАНСА</b> 💳\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'💰 <b>Твой текущий баланс:</b> {balance_str}\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'{payment_details}\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'💡 <b>Доступные модели:</b>\n'
                f'• От 4 ₽ за видео\n'
                f'• От 1 ₽ за изображение\n'
                f'• Редактирование от 1 ₽\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'🚀 <b>ВЫБЕРИ СУММУ:</b>\n'
                f'• Быстрый выбор: 50, 100, 150 ₽\n'
                f'• Или укажи свою сумму\n\n'
                f'📝 <b>Ограничения:</b>\n'
                f'Минимум: 50 ₽ | Максимум: 50000 ₽',
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return SELECTING_AMOUNT
        
        if data.startswith("topup_amount:"):
            # User selected a preset amount
            parts = data.split(":", 1)
            if len(parts) < 2:
                await query.answer("Ошибка: неверный формат суммы", show_alert=True)
                return ConversationHandler.END
            try:
                amount = float(parts[1])
            except (ValueError, TypeError):
                await query.answer("Ошибка: неверная сумма", show_alert=True)
                return ConversationHandler.END
            user_lang = get_user_language(user_id)
            
            # Calculate what user can generate
            examples_count = int(amount / 0.62)  # free tools price
            video_count = int(amount / 3.86)  # Basic video price
            
            # Show payment method selection
            amount_display = format_rub_amount(amount)
            if user_lang == 'ru':
                payment_text = (
                    f'💳 <b>ОПЛАТА {amount_display}</b> 💳\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💵 <b>Сумма к оплате:</b> {amount_display}\n\n'
                    f'🎯 <b>ЧТО ТЫ ПОЛУЧИШЬ:</b>\n'
                    f'• ~{examples_count} изображений (free tools)\n'
                    f'• ~{video_count} видео (базовая модель)\n'
                    f'• Или комбинацию разных моделей!\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💳 <b>ОПЛАТА ТОЛЬКО ПО СБП:</b>'
                )
            else:
                payment_text = (
                    f'💳 <b>PAYMENT {amount_display}</b> 💳\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💵 <b>Amount to pay:</b> {amount_display}\n\n'
                    f'🎯 <b>WHAT YOU WILL GET:</b>\n'
                    f'• ~{examples_count} images (free tools)\n'
                    f'• ~{video_count} videos (basic model)\n'
                    f'• Or a combination of different models!\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💳 <b>PAYMENT ONLY VIA SBP:</b>'
                )
            
            # Store amount in session
            user_sessions[user_id] = {
                'topup_amount': amount,
                'waiting_for': 'payment_method'
            }
            
            keyboard = [
                [InlineKeyboardButton("💳 СБП / SBP", callback_data=f"pay_sbp:{amount}")],
                [
                    InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                    InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                ],
                [
                    InlineKeyboardButton(t('btn_support', lang=user_lang), callback_data="support_contact"),
                    InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")
                ]
            ]
            
            await query.edit_message_text(
                payment_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return SELECTING_AMOUNT
        
        # Handle payment method selection
        if data.startswith("pay_stars:"):
            await query.answer("Сейчас доступна только оплата по СБП.", show_alert=True)
            return SELECTING_AMOUNT
        
        if data.startswith("pay_sbp:"):
            # User chose SBP payment
            parts = data.split(":", 1)
            if len(parts) < 2:
                await query.answer("Ошибка: неверный формат суммы", show_alert=True)
                return ConversationHandler.END
            try:
                amount = float(parts[1])
            except (ValueError, TypeError):
                await query.answer("Ошибка: неверная сумма", show_alert=True)
                return ConversationHandler.END
            user_lang = get_user_language(user_id)
            session = user_sessions.get(user_id, {})
            if session.get("waiting_for") != "payment_method" or session.get("topup_amount") is None:
                await query.answer("Сначала выберите сумму пополнения.", show_alert=True)
                return ConversationHandler.END

            amount = session.get("topup_amount", amount)
            user_sessions[user_id] = {
                'topup_amount': amount,
                'waiting_for': 'payment_screenshot',
                'payment_method': 'sbp'
            }
            
            payment_details = get_payment_details()
            keyboard = [
                [
                    InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                    InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                ],
                [
                    InlineKeyboardButton(t('btn_support', lang=user_lang), callback_data="support_contact"),
                    InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")
                ]
            ]

            sbp_text = build_manual_payment_instructions(
                amount=amount,
                user_lang=user_lang,
                payment_details=payment_details,
                method_label="СБП" if user_lang == "ru" else "SBP",
            )
            
            await query.edit_message_text(
                sbp_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return WAITING_PAYMENT_SCREENSHOT

        if data.startswith("pay_card:"):
            await query.answer("Сейчас доступна только оплата по СБП.", show_alert=True)
            return SELECTING_AMOUNT
        
        if data == "topup_custom":
            # User wants to enter custom amount
            await query.edit_message_text(
                f'💰 <b>ВВЕДИ СВОЮ СУММУ</b> 💰\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'📝 <b>Просто отправь число</b> (например: 250)\n\n'
                f'💡 <b>Доступные модели:</b>\n'
                f'• От 3.86 ₽ за видео\n'
                f'• От 0.62 ₽ за изображение\n'
                f'• Редактирование от 0.5 ₽\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'📋 <b>Ограничения:</b>\n'
                f'• Минимум: 50 ₽\n'
                f'• Максимум: 50000 ₽\n\n'
                f'💬 <b>Отправь сумму цифрами</b> (например: 250)',
                parse_mode='HTML'
            )
            user_sessions[user_id] = {
                'waiting_for': 'topup_amount_input'
            }
            return SELECTING_AMOUNT
        
        # Admin functions (only for admin)
        if get_is_admin(user_id):
            if data.startswith("admin_user_info:"):
                await query.answer()
                parts = data.split(":", 1)
                if len(parts) < 2:
                    await query.answer("Ошибка: неверный формат пользователя", show_alert=True)
                    return ConversationHandler.END
                try:
                    target_user_id = int(parts[1])
                except ValueError:
                    await query.answer("Ошибка: неверный user_id", show_alert=True)
                    return ConversationHandler.END
                text, keyboard = await build_admin_user_overview(target_user_id)
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')
                return ConversationHandler.END

            if data.startswith("admin_topup_user:"):
                await query.answer()
                parts = data.split(":", 1)
                if len(parts) < 2:
                    await query.answer("Ошибка: неверный формат пользователя", show_alert=True)
                    return ConversationHandler.END
                try:
                    target_user_id = int(parts[1])
                except ValueError:
                    await query.answer("Ошибка: неверный user_id", show_alert=True)
                    return ConversationHandler.END
                user_sessions[user_id] = {
                    "waiting_for": "admin_manual_topup_amount",
                    "admin_target_user_id": target_user_id,
                }
                await query.edit_message_text(
                    f"➕ <b>Начисление баланса</b>\n\n"
                    f"👤 Пользователь: <code>{target_user_id}</code>\n"
                    f"💬 Отправьте сумму для начисления (например: 150)\n\n"
                    f"Отмена: /cancel",
                    parse_mode='HTML'
                )
                return ConversationHandler.END

            if data == "admin_stats":
                await render_admin_panel(query, context, is_callback=True)
                return ConversationHandler.END
            
            # Handle payment screenshots viewing
            if data == "view_payment_screenshots":
                await query.answer()
                
                # Get all payments with screenshots
                payments = get_all_payments()
                payments_with_screenshots = [p for p in payments if p.get('screenshot_file_id')]
                
                if not payments_with_screenshots:
                    await query.edit_message_text(
                        "📸 <b>Скриншоты платежей</b>\n\n"
                        "Нет платежей со скриншотами.",
                        parse_mode='HTML'
                    )
                    return ConversationHandler.END
                
                # Show first payment screenshot
                first_payment = payments_with_screenshots[0]
                payment_index = 0
                
                # Store current index in context for navigation
                context.user_data['payment_screenshot_index'] = 0
                context.user_data['payment_screenshots_list'] = [p.get('id') for p in payments_with_screenshots]
                
                await show_payment_screenshot(query, first_payment, payment_index, len(payments_with_screenshots))
                return ConversationHandler.END
            
            # Handle navigation between payment screenshots
            if data.startswith("payment_screenshot_nav:"):
                await query.answer()
                
                parts = data.split(":", 1)
                if len(parts) < 2:
                    await query.answer("Ошибка навигации", show_alert=True)
                    return ConversationHandler.END
                
                direction = parts[1]  # "prev" or "next"
                current_index = context.user_data.get('payment_screenshot_index', 0)
                payment_ids = context.user_data.get('payment_screenshots_list', [])
                
                if not payment_ids:
                    await query.answer("Список платежей не найден", show_alert=True)
                    return ConversationHandler.END
                
                # Navigate
                if direction == "prev":
                    current_index = (current_index - 1) % len(payment_ids)
                elif direction == "next":
                    current_index = (current_index + 1) % len(payment_ids)
                else:
                    await query.answer("Неверное направление", show_alert=True)
                    return ConversationHandler.END
                
                context.user_data['payment_screenshot_index'] = current_index
                
                # Get payment by ID
                payment_id = payment_ids[current_index]
                payments = get_all_payments()
                payment = next((p for p in payments if p.get('id') == payment_id), None)
                
                if not payment:
                    await query.answer("Платеж не найден", show_alert=True)
                    return ConversationHandler.END
                
                await show_payment_screenshot(query, payment, current_index, len(payment_ids))
                return ConversationHandler.END
            
            # Handle back to payments list
            if data == "admin_payments_back":
                await query.answer()
                await show_admin_payments(query, context, is_callback=True)
                return ConversationHandler.END
        
        # Handle admin view all generations
        if data == "admin_view_generations":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору." if get_user_language(user_id) == 'ru' else "This function is available only to administrator.")
                return ConversationHandler.END
            
            await query.answer()
            user_lang = get_user_language(user_id)
            
            # Load all generations from all users
            history = load_json_file(GENERATIONS_HISTORY_FILE, {})
            
            if not history:
                if user_lang == 'ru':
                    message_text = (
                        "📚 <b>Просмотр генераций</b>\n\n"
                        "❌ В системе пока нет сохраненных генераций.\n\n"
                        "💡 Генерации пользователей будут отображаться здесь после их создания."
                    )
                else:
                    message_text = (
                        "📚 <b>View Generations</b>\n\n"
                        "❌ No saved generations in the system yet.\n\n"
                        "💡 User generations will appear here after they are created."
                    )
                
                keyboard = [
                    [InlineKeyboardButton(t('btn_back_to_admin', lang=user_lang), callback_data="admin_stats")]
                ]
                await query.edit_message_text(
                    message_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            # Collect all generations with user info
            all_generations = []
            for user_key, user_history in history.items():
                try:
                    user_id_int = int(user_key) if user_key.isdigit() else None
                    if user_id_int:
                        for gen in user_history:
                            gen_with_user = gen.copy()
                            gen_with_user['user_id'] = user_id_int
                            all_generations.append(gen_with_user)
                except (ValueError, TypeError):
                    continue
            
            # Sort by timestamp (newest first)
            all_generations.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            if not all_generations:
                if user_lang == 'ru':
                    message_text = (
                        "📚 <b>Просмотр генераций</b>\n\n"
                        "❌ Не найдено генераций для отображения."
                    )
                else:
                    message_text = (
                        "📚 <b>View Generations</b>\n\n"
                        "❌ No generations found to display."
                    )
                
                keyboard = [
                    [InlineKeyboardButton(t('btn_back_to_admin', lang=user_lang), callback_data="admin_stats")]
                ]
                await query.edit_message_text(
                    message_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            # Store in context for navigation
            context.user_data['admin_generations_list'] = all_generations
            context.user_data['admin_generation_index'] = 0
            
            # Show first generation
            await show_admin_generation(query, context, all_generations[0], 0, len(all_generations))
            return ConversationHandler.END
        
        # Handle admin generation navigation
        if data.startswith("admin_gen_nav:"):
            if not is_admin(user_id):
                await query.answer("Доступ запрещен", show_alert=True)
                return ConversationHandler.END
            
            await query.answer()
            parts = data.split(":", 1)
            if len(parts) < 2:
                return ConversationHandler.END
            
            direction = parts[1]  # "prev" or "next"
            all_generations = context.user_data.get('admin_generations_list', [])
            current_index = context.user_data.get('admin_generation_index', 0)
            
            if not all_generations:
                await query.answer("Список генераций не найден", show_alert=True)
                return ConversationHandler.END
            
            # Navigate
            if direction == "prev":
                current_index = (current_index - 1) % len(all_generations)
            elif direction == "next":
                current_index = (current_index + 1) % len(all_generations)
            else:
                return ConversationHandler.END
            
            context.user_data['admin_generation_index'] = current_index
            gen = all_generations[current_index]
            
            await show_admin_generation(query, context, gen, current_index, len(all_generations))
            return ConversationHandler.END
        
        # Handle admin view generation result
        if data.startswith("admin_gen_view:"):
            if not is_admin(user_id):
                await query.answer("Доступ запрещен", show_alert=True)
                return ConversationHandler.END
            
            await query.answer()
            parts = data.split(":", 1)
            if len(parts) < 2:
                return ConversationHandler.END
            
            try:
                gen_index = int(parts[1])
            except (ValueError, TypeError):
                return ConversationHandler.END
            
            all_generations = context.user_data.get('admin_generations_list', [])
            if gen_index < 0 or gen_index >= len(all_generations):
                await query.answer("Генерация не найдена", show_alert=True)
                return ConversationHandler.END
            
            gen = all_generations[gen_index]
            result_urls = gen.get('result_urls', [])
            
            if not result_urls:
                await query.answer("Результаты не найдены", show_alert=True)
                return ConversationHandler.END
            
            # Send media
            user_lang = get_user_language(user_id)
            session_http = await get_http_client()
            for i, url in enumerate(result_urls[:5]):
                try:
                    async with session_http.get(url) as resp:
                        if resp.status == 200:
                            media_data = await resp.read()
                            
                            is_last = (i == len(result_urls[:5]) - 1)
                            is_video = gen.get('model_id', '') in ['sora-2-text-to-video', 'sora-watermark-remover', 'kling-2.6/image-to-video', 'kling-2.6/text-to-video', 'kling/v2-5-turbo-text-to-video-pro', 'kling/v2-5-turbo-image-to-video-pro', 'wan/2-5-image-to-video', 'wan/2-5-text-to-video', 'wan/2-2-animate-move', 'wan/2-2-animate-replace', 'hailuo/02-text-to-video-pro', 'hailuo/02-image-to-video-pro', 'hailuo/02-text-to-video-standard', 'hailuo/02-image-to-video-standard']
                            
                            keyboard = []
                            if is_last:
                                keyboard = [
                                    [InlineKeyboardButton(t('btn_back_to_list', lang=user_lang), callback_data="admin_view_generations")],
                                    [InlineKeyboardButton(t('btn_back_to_admin', lang=user_lang), callback_data="admin_stats")]
                                ]
                            
                            if is_video:
                                video_file = io.BytesIO(media_data)
                                video_file.name = f"generated_video_{i+1}.mp4"
                                await context.bot.send_video(
                                    chat_id=query.message.chat_id,
                                    video=video_file,
                                    reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
                                )
                            else:
                                photo_file = io.BytesIO(media_data)
                                photo_file.name = f"generated_image_{i+1}.png"
                                await context.bot.send_photo(
                                    chat_id=query.message.chat_id,
                                    photo=photo_file,
                                    reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
                                )
                except Exception as e:
                    logger.error(f"Error sending admin generation result: {e}")
            
            await query.answer("✅ Результаты отправлены")
            return ConversationHandler.END
        
        if data == "admin_settings":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору." if get_user_language(user_id) == 'ru' else "This function is available only to administrator.")
                return ConversationHandler.END
            
            # Get user language
            user_lang = get_user_language(user_id)
            
            # Get support contact info
            support_telegram = os.getenv('SUPPORT_TELEGRAM', 'Не указано' if user_lang == 'ru' else 'Not specified')
            
            if user_lang == 'ru':
                settings_text = (
                    f'⚙️ <b>Настройки администратора:</b>\n\n'
                    f'🔧 <b>Доступные функции:</b>\n\n'
                    f'✅ Управление моделями\n'
                    f'✅ Просмотр статистики\n'
                    f'✅ Управление пользователями\n'
                    f'✅ Настройки API\n\n'
                    f'💡 <b>Команды:</b>\n'
                    f'/models - Управление моделями\n'
                    f'/balance - Проверка баланса\n'
                    f'/search - Поиск в базе знаний\n'
                    f'/add - Добавление знаний\n'
                    f'/admin - Пользователи и ручные пополнения\n'
                    f'/payments - Просмотр платежей\n'
                    f'/block_user - Заблокировать пользователя\n'
                    f'/unblock_user - Разблокировать пользователя\n'
                    f'/user_balance - Баланс пользователя\n'
                    f'/config_check - Проверка конфигурации\n\n'
                    f'💬 <b>Настройки поддержки:</b>\n\n'
                    f'💬 Telegram: {support_telegram if support_telegram != "Не указано" else "Не указано"}\n\n'
                    f'💡 Для изменения настроек поддержки отредактируйте файл .env'
                )
            else:
                settings_text = (
                    f'⚙️ <b>Administrator Settings:</b>\n\n'
                    f'🔧 <b>Available Functions:</b>\n\n'
                    f'✅ Model Management\n'
                    f'✅ View Statistics\n'
                    f'✅ User Management\n'
                    f'✅ API Settings\n\n'
                    f'💡 <b>Commands:</b>\n'
                    f'/models - Model Management\n'
                    f'/balance - Check Balance\n'
                    f'/search - Search Knowledge Base\n'
                    f'/add - Add Knowledge\n'
                    f'/admin - User overview and manual top-ups\n'
                    f'/payments - View Payments\n'
                    f'/block_user - Block User\n'
                    f'/unblock_user - Unblock User\n'
                    f'/user_balance - User Balance\n'
                    f'/config_check - Config Check\n\n'
                    f'💬 <b>Support Settings:</b>\n\n'
                    f'💬 Telegram: {support_telegram if support_telegram != "Not specified" else "Not specified"}\n\n'
                    f'💡 To change support settings, edit the .env file'
                )
            
            # Get current exchange rate
            current_rate = get_usd_to_rub_rate()
            
            if user_lang == 'ru':
                settings_text += f'\n💱 <b>Курс валюты:</b>\n'
                settings_text += f'1 USD = {current_rate:.2f} RUB\n\n'
                keyboard = [
                    [InlineKeyboardButton("💱 Установить курс валюты", callback_data="admin_set_currency_rate")],
                    [InlineKeyboardButton("🧩 Проверка конфигурации", callback_data="admin_config_check")],
                    [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("🎁 Промокоды", callback_data="admin_promocodes")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="admin_back_to_admin")]
                ]
            else:
                settings_text += f'\n💱 <b>Exchange Rate:</b>\n'
                settings_text += f'1 USD = {current_rate:.2f} RUB\n\n'
                keyboard = [
                    [InlineKeyboardButton("💱 Set Exchange Rate", callback_data="admin_set_currency_rate")],
                    [InlineKeyboardButton("🧩 Config Check", callback_data="admin_config_check")],
                    [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("🎁 Promocodes", callback_data="admin_promocodes")],
                    [InlineKeyboardButton("◀️ Back", callback_data="admin_back_to_admin")]
                ]
            
            await query.edit_message_text(
                settings_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END

        if data == "admin_config_check":
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END

            from app.config_env import build_config_self_check_report

            report = build_config_self_check_report()
            user_lang = get_user_language(user_id)
            back_label = "◀️ Назад" if user_lang == "ru" else "◀️ Back"
            keyboard = [[InlineKeyboardButton(back_label, callback_data="admin_settings")]]
            await query.edit_message_text(
                report,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
            return ConversationHandler.END
        
        if data == "admin_promocodes":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            # Show promocodes menu
            promocodes = load_promocodes()
            active_promo = get_active_promocode()
            
            promocodes_text = "🎁 <b>Управление промокодами</b>\n\n"
            
            if active_promo:
                promo_code = active_promo.get('code', 'N/A')
                promo_value = active_promo.get('value', 0)
                promo_expires = active_promo.get('expires', 'N/A')
                promo_used = active_promo.get('used_count', 0)
                
                promocodes_text += (
                    f"✅ <b>Активный промокод:</b>\n"
                    f"🔑 <b>Код:</b> <code>{promo_code}</code>\n"
                    f"💰 <b>Значение:</b> {promo_value} ₽\n"
                    f"📅 <b>Действителен до:</b> {promo_expires}\n"
                    f"👥 <b>Использовано раз:</b> {promo_used}\n\n"
                )
            else:
                promocodes_text += "❌ <b>Нет активного промокода</b>\n\n"
            
            # Show all promocodes
            if promocodes:
                promocodes_text += f"📋 <b>Все промокоды ({len(promocodes)}):</b>\n\n"
                for i, promo in enumerate(promocodes, 1):
                    promo_code = promo.get('code', 'N/A')
                    promo_value = promo.get('value', 0)
                    promo_expires = promo.get('expires', 'N/A')
                    promo_used = promo.get('used_count', 0)
                    is_active = promo.get('active', False)
                    
                    status = "✅ Активен" if is_active else "❌ Неактивен"
                    
                    promocodes_text += (
                        f"{i}. <b>{status}</b>\n"
                        f"   🔑 <code>{promo_code}</code>\n"
                        f"   💰 {promo_value} ₽ | 👥 {promo_used} использований\n"
                        f"   📅 До: {promo_expires}\n\n"
                    )
            else:
                promocodes_text += "📋 <b>Нет созданных промокодов</b>\n\n"
            
            promocodes_text += "💡 <b>Доступные действия:</b>\n"
            promocodes_text += "• Просмотр всех промокодов\n"
            promocodes_text += "• Информация об активном промокоде\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="admin_promocodes")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_settings")]
            ]
            
            await query.edit_message_text(
                promocodes_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        if data == "admin_broadcast":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            # Show broadcast menu
            broadcasts = get_broadcasts()
            total_users = len(get_all_users())
            
            broadcast_text = "📢 <b>Рассылка сообщений</b>\n\n"
            broadcast_text += f"👥 <b>Всего пользователей:</b> {total_users}\n\n"
            
            if broadcasts:
                broadcast_text += f"📋 <b>История рассылок ({len(broadcasts)}):</b>\n\n"
                # Show last 5 broadcasts
                sorted_broadcasts = sorted(
                    broadcasts.items(),
                    key=lambda x: x[1].get('created_at', 0),
                    reverse=True
                )[:5]
                
                for broadcast_id, broadcast in sorted_broadcasts:
                    created_at = broadcast.get('created_at', 0)
                    sent = broadcast.get('sent', 0)
                    delivered = broadcast.get('delivered', 0)
                    failed = broadcast.get('failed', 0)
                    message_preview = broadcast.get('message', '')[:30] + '...' if len(broadcast.get('message', '')) > 30 else broadcast.get('message', '')
                    
                    from datetime import datetime
                    if created_at:
                        date_str = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M')
                    else:
                        date_str = 'N/A'
                    
                    broadcast_text += (
                        f"📨 <b>#{broadcast_id}</b> ({date_str})\n"
                        f"   📝 {message_preview}\n"
                        f"   ✅ Отправлено: {sent} | 📬 Доставлено: {delivered} | ❌ Ошибок: {failed}\n\n"
                    )
            else:
                broadcast_text += "📋 <b>Нет истории рассылок</b>\n\n"
            
            broadcast_text += "💡 <b>Создать новую рассылку:</b>\n"
            broadcast_text += "Нажмите кнопку ниже и отправьте сообщение для рассылки."
            
            keyboard = [
                [InlineKeyboardButton("📢 Создать рассылку", callback_data="admin_create_broadcast")],
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_broadcast_stats")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_settings")]
            ]
            
            await query.edit_message_text(
                broadcast_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        if data == "admin_create_broadcast":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            # Start broadcast creation
            await query.edit_message_text(
                "📢 <b>Создание рассылки</b>\n\n"
                "Отправьте сообщение, которое хотите разослать всем пользователям.\n\n"
                "💡 <b>Поддерживается:</b>\n"
                "• Текст\n"
                "• HTML форматирование\n"
                "• Изображения\n\n"
                "Или нажмите /cancel для отмены.",
                parse_mode='HTML'
            )
            user_sessions[user_id] = {
                'waiting_for': 'broadcast_message'
            }
            return WAITING_BROADCAST_MESSAGE
        
        if data == "admin_set_currency_rate":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            # Get current exchange rate
            current_rate = get_usd_to_rub_rate()
            
            currency_text = (
                f'💱 <b>Установка курса валюты</b>\n\n'
                f'📊 <b>Текущий курс:</b>\n'
                f'1 USD = {current_rate:.2f} RUB\n\n'
                f'💡 <b>Инструкция:</b>\n'
                f'Отправьте новое значение курса валюты.\n'
                f'Например: <code>100</code> (означает 1 USD = 100 RUB)\n\n'
                f'⚠️ <b>Важно:</b>\n'
                f'• Курс должен быть положительным числом\n'
                f'• Используйте точку для десятичных значений (например: 95.5)\n'
                f'• После установки все цены будут пересчитаны автоматически\n\n'
                f'Для отмены нажмите /cancel'
            )
            
            await query.edit_message_text(
                currency_text,
                parse_mode='HTML'
            )
            
            # Set session to wait for currency rate
            user_sessions[user_id] = {
                'waiting_for': 'currency_rate'
            }
            return WAITING_CURRENCY_RATE
        
        if data == "admin_broadcast_stats":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            # Show detailed broadcast statistics
            broadcasts = get_broadcasts()
            total_users = len(get_all_users())
            
            if not broadcasts:
                await query.edit_message_text(
                    "📊 <b>Статистика рассылок</b>\n\n"
                    "❌ Нет истории рассылок",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Назад", callback_data="admin_broadcast")]
                    ]),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            # Calculate totals
            total_sent = sum(b.get('sent', 0) for b in broadcasts.values())
            total_delivered = sum(b.get('delivered', 0) for b in broadcasts.values())
            total_failed = sum(b.get('failed', 0) for b in broadcasts.values())
            
            stats_text = (
                f"📊 <b>Статистика рассылок</b>\n\n"
                f"👥 <b>Всего пользователей:</b> {total_users}\n"
                f"📨 <b>Всего рассылок:</b> {len(broadcasts)}\n\n"
                f"📈 <b>Общая статистика:</b>\n"
                f"✅ Отправлено: {total_sent}\n"
                f"📬 Доставлено: {total_delivered}\n"
                f"❌ Ошибок: {total_failed}\n\n"
            )
            
            if total_sent > 0:
                success_rate = (total_delivered / total_sent) * 100
                stats_text += f"📊 <b>Успешность доставки:</b> {success_rate:.1f}%\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="admin_broadcast_stats")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_broadcast")]
            ]
            
            await query.edit_message_text(
                stats_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        if data == "admin_search":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            await query.edit_message_text(
                '🔍 <b>Поиск в базе знаний</b>\n\n'
                'Используйте команду:\n'
                '<code>/search [запрос]</code>\n\n'
                'Пример:\n'
                '<code>/search нейросети</code>',
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        if data == "admin_add":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            await query.edit_message_text(
                '📝 <b>Добавление знаний</b>\n\n'
                'Используйте команду:\n'
                '<code>/add [заголовок] | [содержание]</code>\n\n'
                'Пример:\n'
                '<code>/add AI | Искусственный интеллект - это...</code>',
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        if data == "admin_test_ocr":
            # Check admin access
            if not is_admin(user_id):
                await query.answer("Эта функция доступна только администратору.")
                return ConversationHandler.END
            
            if not OCR_AVAILABLE or not PIL_AVAILABLE:
                await query.edit_message_text(
                    '❌ <b>OCR недоступен</b>\n\n'
                    'Tesseract OCR не установлен или библиотеки не найдены.\n\n'
                    'Установите:\n'
                    '1. pip install Pillow pytesseract\n'
                    '2. Tesseract OCR (см. TESSERACT_INSTALL.txt)',
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            await query.edit_message_text(
                '🧪 <b>Тест OCR</b>\n\n'
                'Отправьте изображение со скриншотом платежа.\n\n'
                'Система проверит:\n'
                '✅ Распознавание текста\n'
                '✅ Поиск сумм\n'
                '✅ Работа Tesseract OCR\n\n'
                'Или нажмите /cancel для отмены.',
                parse_mode='HTML'
            )
            user_sessions[user_id] = {
                'waiting_for': 'admin_test_ocr'
            }
            return ADMIN_TEST_OCR
        
        if data == "tutorial_start":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            try:
                # Interactive tutorial for new users
                tutorial_text = (
                    '🎓 <b>ИНТЕРАКТИВНЫЙ ТУТОРИАЛ</b>\n\n'
                    '━━━━━━━━━━━━━━━━━━━━\n\n'
                    '👋 Добро пожаловать! Давайте разберемся, как пользоваться ботом.\n\n'
                    '📚 <b>Что вы узнаете:</b>\n'
                    '• Что такое AI-генерация\n'
                    '• Как выбрать модель\n'
                    '• Как создать контент\n'
                    '• Как пополнить баланс\n\n'
                    '💡 <b>Это займет 2 минуты!</b>'
                )
                
                keyboard = [
                    [InlineKeyboardButton("▶️ Начать туториал", callback_data="tutorial_step1")],
                    [InlineKeyboardButton("⏭️ Пропустить", callback_data="back_to_menu")]
                ]
                
                try:
                    await query.edit_message_text(
                        tutorial_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message in tutorial_start: {edit_error}, sending new message")
                    try:
                        await query.message.reply_text(
                            tutorial_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message in tutorial_start: {send_error}", exc_info=True)
                        await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in tutorial_start: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
        
        if data == "tutorial_step1":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            try:
                tutorial_text = (
                    '📖 <b>ШАГ 1: Что такое AI-генерация?</b>\n\n'
                    '━━━━━━━━━━━━━━━━━━━━\n\n'
                    '🤖 <b>Искусственный интеллект</b> может создавать:\n\n'
                    '🎨 <b>Изображения</b>\n'
                    'Опишите картинку словами, и AI создаст её!\n'
                    'Пример: "Кот в космосе, пиксель-арт"\n\n'
                    '🎬 <b>Видео</b>\n'
                    'Создавайте короткие видео из текста\n'
                    'Пример: "Летящий дракон над городом"\n\n'
                    '🖼️ <b>Улучшение качества</b>\n'
                    'Увеличивайте разрешение фото в 4-8 раз\n\n'
                    '💡 <b>Все это без VPN!</b> Прямой доступ к лучшим AI-моделям.'
                )
                
                keyboard = [
                    [InlineKeyboardButton("▶️ Далее", callback_data="tutorial_step2")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="tutorial_start")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                
                try:
                    await query.edit_message_text(
                        tutorial_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message in tutorial_step1: {edit_error}, sending new message")
                    try:
                        await query.message.reply_text(
                            tutorial_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message in tutorial_step1: {send_error}", exc_info=True)
                        await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in tutorial_step1: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
        
        if data == "tutorial_step2":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            try:
                categories = get_categories_from_registry()
                total_models = len(get_models_sync())
                tutorial_text = (
                    f'📖 <b>ШАГ 2: Как выбрать модель?</b>\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'🎯 <b>У нас {total_models} моделей в {len(categories)} категориях:</b>\n\n'
                    f'🖼️ <b>Изображения</b>\n'
                    f'• free tools - бесплатные модели (5 раз в день)\n'
                    f'• Nano Banana Pro - качество 2K/4K\n'
                    f'• Imagen 4 Ultra - новейшая от Google\n\n'
                    f'🎬 <b>Видео</b>\n'
                    f'• Sora 2 - реалистичные видео\n'
                    f'• Grok Imagine - мультимодальная модель\n\n'
                    f'💡 <b>Совет:</b> Начните с бесплатных моделей - это бесплатно!'
                )
                
                keyboard = [
                    [InlineKeyboardButton("▶️ Далее", callback_data="tutorial_step3")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="tutorial_step1")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                
                try:
                    await query.edit_message_text(
                        tutorial_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message in tutorial_step2: {edit_error}, sending new message")
                    try:
                        await query.message.reply_text(
                            tutorial_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message in tutorial_step2: {send_error}", exc_info=True)
                        await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in tutorial_step2: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
        
        if data == "tutorial_step3":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            try:
                tutorial_text = (
                    '📖 <b>ШАГ 3: Как создать контент?</b>\n\n'
                    '━━━━━━━━━━━━━━━━━━━━\n\n'
                    '📝 <b>Простой процесс:</b>\n\n'
                    '1️⃣ Нажмите "📋 Все модели"\n'
                    '2️⃣ Выберите модель из бесплатных моделей\n'
                    '3️⃣ Введите описание (промпт)\n'
                    '   Пример: "Красивый закат над океаном"\n'
                    '4️⃣ Выберите параметры (размер, стиль и т.д.)\n'
                    '5️⃣ Нажмите "✅ Генерировать"\n'
                    '6️⃣ Подождите 10-60 секунд\n'
                    '7️⃣ Получите результат! 🎉\n\n'
                    '💡 <b>Совет:</b> Чем подробнее описание, тем лучше результат!'
                )
                
                keyboard = [
                    [InlineKeyboardButton("▶️ Далее", callback_data="tutorial_step4")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="tutorial_step2")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                
                try:
                    await query.edit_message_text(
                        tutorial_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message in tutorial_step3: {edit_error}, sending new message")
                    try:
                        await query.message.reply_text(
                            tutorial_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message in tutorial_step3: {send_error}", exc_info=True)
                        await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in tutorial_step3: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
        
        if data == "tutorial_step4":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            try:
                remaining_free = await get_user_free_generations_remaining(user_id)
                tutorial_text = (
                    '📖 <b>ШАГ 4: Баланс и оплата</b>\n\n'
                    '━━━━━━━━━━━━━━━━━━━━\n\n'
                    '💰 <b>Как это работает:</b>\n\n'
                    '🎁 <b>Бесплатно:</b>\n'
                    f'• {remaining_free if remaining_free > 0 else FREE_GENERATIONS_PER_DAY} бесплатных генераций в день\n'
                    f'• Пригласите друга - получите +{REFERRAL_BONUS_GENERATIONS} генераций!\n\n'
                    '💳 <b>Пополнение баланса:</b>\n'
                    '• Минимальная сумма: 50 ₽\n'
                    '• Быстрый выбор: 50, 100, 150 ₽\n'
                    '• Или укажите свою сумму\n'
                    '• Оплата через СБП (Система быстрых платежей)\n\n'
                    '💡 <b>Совет:</b> Начните с бесплатных генераций!'
                )
                
                keyboard = [
                    [InlineKeyboardButton("▶️ Завершить", callback_data="tutorial_complete")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="tutorial_step3")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                
                try:
                    await query.edit_message_text(
                        tutorial_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message in tutorial_step4: {edit_error}, sending new message")
                    try:
                        await query.message.reply_text(
                            tutorial_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message in tutorial_step4: {send_error}", exc_info=True)
                        await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in tutorial_step4: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
        
        if data == "tutorial_complete":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            try:
                tutorial_text = (
                '🎉 <b>ТУТОРИАЛ ЗАВЕРШЕН!</b>\n\n'
                '━━━━━━━━━━━━━━━━━━━━\n\n'
                '✅ Теперь вы знаете:\n'
                '• Что такое AI-генерация\n'
                '• Как выбрать модель\n'
                '• Как создать контент\n'
                '• Как пополнить баланс\n\n'
                '🚀 <b>Готовы начать?</b>\n\n'
                '💡 <b>Рекомендация:</b>\n'
                    'Начните с бесплатной генерации в бесплатных моделях!\n'
                'Просто выберите модель и опишите, что хотите создать.'
            )
            
                keyboard = [
                    [InlineKeyboardButton("📋 Все модели", callback_data="all_models")],
                    [InlineKeyboardButton("🆓 Бесплатные модели", callback_data="free_tools")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
                ]
                
                try:
                    await query.edit_message_text(
                        tutorial_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message in tutorial_complete: {edit_error}, sending new message")
                    try:
                        await query.message.reply_text(
                            tutorial_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message in tutorial_complete: {send_error}", exc_info=True)
                        await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in tutorial_complete: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
        
        if data == "help_menu":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            
            # Get user language
            user_lang = get_user_language(user_id)
            is_new = await is_new_user_async(user_id)
            
            if is_new:
                if user_lang == 'ru':
                    help_text = (
                        '📋 <b>ПОМОЩЬ ДЛЯ НОВЫХ ПОЛЬЗОВАТЕЛЕЙ</b>\n\n'
                        '━━━━━━━━━━━━━━━━━━━━\n\n'
                        '👋 <b>Добро пожаловать!</b>\n\n'
                        '🎯 <b>Быстрый старт:</b>\n'
                        '1. Нажмите "📋 Все модели"\n'
                        '2. Выберите "🆓 Бесплатные модели" (это бесплатно!)\n'
                        '3. Введите описание, например: "Кот в космосе"\n'
                        '4. Нажмите "✅ Генерировать"\n'
                        '5. Получите результат через 10-30 секунд!\n\n'
                        '━━━━━━━━━━━━━━━━━━━━\n\n'
                        '💡 <b>Полезные команды:</b>\n'
                        '/start - Главное меню\n'
                        '/models - Показать все модели\n'
                        '/balance - Проверить баланс\n'
                        '/help - Эта справка\n\n'
                        '❓ <b>Нужна помощь?</b>\n'
                        'Нажмите "❓ Как это работает?" для интерактивного туториала!'
                    )
                else:
                    help_text = (
                        '📋 <b>HELP FOR NEW USERS</b>\n\n'
                        '━━━━━━━━━━━━━━━━━━━━\n\n'
                        '👋 <b>Welcome!</b>\n\n'
                        '🎯 <b>Quick Start:</b>\n'
                        '1. Click "📋 All Models"\n'
                        '2. Select "🆓 Free tools" (it\'s free!)\n'
                        '3. Enter description, e.g.: "Cat in space"\n'
                        '4. Click "✅ Generate"\n'
                        '5. Get result in 10-30 seconds!\n\n'
                        '━━━━━━━━━━━━━━━━━━━━\n\n'
                        '💡 <b>Useful Commands:</b>\n'
                        '/start - Main menu\n'
                        '/models - Show all models\n'
                        '/balance - Check balance\n'
                        '/help - This help\n\n'
                        '❓ <b>Need help?</b>\n'
                        'Click "❓ How it works?" for interactive tutorial!'
                    )
            else:
                if user_lang == 'ru':
                    help_text = (
                        '📋 <b>ДОСТУПНЫЕ КОМАНДЫ</b>\n\n'
                        '━━━━━━━━━━━━━━━━━━━━\n\n'
                        '🔹 <b>Основные:</b>\n'
                        '/start - Главное меню\n'
                        '/models - Показать модели\n'
                        '/balance - Проверить баланс\n'
                        '/generate - Начать генерацию\n'
                        '/help - Справка\n\n'
                    )
                else:
                    help_text = (
                        '📋 <b>AVAILABLE COMMANDS</b>\n\n'
                        '━━━━━━━━━━━━━━━━━━━━\n\n'
                        '🔹 <b>Main:</b>\n'
                        '/start - Main menu\n'
                        '/models - Show models\n'
                        '/balance - Check balance\n'
                        '/generate - Start generation\n'
                        '/help - Help\n\n'
                    )
                
                if get_is_admin(user_id):
                    if user_lang == 'ru':
                        help_text += (
                            '👑 <b>Административные:</b>\n'
                            '/search - Поиск в базе знаний\n'
                            '/add - Добавление знаний\n'
                            '/admin - Пользователи и ручные пополнения\n'
                            '/payments - Просмотр платежей\n'
                            '/block_user - Заблокировать пользователя\n'
                            '/unblock_user - Разблокировать пользователя\n'
                            '/user_balance - Баланс пользователя\n\n'
                        )
                    else:
                        help_text += (
                            '👑 <b>Administrative:</b>\n'
                            '/search - Search knowledge base\n'
                            '/add - Add knowledge\n'
                            '/admin - User overview and manual top-ups\n'
                            '/payments - View payments\n'
                            '/block_user - Block user\n'
                            '/unblock_user - Unblock user\n'
                            '/user_balance - User balance\n\n'
                        )
                
                if user_lang == 'ru':
                    help_text += (
                        '💡 <b>Как использовать:</b>\n'
                        '1. Выберите модель из меню\n'
                        '2. Введите промпт (описание)\n'
                        '3. Выберите параметры через кнопки\n'
                        '4. Подтвердите генерацию\n'
                        '5. Получите результат!\n\n'
                        '📚 <b>Полезные функции:</b>\n'
                        '• "📚 Мои генерации" - просмотр истории\n'
                        '• "🔄 Повторить" - создать с теми же параметрами\n'
                        '• "💳 Пополнить" - пополнение баланса'
                    )
                else:
                    help_text += (
                        '💡 <b>How to use:</b>\n'
                        '1. Select model from menu\n'
                        '2. Enter prompt (description)\n'
                        '3. Select parameters via buttons\n'
                        '4. Confirm generation\n'
                        '5. Get result!\n\n'
                        '📚 <b>Useful features:</b>\n'
                        '• "📚 My generations" - view history\n'
                        '• "🔄 Repeat" - create with same parameters\n'
                        '• "💳 Top up" - top up balance'
                    )
            
            keyboard = []
            if is_new:
                if user_lang == 'ru':
                    keyboard.append([InlineKeyboardButton("❓ Как это работает?", callback_data="tutorial_start")])
                else:
                    keyboard.append([InlineKeyboardButton("❓ How it works?", callback_data="tutorial_start")])
            if user_lang == 'ru':
                keyboard.append([
                    InlineKeyboardButton("🎁 Колесо удачи", callback_data="claim_gift"),
                    InlineKeyboardButton(t('btn_copy_bot', lang=user_lang), callback_data="copy_bot")
                ])
                keyboard.append([
                    InlineKeyboardButton("🇷🇺 Русский", callback_data="set_language:ru"),
                    InlineKeyboardButton("🇺🇸 English", callback_data="set_language:en")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("🎁 Wheel of Fortune", callback_data="claim_gift"),
                    InlineKeyboardButton(t('btn_copy_bot', lang=user_lang), callback_data="copy_bot")
                ])
                keyboard.append([
                    InlineKeyboardButton("🇷🇺 Russian", callback_data="set_language:ru"),
                    InlineKeyboardButton("🇺🇸 English", callback_data="set_language:en")
                ])
            keyboard.append([
                InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")
            ])
            
            try:
                await query.edit_message_text(
                    help_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message in help_menu: {e}", exc_info=True)
                try:
                    await query.message.reply_text(
                        help_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except:
                    pass
            return ConversationHandler.END
        
        if data == "support_contact":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            
            # Get user language
            user_lang = get_user_language(user_id)
            support_info = get_support_contact()
            
            # Translate support contact message if needed
            if user_lang == 'en' and 'Поддержка' in support_info:
                # If support info is in Russian but user wants English, add English header
                support_info = (
                    '💬 <b>SUPPORT</b>\n\n'
                    '━━━━━━━━━━━━━━━━━━━━\n\n'
                    'If you have any questions or need help, please contact our support team:\n\n'
                    + support_info.replace('💬 <b>Поддержка</b>', '').replace('━━━━━━━━━━━━━━━━━━━━', '').strip()
                )
            
            keyboard = [
                [InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_menu")]
            ]
            
            try:
                await query.edit_message_text(
                    support_info,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message in support_contact: {e}", exc_info=True)
                try:
                    await query.message.reply_text(
                        support_info,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except:
                    pass
            return ConversationHandler.END
        
        # Handle copy bot request
        if data == "copy_bot":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            
            # Get user language
            user_lang = get_user_language(user_id)
            
            # Create admin link
            admin_link = f"tg://user?id={ADMIN_ID}"
            
            # Create message with admin link
            if user_lang == 'ru':
                copy_message = (
                    f"{t('msg_copy_bot_title', lang=user_lang)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{t('msg_copy_bot_description', lang=user_lang)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👨‍💻 <a href=\"{admin_link}\">Связаться с администратором</a>"
                )
            else:
                copy_message = (
                    f"{t('msg_copy_bot_title', lang=user_lang)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"{t('msg_copy_bot_description', lang=user_lang)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👨‍💻 <a href=\"{admin_link}\">Contact Administrator</a>"
                )
            
            keyboard = [
                [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]
            ]
            
            try:
                await query.edit_message_text(
                    copy_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
                    disable_web_page_preview=False
                )
            except Exception as e:
                logger.error(f"Error editing message in copy_bot: {e}", exc_info=True)
                try:
                    await query.message.reply_text(
                        copy_message,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
                        disable_web_page_preview=False
                    )
                except:
                    pass
            return ConversationHandler.END
        
        if data == "referral_info":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            reset_session_on_navigation(user_id, reason="referral_info")
            
            # Show referral information
            referral_link = get_user_referral_link(user_id)
            referrals_count = len(get_user_referrals(user_id))
            remaining_free = await get_user_free_generations_remaining(user_id)
            
            user_lang = get_user_language(user_id)
            
            referral_text = (
                f'{t("msg_referral_title", lang=user_lang)}\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'{t("msg_referral_how_it_works", lang=user_lang, bonus=REFERRAL_BONUS_GENERATIONS)}\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'{t("msg_referral_stats", lang=user_lang, count=referrals_count, bonus_total=referrals_count * REFERRAL_BONUS_GENERATIONS, remaining=remaining_free)}\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'{t("msg_referral_important", lang=user_lang)}\n\n'
                f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                f'{t("msg_referral_link_title", lang=user_lang)}\n\n'
                f'<code>{referral_link}</code>\n\n'
                f'{t("msg_referral_send", lang=user_lang, bonus=REFERRAL_BONUS_GENERATIONS)}'
            )
            keyboard = [
                [InlineKeyboardButton(t('btn_copy_link', lang=user_lang), url=referral_link)],
                [InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")]
            ]
            
            try:
                await query.edit_message_text(
                    referral_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message in referral_info: {e}", exc_info=True)
                try:
                    await query.message.reply_text(
                        referral_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except:
                    pass
            return ConversationHandler.END
        
        if data == "my_generations":
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
            except:
                pass
            
            # Show user's generation history
            history = get_user_generations_history(user_id, limit=20)
            
            # Debug: log history loading
            logger.info(f"Loading history for user {user_id}: found {len(history)} generations")
            
            # Check if file exists and show helpful message
            if not history:
                user_lang = get_user_language(user_id)
                file_exists = os.path.exists(GENERATIONS_HISTORY_FILE)
                
                # Load full history to check if there are any users at all
                full_history = {}
                total_users = 0
                if file_exists:
                    try:
                        full_history = load_json_file(GENERATIONS_HISTORY_FILE, {})
                        total_users = len(full_history)
                        logger.info(f"History file exists with {total_users} users. Checking for user {user_id}...")
                    except Exception as e:
                        logger.error(f"Error loading history file: {e}", exc_info=True)
                
                if user_lang == 'ru':
                    message_text = (
                        "📚 <b>Мои генерации</b>\n\n"
                        "❌ У вас пока нет сохраненных генераций.\n\n"
                    )
                    if not file_exists:
                        message_text += (
                            "⚠️ <b>Примечание:</b> Файл истории не найден.\n"
                            "Это может произойти после обновления бота.\n\n"
                        )
                    elif total_users > 0:
                        message_text += (
                            f"ℹ️ В системе сохранено {total_users} пользователей с историей.\n"
                            f"Если вы создавали генерации ранее, они должны отображаться.\n\n"
                        )
                    message_text += "💡 После создания контента все ваши работы будут сохранены здесь."
                else:
                    message_text = (
                        "📚 <b>My Generations</b>\n\n"
                        "❌ You don't have any saved generations yet.\n\n"
                    )
                    if not file_exists:
                        message_text += (
                            "⚠️ <b>Note:</b> History file not found.\n"
                            "This may happen after bot update.\n\n"
                        )
                    elif total_users > 0:
                        message_text += (
                            f"ℹ️ System has {total_users} users with history saved.\n"
                            f"If you created generations before, they should appear.\n\n"
                        )
                    message_text += "💡 After creating content, all your works will be saved here."
                
                keyboard = [[InlineKeyboardButton("◀️ Назад в меню" if user_lang == 'ru' else "◀️ Back to menu", callback_data="back_to_menu")]]
                try:
                    await query.edit_message_text(
                        message_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error editing message in my_generations (empty): {e}", exc_info=True)
                    try:
                        await query.message.reply_text(
                            message_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                    except:
                        pass
                return ConversationHandler.END
            
            # Show first generation with navigation
            try:
                from datetime import datetime
                
                gen = history[0]
                timestamp = gen.get('timestamp', 0)
                if timestamp:
                    date_str = datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M')
                else:
                    date_str = 'Неизвестно'
                
                model_name = gen.get('model_name', gen.get('model_id', 'Unknown'))
                result_urls = gen.get('result_urls', [])
                price = gen.get('price', 0)
                is_free = gen.get('is_free', False)
                
                user_lang = get_user_language(user_id)
                
                history_text = (
                    f"📚 <b>Мои генерации</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📊 <b>Всего:</b> {len(history)} генераций\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎨 <b>Генерация #{gen.get('id', 1)}</b>\n"
                    f"📅 <b>Дата:</b> {date_str}\n"
                    f"🤖 <b>Модель:</b> {model_name}\n"
                    f"💰 <b>Стоимость:</b> {'🎁 Бесплатно' if is_free else format_rub_amount(price)}\n"
                    f"📦 <b>Результатов:</b> {len(result_urls)}\n\n"
                )
                
                if len(history) > 1:
                    history_text += f"💡 <b>Показана последняя генерация</b>\n"
                    history_text += f"Используйте кнопки для навигации\n\n"
                
                keyboard = []
                
                # Navigation buttons if more than 1 generation
                if len(history) > 1:
                    keyboard.append([
                        InlineKeyboardButton(t('btn_previous', lang=user_lang), callback_data=f"gen_history:{gen.get('id', 1)}:prev"),
                        InlineKeyboardButton(t('btn_next', lang=user_lang), callback_data=f"gen_history:{gen.get('id', 1)}:next")
                    ])
                
                # Action buttons
                if result_urls:
                    keyboard.append([
                        InlineKeyboardButton("👁️ Показать результат", callback_data=f"gen_view:{gen.get('id', 1)}")
                    ])
                    keyboard.append([
                        InlineKeyboardButton("🔄 Повторить", callback_data=f"gen_repeat:{gen.get('id', 1)}")
                    ])
                
                keyboard.append([InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")])
                
                try:
                    await query.edit_message_text(
                        history_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error editing message in my_generations: {e}", exc_info=True)
                    try:
                        await query.message.reply_text(
                            history_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error in my_generations: {e}", exc_info=True)
                try:
                    await query.answer("❌ Ошибка при загрузке истории", show_alert=True)
                except:
                    pass
            return ConversationHandler.END
        
        if data.startswith("gen_view:"):
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            # View specific generation result
            parts = data.split(":", 1)
            if len(parts) < 2:
                try:
                    await query.answer("Ошибка: неверный формат запроса", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            try:
                gen_id = int(parts[1])
            except (ValueError, TypeError):
                try:
                    await query.answer("Ошибка: неверный ID генерации", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            gen = get_generation_by_id(user_id, gen_id)
            
            if not gen:
                try:
                    await query.answer("❌ Генерация не найдена", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            result_urls = gen.get('result_urls', [])
            if not result_urls:
                try:
                    await query.answer("❌ Результаты не найдены", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            user_lang = get_user_language(user_id)
            
            # Send media
            try:
                session_http = await get_http_client()
                for i, url in enumerate(result_urls[:5]):
                    try:
                        async with session_http.get(url) as resp:
                                if resp.status == 200:
                                    media_data = await resp.read()
                                    
                                    is_last = (i == len(result_urls[:5]) - 1)
                                    is_video = gen.get('model_id', '') in ['sora-2-text-to-video', 'sora-watermark-remover', 'kling-2.6/image-to-video', 'kling-2.6/text-to-video', 'kling/v2-5-turbo-text-to-video-pro', 'kling/v2-5-turbo-image-to-video-pro', 'wan/2-5-image-to-video', 'wan/2-5-text-to-video', 'wan/2-2-animate-move', 'wan/2-2-animate-replace', 'hailuo/02-text-to-video-pro', 'hailuo/02-image-to-video-pro', 'hailuo/02-text-to-video-standard', 'hailuo/02-image-to-video-standard']
                                    
                                    keyboard = []
                                    if is_last:
                                        keyboard = [
                                            [InlineKeyboardButton(t('btn_back_to_history', lang=user_lang), callback_data="my_generations")],
                                            [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]
                                        ]
                                    
                                    if is_video:
                                        video_file = io.BytesIO(media_data)
                                        video_file.name = f"generated_video_{i+1}.mp4"
                                        await context.bot.send_video(
                                            chat_id=update.effective_chat.id,
                                            video=video_file,
                                            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
                                        )
                                    else:
                                        photo_file = io.BytesIO(media_data)
                                        photo_file.name = f"generated_image_{i+1}.png"
                                        await context.bot.send_photo(
                                            chat_id=update.effective_chat.id,
                                            photo=photo_file,
                                            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
                                        )
                    except Exception as e:
                        logger.error(f"Error sending generation result (HTTP API call): {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Error in gen_view API calls: {e}", exc_info=True)
                try:
                    user_lang = get_user_language(user_id) if user_id else 'ru'
                    error_msg = "Ошибка сервера, попробуйте позже" if user_lang == 'ru' else "Server error, please try later"
                    await query.answer(error_msg, show_alert=True)
                except:
                    pass
            
            try:
                await query.answer("✅ Результаты отправлены")
            except:
                pass
            return ConversationHandler.END
        
        if data.startswith("gen_repeat:"):
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            # Repeat generation with same parameters
            parts = data.split(":", 1)
            if len(parts) < 2:
                try:
                    await query.answer("Ошибка: неверный формат запроса", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            try:
                gen_id = int(parts[1])
            except (ValueError, TypeError):
                try:
                    await query.answer("Ошибка: неверный ID генерации", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            gen = get_generation_by_id(user_id, gen_id)
            
            if not gen:
                try:
                    await query.answer("❌ Генерация не найдена", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            # Restore session from history
            model_id = gen.get('model_id')
            params = gen.get('params', {})
            model_info = get_model_by_id(model_id)
            
            if not model_info:
                try:
                    await query.answer("❌ Модель не найдена", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            user_lang = get_user_language(user_id)
            
            user_sessions[user_id] = {
                'model_id': model_id,
                'model_info': model_info,
                'params': params.copy(),
                'properties': model_info.get('input_params', {}),
                'required': []
            }
            
            # Go directly to confirmation
            try:
                await query.answer("✅ Параметры восстановлены")
            except:
                pass
            
            try:
                # Format parameters for display
                params = gen.get('params', {})
                params_preview = "\n".join([f"  • {k}: {str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in list(params.items())[:5]])
                if len(params) > 5:
                    params_preview += f"\n  ... и еще {len(params) - 5} параметров"
                
                if user_lang == 'ru':
                    repeat_msg = (
                        "🔄 <b>Повторная генерация</b>\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🤖 <b>Модель:</b> {model_info.get('name', model_id)}\n\n"
                        f"⚙️ <b>Параметры восстановлены из истории:</b>\n{params_preview if params_preview else '  (нет параметров)'}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "💡 <b>Что будет дальше:</b>\n"
                        "• Параметры уже заполнены\n"
                        "• Вы можете сразу начать генерацию\n"
                        "• Или вернуться и изменить параметры\n\n"
                        "🚀 <b>Подтвердите генерацию:</b>"
                    )
                else:
                    repeat_msg = (
                        "🔄 <b>Repeat generation</b>\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🤖 <b>Model:</b> {model_info.get('name', model_id)}\n\n"
                        f"⚙️ <b>Parameters restored from history:</b>\n{params_preview if params_preview else '  (no parameters)'}\n\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "💡 <b>What's next:</b>\n"
                        "• Parameters are already filled\n"
                        "• You can start generation immediately\n"
                        "• Or go back and change parameters\n\n"
                        "🚀 <b>Confirm generation:</b>"
                    )
                
                logger.info(f"✅ [UX IMPROVEMENT] Sending improved repeat generation message to user {user_id}")
                await query.edit_message_text(
                    repeat_msg,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(t('btn_confirm_generate_text', lang=user_lang), callback_data="confirm_generate")],
                        [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                        [InlineKeyboardButton(t('btn_back_to_history', lang=user_lang), callback_data="my_generations")],
                        [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]
                    ]),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message in gen_repeat: {e}", exc_info=True)
                try:
                    # Format parameters for display
                    params = gen.get('params', {})
                    params_preview = "\n".join([f"  • {k}: {str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in list(params.items())[:5]])
                    if len(params) > 5:
                        params_preview += f"\n  ... и еще {len(params) - 5} параметров"
                    
                    if user_lang == 'ru':
                        repeat_msg = (
                            "🔄 <b>Повторная генерация</b>\n\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🤖 <b>Модель:</b> {model_info.get('name', model_id)}\n\n"
                            f"⚙️ <b>Параметры восстановлены из истории:</b>\n{params_preview if params_preview else '  (нет параметров)'}\n\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "💡 <b>Что будет дальше:</b>\n"
                            "• Параметры уже заполнены\n"
                            "• Вы можете сразу начать генерацию\n"
                            "• Или вернуться и изменить параметры\n\n"
                            "🚀 <b>Подтвердите генерацию:</b>"
                        )
                    else:
                        repeat_msg = (
                            "🔄 <b>Repeat generation</b>\n\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"🤖 <b>Model:</b> {model_info.get('name', model_id)}\n\n"
                            f"⚙️ <b>Parameters restored from history:</b>\n{params_preview if params_preview else '  (no parameters)'}\n\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "💡 <b>What's next:</b>\n"
                            "• Parameters are already filled\n"
                            "• You can start generation immediately\n"
                            "• Or go back and change parameters\n\n"
                            "🚀 <b>Confirm generation:</b>"
                        )
                    
                    logger.info(f"✅ [UX IMPROVEMENT] Sending improved repeat generation message (fallback) to user {user_id}")
                    await query.message.reply_text(
                        repeat_msg,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Генерировать" if user_lang == 'ru' else "✅ Generate", callback_data="confirm_generate")],
                            [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                            [InlineKeyboardButton("◀️ Назад к истории" if user_lang == 'ru' else "◀️ Back to history", callback_data="my_generations")],
                            [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]
                        ]),
                        parse_mode='HTML'
                    )
                except:
                    pass
            return CONFIRMING_GENERATION
        
        if data.startswith("gen_history:"):
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            # Navigate through generation history
            parts = data.split(":", 2)
            if len(parts) < 3:
                try:
                    await query.answer("❌ Ошибка навигации", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            try:
                current_gen_id = int(parts[1])
            except (ValueError, TypeError):
                try:
                    await query.answer("❌ Ошибка: неверный ID генерации", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            direction = parts[2]  # prev or next
            
            history = get_user_generations_history(user_id, limit=100)
            if not history:
                try:
                    await query.answer("❌ История пуста", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            # Find current generation index
            current_index = -1
            for i, gen in enumerate(history):
                if gen.get('id') == current_gen_id:
                    current_index = i
                    break
            
            if current_index == -1:
                try:
                    await query.answer("❌ Генерация не найдена", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            # Navigate
            if direction == 'prev' and current_index < len(history) - 1:
                new_index = current_index + 1
            elif direction == 'next' and current_index > 0:
                new_index = current_index - 1
            else:
                try:
                    await query.answer("⚠️ Это первая/последняя генерация", show_alert=True)
                except:
                    pass
                return ConversationHandler.END
            
            user_lang = get_user_language(user_id)
            
            gen = history[new_index]
            from datetime import datetime
            
            timestamp = gen.get('timestamp', 0)
            if timestamp:
                date_str = datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M')
            else:
                date_str = 'Неизвестно'
            
            model_name = gen.get('model_name', gen.get('model_id', 'Unknown'))
            result_urls = gen.get('result_urls', [])
            price = gen.get('price', 0)
            is_free = gen.get('is_free', False)
            
            if user_lang == 'ru':
                history_text = (
                    f"📚 <b>Мои генерации</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📊 <b>Всего генераций:</b> {len(history)}\n"
                    f"📍 <b>Показана:</b> {new_index + 1} из {len(history)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎨 <b>Генерация #{gen.get('id', 1)}</b>\n\n"
                    f"📅 <b>Дата создания:</b> {date_str}\n"
                    f"🤖 <b>Модель:</b> {model_name}\n"
                    f"💰 <b>Стоимость:</b> {'🎁 Бесплатно' if is_free else format_rub_amount(price)}\n"
                    f"📦 <b>Результатов:</b> {len(result_urls)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 <b>Что можно сделать:</b>\n"
                    f"• Просмотреть результат генерации\n"
                    f"• Повторить генерацию с теми же параметрами\n"
                    f"• Перейти к другой генерации\n\n"
                    f"🔄 <b>Навигация:</b> Используйте кнопки ниже"
                )
            else:
                history_text = (
                    f"📚 <b>My Generations</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📊 <b>Total generations:</b> {len(history)}\n"
                    f"📍 <b>Showing:</b> {new_index + 1} of {len(history)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎨 <b>Generation #{gen.get('id', 1)}</b>\n\n"
                    f"📅 <b>Created:</b> {date_str}\n"
                    f"🤖 <b>Model:</b> {model_name}\n"
                    f"💰 <b>Cost:</b> {'🎁 Free' if is_free else format_rub_amount(price)}\n"
                    f"📦 <b>Results:</b> {len(result_urls)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 <b>What you can do:</b>\n"
                    f"• View generation result\n"
                    f"• Repeat generation with same parameters\n"
                    f"• Navigate to another generation\n\n"
                    f"🔄 <b>Navigation:</b> Use buttons below"
                )
            
            logger.info(f"✅ [UX IMPROVEMENT] Sending improved generation history view to user {user_id}")
            
            keyboard = []
            
            # Navigation buttons
            keyboard.append([
                InlineKeyboardButton("◀️ Предыдущая", callback_data=f"gen_history:{gen.get('id', 1)}:prev"),
                InlineKeyboardButton("Следующая ▶️", callback_data=f"gen_history:{gen.get('id', 1)}:next")
            ])
            
            # Action buttons
            if result_urls:
                keyboard.append([
                    InlineKeyboardButton("👁️ Показать результат", callback_data=f"gen_view:{gen.get('id', 1)}")
                ])
                keyboard.append([
                    InlineKeyboardButton("🔄 Повторить", callback_data=f"gen_repeat:{gen.get('id', 1)}")
                ])
            
            keyboard.append([InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")])
            
            await query.edit_message_text(
                history_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        # Handle model card display (model:<model_id>)
        if data.startswith("m:"):
            short_id = data.split(":", 1)[1] if ":" in data else ""
            if not short_id:
                user_lang = get_user_language(user_id) if user_id else "ru"
                await query.answer(
                    t('error_model_not_found', lang=user_lang, default="❌ Модель не найдена"),
                    show_alert=True,
                )
                return ConversationHandler.END
            models = get_models_sync()
            matches = [m for m in models if m.get("id", "").startswith(short_id)]
            if len(matches) == 1:
                data = f"model:{matches[0].get('id')}"
            else:
                user_lang = get_user_language(user_id) if user_id else "ru"
                error_msg = (
                    "❌ Не удалось определить модель. Вернитесь в меню и выберите снова."
                    if user_lang == "ru"
                    else "❌ Could not resolve model. Return to the menu and select again."
                )
                await query.edit_message_text(
                    error_msg,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")]]
                    ),
                    parse_mode="HTML",
                )
                return ConversationHandler.END

        if data.startswith("model:") or data.startswith("modelk:"):
            try:
                await query.answer()
            except:
                pass
            
            # Используем новый каталог
            user_lang = get_user_language(user_id)
            
            try:
                from app.helpers.models_menu_handlers import handle_model_callback
                success = await handle_model_callback(query, user_id, user_lang, data)
                
                if success:
                    return SELECTING_MODEL
                else:
                    return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in handle_model_callback: {e}", exc_info=True)
                if user_lang == 'ru':
                    await query.answer("❌ Ошибка при загрузке модели", show_alert=True)
                else:
                    await query.answer("❌ Error loading model", show_alert=True)
                return ConversationHandler.END
            
            # Fallback на старый код (если новый обработчик не сработал)
            parts = data.split(":", 1)
            if len(parts) < 2:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_invalid_model', lang=user_lang, default="❌ Ошибка: неверный формат запроса"), show_alert=True)
                return ConversationHandler.END
            
            model_id = parts[1] if len(parts) > 1 else None
            if not model_id:
                # Пробуем разрешить через новый каталог
                from app.helpers.models_menu import resolve_model_id_from_callback
                model_id = resolve_model_id_from_callback(data)
            
            if not model_id:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_model_not_found', lang=user_lang, default="❌ Модель не найдена"), show_alert=True)
                return ConversationHandler.END
            
            # Пробуем получить из нового каталога
            from app.kie_catalog import get_model as get_model_from_catalog
            catalog_model = get_model_from_catalog(model_id)
            
            if catalog_model:
                # Используем новый каталог
                from app.helpers.models_menu import build_model_card_text
                card_text, keyboard_markup = build_model_card_text(catalog_model, 0, user_lang)
                try:
                    await query.edit_message_text(
                        card_text,
                        reply_markup=keyboard_markup,
                        parse_mode='HTML'
                    )
                    return SELECTING_MODEL
                except Exception as e:
                    logger.error(f"Error showing model card: {e}", exc_info=True)
                    await query.answer("❌ Ошибка при отображении модели", show_alert=True)
                    return ConversationHandler.END
            
            # Fallback на старый код
            model = get_model_by_id(model_id)
            
            if not model:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_model_not_found', lang=user_lang, default="❌ Модель не найдена"), show_alert=True)
                return ConversationHandler.END
            
            # Нормализуем модель для единообразного использования
            try:
                from kie_models import normalize_model_for_api
                normalized = normalize_model_for_api(model)
            except:
                normalized = model
            
            user_lang = get_user_language(user_id)
            
            # Формируем карточку модели
            title = normalized.get('title') or normalized.get('name') or model_id
            emoji = normalized.get('emoji', '')
            gen_type = normalized.get('generation_type', 'unknown')
            help_text = normalized.get('help') or normalized.get('description', '')
            input_schema = normalized.get('input_schema') or normalized.get('input_params', {})
            
            # Формируем улучшенный текст карточки модели
            if user_lang == 'ru':
                model_info_text = (
                    f"{emoji} <b>{title}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📋 <b>Тип генерации:</b> {gen_type.replace('_', '-')}\n\n"
                    f"ℹ️ <b>Описание:</b>\n{help_text}\n\n"
                )
                
                # Добавляем информацию о параметрах (без технической схемы)
                if input_schema:
                    required_params = [k for k, v in input_schema.items() if v.get('required', False)]
                    optional_params = [k for k, v in input_schema.items() if not v.get('required', False)]
                    
                    model_info_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    model_info_text += "⚙️ <b>Основные параметры:</b>\n"
                    if required_params:
                        model_info_text += f"• Обязательные: {', '.join(required_params[:5])}"
                        if len(required_params) > 5:
                            model_info_text += f" и еще {len(required_params) - 5}"
                        model_info_text += "\n"
                    if optional_params:
                        model_info_text += f"• Опциональные: {', '.join(optional_params[:5])}"
                        if len(optional_params) > 5:
                            model_info_text += f" и еще {len(optional_params) - 5}"
                        model_info_text += "\n"
                    model_info_text += "\n"
                
                model_info_text += (
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 <b>Совет:</b> После начала генерации вы сможете настроить все параметры пошагово.\n\n"
                    "🚀 <b>Готовы начать?</b> Нажмите кнопку ниже!"
                )
            else:
                model_info_text = (
                    f"{emoji} <b>{title}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📋 <b>Generation type:</b> {gen_type.replace('_', '-')}\n\n"
                    f"ℹ️ <b>Description:</b>\n{help_text}\n\n"
                )
                
                # Add parameter info (without technical schema)
                if input_schema:
                    required_params = [k for k, v in input_schema.items() if v.get('required', False)]
                    optional_params = [k for k, v in input_schema.items() if not v.get('required', False)]
                    
                    model_info_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    model_info_text += "⚙️ <b>Main parameters:</b>\n"
                    if required_params:
                        model_info_text += f"• Required: {', '.join(required_params[:5])}"
                        if len(required_params) > 5:
                            model_info_text += f" and {len(required_params) - 5} more"
                        model_info_text += "\n"
                    if optional_params:
                        model_info_text += f"• Optional: {', '.join(optional_params[:5])}"
                        if len(optional_params) > 5:
                            model_info_text += f" and {len(optional_params) - 5} more"
                        model_info_text += "\n"
                    model_info_text += "\n"
                
                model_info_text += (
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "💡 <b>Tip:</b> After starting generation, you'll be able to configure all parameters step by step.\n\n"
                    "🚀 <b>Ready to start?</b> Click the button below!"
                )
            
            logger.info(f"✅ [UX IMPROVEMENT] Sending improved model card to user {user_id} for model {model_id}")
            
            # Кнопки
            if user_lang == 'ru':
                keyboard = [
                    [InlineKeyboardButton("✅ Начать генерацию", callback_data=f"start:{model_id}")],
                    [InlineKeyboardButton("ℹ️ Пример запроса", callback_data=f"example:{model_id}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("✅ Start generation", callback_data=f"start:{model_id}")],
                    [InlineKeyboardButton("ℹ️ Example request", callback_data=f"example:{model_id}")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="back_to_menu")]
                ]
            
            await query.edit_message_text(
                text=model_info_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        # Handle start generation from model card (start:<model_id>)
        if data.startswith("start:"):
            try:
                await query.answer()
            except:
                pass
            
            parts = data.split(":", 1)
            if len(parts) < 2:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_invalid_model', lang=user_lang, default="❌ Ошибка: неверный формат запроса"), show_alert=True)
                return ConversationHandler.END
            
            model_id = parts[1]
            # Перенаправляем на select_model для начала генерации
            query.data = f"select_model:{model_id}"
            # Продолжаем обработку как select_model
            data = query.data
        
        # Handle example request (example:<model_id>)
        if data.startswith("example:"):
            try:
                await query.answer()
            except:
                pass
            
            parts = data.split(":", 1)
            if len(parts) < 2:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_invalid_model', lang=user_lang, default="❌ Ошибка: неверный формат запроса"), show_alert=True)
                return ConversationHandler.END
            
            model_id = parts[1]
            user_lang = get_user_language(user_id)
            
            # Пробуем получить из нового каталога
            from app.kie_catalog import get_model as get_model_from_catalog
            catalog_model = get_model_from_catalog(model_id)
            
            if catalog_model:
                # Используем новый каталог для примера
                mode = catalog_model.modes[0] if catalog_model.modes else None
                if user_lang == 'ru':
                    example_text = (
                        f"📸 <b>Пример запроса для {catalog_model.title_ru}</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>Тип генерации:</b> {catalog_model.type}\n\n"
                    )
                else:
                    example_text = (
                        f"📸 <b>Example request for {catalog_model.title_ru}</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>Generation type:</b> {catalog_model.type}\n\n"
                    )
                
                if mode:
                    mode_label = _resolve_mode_label(mode, 0, user_lang)
                    example_text += (
                        f"⚙️ <b>Режим:</b> {mode_label}\n\n"
                        if user_lang == 'ru'
                        else f"⚙️ <b>Mode:</b> {mode_label}\n\n"
                    )
                
                if user_lang == 'ru':
                    example_text += (
                        f"💡 <b>Совет:</b> После начала генерации вы сможете настроить все параметры пошагово.\n\n"
                        f"🚀 <b>Готовы начать?</b> Нажмите кнопку ниже!"
                    )
                else:
                    example_text += (
                        f"💡 <b>Tip:</b> After starting generation, you'll be able to configure all parameters step by step.\n\n"
                        f"🚀 <b>Ready to start?</b> Click the button below!"
                    )
                
                keyboard = [
                    [InlineKeyboardButton("🚀 Сгенерировать" if user_lang == 'ru' else "🚀 Generate", callback_data=f"select_model:{model_id}")],
                    [InlineKeyboardButton("ℹ️ Инфо" if user_lang == 'ru' else "ℹ️ Info", callback_data=f"info:{model_id}")],
                    [InlineKeyboardButton("⬅️ Назад" if user_lang == 'ru' else "⬅️ Back", callback_data=f"model:{model_id}")]
                ]
                
                try:
                    await query.edit_message_text(
                        text=example_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return SELECTING_MODEL
                except Exception as e:
                    logger.error(f"Error showing example from catalog: {e}", exc_info=True)
                    await query.answer("❌ Ошибка при загрузке примера", show_alert=True)
                    return ConversationHandler.END
            
            # Fallback на старый код
            model = get_model_by_id(model_id)
            
            if not model:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_model_not_found', lang=user_lang, default="❌ Модель не найдена"), show_alert=True)
                return ConversationHandler.END
            
            # Нормализуем модель
            try:
                from kie_models import normalize_model_for_api
                normalized = normalize_model_for_api(model)
            except:
                normalized = model
            
            user_lang = get_user_language(user_id)
            input_schema = normalized.get('input_schema') or normalized.get('input_params', {})
            
            # Формируем пример запроса
            example_text = f"📝 <b>Пример запроса для {normalized.get('title', model_id)}</b>\n\n"
            example_text += f"<b>Параметры:</b>\n"
            
            import json
            # Генерируем пример значений на основе схемы
            example_params = {}
            for param_name, param_type in input_schema.items():
                if param_type == 'string':
                    if 'prompt' in param_name.lower():
                        example_params[param_name] = "Красивый закат над океаном"
                    elif 'url' in param_name.lower():
                        example_params[param_name] = "https://example.com/image.jpg"
                    else:
                        example_params[param_name] = "пример значения"
                elif param_type == 'array':
                    example_params[param_name] = ["https://example.com/image1.jpg"]
                else:
                    example_params[param_name] = "пример"
            
            example_text += f"<code>{json.dumps(example_params, indent=2, ensure_ascii=False)}</code>\n\n"
            example_text += f"💡 <b>Инструкция:</b>\n{normalized.get('help', 'Следуйте инструкциям модели')}"
            
            keyboard = [
                [InlineKeyboardButton("✅ Начать генерацию", callback_data=f"start:{model_id}")],
                [InlineKeyboardButton("⬅️ Назад к модели", callback_data=f"model:{model_id}")]
            ]
            
            await query.edit_message_text(
                text=example_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return SELECTING_MODEL
        
        # Handle info: callback - shows detailed model information
        if data.startswith("info:"):
            try:
                await query.answer()
            except:
                pass
            
            parts = data.split(":", 1)
            if len(parts) < 2:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_invalid_model', lang=user_lang, default="❌ Ошибка: неверный формат запроса"), show_alert=True)
                return ConversationHandler.END
            
            model_id = parts[1]
            user_lang = get_user_language(user_id)
            
            # Пробуем получить из нового каталога
            from app.kie_catalog import get_model as get_model_from_catalog
            catalog_model = get_model_from_catalog(model_id)
            
            if catalog_model:
                # Используем новый каталог для отображения информации
                from app.helpers.models_menu import build_model_card_text
                card_text, keyboard_markup = build_model_card_text(catalog_model, 0, user_lang)
                try:
                    await query.edit_message_text(
                        card_text,
                        reply_markup=keyboard_markup,
                        parse_mode='HTML'
                    )
                    return SELECTING_MODEL
                except Exception as e:
                    logger.error(f"Error showing model info: {e}", exc_info=True)
                    await query.answer("❌ Ошибка при загрузке информации о модели", show_alert=True)
                    return ConversationHandler.END
            
            # Fallback на старый код
            model = get_model_by_id(model_id)
            if not model:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_model_not_found', lang=user_lang, default="❌ Модель не найдена"), show_alert=True)
                return ConversationHandler.END
            
            # Нормализуем модель
            try:
                from kie_models import normalize_model_for_api
                normalized = normalize_model_for_api(model)
            except:
                normalized = model
            
            user_lang = get_user_language(user_id)
            input_schema = normalized.get('input_schema') or normalized.get('input_params', {})
            
            # Формируем детальную информацию о модели
            if user_lang == 'ru':
                info_text = (
                    f"ℹ️ <b>Информация о модели: {normalized.get('title', model_id)}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                )
            else:
                info_text = (
                    f"ℹ️ <b>Model Information: {normalized.get('title', model_id)}</b>\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                )
            
            if normalized.get('description'):
                info_text += f"📝 <b>Описание:</b>\n{normalized.get('description')}\n\n"
            
            if input_schema:
                if user_lang == 'ru':
                    info_text += f"⚙️ <b>Параметры:</b>\n"
                else:
                    info_text += f"⚙️ <b>Parameters:</b>\n"
                
                for param_name, param_info in input_schema.items():
                    if isinstance(param_info, dict):
                        param_type = param_info.get('type', 'string')
                        param_desc = param_info.get('description', '')
                        required = param_info.get('required', False)
                        req_text = " (обязательный)" if required else " (опциональный)"
                        if user_lang != 'ru':
                            req_text = " (required)" if required else " (optional)"
                        info_text += f"• <b>{param_name}</b>: {param_type}{req_text}\n"
                        if param_desc:
                            info_text += f"  {param_desc}\n"
                    else:
                        info_text += f"• <b>{param_name}</b>: {param_info}\n"
            
            if normalized.get('help'):
                info_text += f"\n💡 <b>Совет:</b>\n{normalized.get('help')}\n"
            
            keyboard = [
                [InlineKeyboardButton("🚀 Сгенерировать" if user_lang == 'ru' else "🚀 Generate", callback_data=f"select_model:{model_id}")],
                [InlineKeyboardButton("📸 Пример" if user_lang == 'ru' else "📸 Example", callback_data=f"example:{model_id}")],
                [InlineKeyboardButton("⬅️ Назад" if user_lang == 'ru' else "⬅️ Back", callback_data=f"model:{model_id}")]
            ]
            
            await query.edit_message_text(
                text=info_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return SELECTING_MODEL
        
        # Handle model: callback - shows model card with "Start" button (canonical format for tests)
        if data.startswith("model:") or data.startswith("modelk:"):
            try:
                await query.answer()
            except:
                pass
            
            # Используем новый каталог
            user_lang = get_user_language(user_id)
            
            try:
                from app.helpers.models_menu_handlers import handle_model_callback
                success = await handle_model_callback(query, user_id, user_lang, data)
                
                if success:
                    return SELECTING_MODEL
                else:
                    return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in handle_model_callback (second handler): {e}", exc_info=True)
                # Fallback на старый код
                pass
            
            # Fallback на старый код
            parts = data.split(":", 1)
            if len(parts) < 2:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_invalid_model', lang=user_lang, default="❌ Ошибка: неверный формат запроса"), show_alert=True)
                return ConversationHandler.END
            
            model_id = parts[1] if len(parts) > 1 else None
            if not model_id:
                # Пробуем разрешить через новый каталог
                from app.helpers.models_menu import resolve_model_id_from_callback
                model_id = resolve_model_id_from_callback(data)
            
            if not model_id:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_model_not_found', lang=user_lang, default=f"❌ Модель не найдена"), show_alert=True)
                return ConversationHandler.END
            
            logger.info(f"Model card requested: model_id={model_id}, user_id={user_id}")
            
            # Пробуем получить из нового каталога
            from app.kie_catalog import get_model as get_model_from_catalog
            catalog_model = get_model_from_catalog(model_id)
            
            if catalog_model:
                # Используем новый каталог
                from app.helpers.models_menu import build_model_card_text
                card_text, keyboard_markup = build_model_card_text(catalog_model, 0, user_lang)
                try:
                    await query.edit_message_text(
                        card_text,
                        reply_markup=keyboard_markup,
                        parse_mode='HTML'
                    )
                    return SELECTING_MODEL
                except Exception as e:
                    logger.error(f"Error showing model card: {e}", exc_info=True)
                    await query.answer("❌ Ошибка при отображении модели", show_alert=True)
                    return ConversationHandler.END
            
            # Fallback на старый код
            # Get model from registry
            model_info = get_model_by_id_from_registry(model_id)
            if not model_info:
                user_lang = get_user_language(user_id)
                await query.answer(t('error_model_not_found', lang=user_lang, default=f"❌ Модель {model_id} не найдена"), show_alert=True)
                return ConversationHandler.END
            
            # Check if model is coming soon
            if model_info.get('coming_soon', False):
                user_lang = get_user_language(user_id)
                keyboard = [
                    [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
                ]
                error_msg = t('error_model_unavailable', lang=user_lang) or "Модель временно недоступна"
                try:
                    await query.edit_message_text(
                        error_msg,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                except Exception as edit_error:
                    logger.warning(f"Could not edit message for coming_soon model: {edit_error}")
                    try:
                        await query.message.reply_text(error_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except:
                        await query.answer(error_msg, show_alert=True)
                return ConversationHandler.END
            
            # Show model card with info and "Start" button
            user_balance = await get_user_balance_async(user_id)
            is_admin = get_is_admin(user_id)
            user_lang = get_user_language(user_id)
            
            is_admin_check = get_is_admin(user_id) if user_id is not None else is_admin
            min_price = get_from_price_value(model_id)
            price_text = get_model_price_text(model_id, None, is_admin_check, user_id)
            try:
                from app.services.pricing_service import get_model_price_info
                from app.config import get_settings

                settings = get_settings()
                mode_index = _resolve_mode_index(model_id, {}, user_id)
                price_info = get_model_price_info(model_id, mode_index, settings, is_admin=is_admin_check)
                trace_event(
                    "info",
                    correlation_id,
                    event="PRICE_CALC",
                    stage="PRICE_CALC",
                    update_type="callback",
                    action="SELECT_MODEL",
                    action_path=build_action_path(data),
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    model_id=model_id,
                    official_usd=price_info.get("official_usd") if price_info else None,
                    rate=price_info.get("usd_to_rub") if price_info else None,
                    multiplier=price_info.get("price_multiplier") if price_info else None,
                    price_rub=min_price,
                    is_admin=is_admin_check,
                    pricing_source="catalog",
                    always_fields=[
                        "model_id",
                        "official_usd",
                        "rate",
                        "multiplier",
                        "price_rub",
                        "is_admin",
                        "pricing_source",
                    ],
                )
            except Exception as price_exc:
                logger.debug("Pricing trace skipped: %s", price_exc)
            
            # Format model card
            model_name = model_info.get('name', model_id)
            model_emoji = model_info.get('emoji', '🤖')
            model_desc = model_info.get('description', '')
            model_category = model_info.get('category', 'Общее')
            
            model_info_text = (
                f"{model_emoji} <b>{model_name}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            
            if model_category:
                model_info_text += f"📁 <b>Категория:</b> {model_category}\n"
            
            if model_desc:
                model_info_text += f"\n📝 <b>Описание:</b>\n{model_desc}\n\n"
            
            model_info_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            model_info_text += f"💰 <b>Стоимость:</b> {price_text}\n\n"
            
            # Build keyboard with "Start" button
            keyboard = [
                [InlineKeyboardButton("🚀 Старт", callback_data=f"select_model:{model_id}")],
                [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
            ]
            
            # Try to edit message, fallback to reply if edit fails
            try:
                await query.edit_message_text(
                    model_info_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
            except Exception as edit_error:
                logger.warning(f"Could not edit message in model: handler: {edit_error}, sending new message")
                try:
                    await query.message.reply_text(
                        model_info_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    try:
                        await query.message.delete()
                    except:
                        pass
                except Exception as send_error:
                    logger.error(f"Could not send new message in model: handler: {send_error}", exc_info=True)
                    await query.answer(t('error_try_start', lang=user_lang, default="❌ Ошибка отображения. Попробуйте /start"), show_alert=True)
            
            return ConversationHandler.END
        
        mode_selected = False
        if data.startswith("select_mode:"):
            parts = data.split(":")
            if len(parts) < 3:
                await query.answer("Ошибка: неверный формат режима", show_alert=True)
                return ConversationHandler.END
            model_id = parts[1]
            try:
                mode_index = int(parts[2])
            except ValueError:
                await query.answer("Ошибка: неверный режим", show_alert=True)
                return ConversationHandler.END
            if user_id not in user_sessions:
                user_sessions[user_id] = {}
            user_sessions[user_id]["mode_index"] = mode_index
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
                update_id=update_id,
                action="MODE_SELECTED",
                action_path=build_action_path(data),
                model_id=model_id,
                param={"mode_index": mode_index},
                outcome="selected",
            )
            data = f"select_model:{model_id}"
            mode_selected = True

        if data.startswith("sku:") or data.startswith("sk:"):
            await query.answer()
            from app.pricing.ssot_catalog import get_sku_by_id, resolve_sku_callback

            sku_id = resolve_sku_callback(data)
            sku = get_sku_by_id(sku_id) if sku_id else None
            if not sku:
                user_lang = get_user_language(user_id)
                await query.edit_message_text(
                    "❌ Неверная бесплатная опция" if user_lang == "ru" else "❌ Invalid free option",
                )
                return ConversationHandler.END
            session = ensure_session_cached(context, session_store, user_id, update_id)
            session["prefill_params"] = dict(sku.params)
            session["sku_id"] = sku.sku_id
            data = f"select_model:{sku.model_id}"

        # Handle select_model: callback - starts generation flow directly (legacy, still supported)
        # Also handles start: callback (redirects to select_model:)
        if data.startswith("select_model:") or data.startswith("sel:"):
            # Handle short format sel: -> select_model:
            if data.startswith("sel:"):
                parts = data.split(":", 1)
                if len(parts) >= 2:
                    model_id = parts[1]
                    # Try to find full model_id by prefix (for backward compatibility)
                    # In most cases, sel: prefix means it was truncated, so we need to search
                    models = get_models_sync()
                    matching_models = [m for m in models if m.get('id', '').startswith(model_id)]
                    if matching_models:
                        model_id = matching_models[0].get('id')
                        data = f"select_model:{model_id}"
                    else:
                        data = f"select_model:{model_id}"
            
            # 🔥 MAXIMUM LOGGING: select_model entry
            logger.debug(f"🔥🔥🔥 SELECT_MODEL START: user_id={user_id}, data={data}")
            reset_session_context(
                user_id,
                reason="select_model",
                clear_gen_type=False,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            if not mode_selected and user_id in user_sessions:
                user_sessions[user_id].pop("mode_index", None)
            
            # Answer callback immediately to show button was pressed
            try:
                await query.answer()
                logger.info(f"✅ Query answered for select_model: user_id={user_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to answer query: {e}")
            
            parts = data.split(":", 1)
            if len(parts) < 2:
                logger.error(f"❌ Invalid select_model format: data={data}, user_id={user_id}")
                try:
                    await query.answer("Ошибка: неверный формат запроса", show_alert=True)
                except:
                    pass
                try:
                    await query.edit_message_text("❌ Ошибка: неверный формат запроса.")
                except:
                    try:
                        await query.message.reply_text("❌ Ошибка: неверный формат запроса.")
                    except:
                        pass
                return ConversationHandler.END
            model_id = parts[1]
            logger.debug(f"🔥🔥🔥 SELECT_MODEL: Parsed model_id={model_id}, user_id={user_id}")
            
            # Сначала пробуем получить из нового каталога
            model_info = None
            catalog_model = None
            try:
                from app.kie_catalog import get_model as get_model_from_catalog
                catalog_model = get_model_from_catalog(model_id)
                if catalog_model:
                    # Преобразуем catalog_model в формат model_info для совместимости
                    model_info = {
                        'id': catalog_model.id,
                        'name': catalog_model.title_ru,
                        'emoji': '🤖',  # Будет определено позже
                        'description': catalog_model.title_ru,
                        'category': catalog_model.type,
                        'coming_soon': False
                    }
                    logger.info(f"✅ SELECT_MODEL: Found in catalog: model_id={model_id}, name={catalog_model.title_ru}, user_id={user_id}")
            except Exception as e:
                logger.warning(f"⚠️ SELECT_MODEL: Error loading from catalog: {e}, trying registry")
            
            # Если не нашли в каталоге, пробуем старый реестр
            if not model_info:
                model_info = get_model_by_id_from_registry(model_id)
                logger.debug(f"🔥🔥🔥 SELECT_MODEL: Model lookup result: found={bool(model_info)}, model_name={model_info.get('name', 'N/A') if model_info else 'N/A'}, user_id={user_id}")
            
            if not model_info:
                logger.error(f"❌❌❌ MODEL NOT FOUND: model_id={model_id}, user_id={user_id}")
                user_lang = get_user_language(user_id)
                error_msg = t('error_model_not_found', lang=user_lang, default=f"❌ Модель {model_id} не найдена")
                try:
                    await query.edit_message_text(error_msg)
                except:
                    try:
                        await query.message.reply_text(error_msg)
                    except:
                        await query.answer(error_msg, show_alert=True)
                return ConversationHandler.END
            
            # Check if model is coming soon - НЕ показываем пользователю, просто возвращаем в меню
            if model_info.get('coming_soon', False):
                user_lang = get_user_language(user_id)
                # Не показываем "COMING SOON" - просто возвращаем в меню
                keyboard = [
                    [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
                ]
                
                await query.edit_message_text(
                    t('error_model_unavailable', lang=user_lang) or "Модель временно недоступна",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END

            # Load model spec early (needed for multi-mode selection)
            from app.kie_catalog import get_model
            model_spec = get_model(model_id)
            if not model_spec:
                await query.edit_message_text(
                    "❌ <b>Модель не найдена в каталоге</b>",
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            from app.ux.model_visibility import evaluate_model_visibility, STATUS_READY_VISIBLE
            visibility = evaluate_model_visibility(model_id)
            if visibility.status != STATUS_READY_VISIBLE:
                user_lang = get_user_language(user_id)
                issues = "\n".join(f"• {issue}" for issue in visibility.issues) if visibility.issues else ""
                if user_lang == "ru":
                    blocked_text = (
                        "⛔️ <b>Модель недоступна</b>\n\n"
                        f"Причина: <code>{visibility.status}</code>\n"
                        f"{issues or '• Причина не указана'}"
                    )
                else:
                    blocked_text = (
                        "⛔️ <b>Model unavailable</b>\n\n"
                        f"Reason: <code>{visibility.status}</code>\n"
                        f"{issues or '• No details available'}"
                    )
                await query.edit_message_text(blocked_text, parse_mode="HTML")
                return ConversationHandler.END

            session = ensure_session_cached(context, session_store, user_id, update_id)
            session_gen_type = _resolve_session_gen_type(session, None)
            model_gen_type = _derive_model_gen_type(model_spec)
            if session_gen_type and model_gen_type and session_gen_type != model_gen_type:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    update_id=update_id,
                    action="GEN_TYPE_AUTO_SWITCH_ON_SELECT",
                    action_path="select_model",
                    model_id=model_id,
                    gen_type=model_gen_type,
                    stage="MODEL_SELECT",
                    outcome="auto_switched",
                    param={
                        "previous_gen_type": session_gen_type,
                        "new_gen_type": model_gen_type,
                    },
                )
                session["active_gen_type"] = model_gen_type
                session["gen_type"] = model_gen_type

            mode_index = user_sessions.get(user_id, {}).get("mode_index")
            if model_spec.modes and len(model_spec.modes) > 1 and mode_index is None:
                user_lang = get_user_language(user_id)
                model_name = model_info.get("name", model_id)
                await query.edit_message_text(
                    _build_mode_selection_text(model_name, user_lang),
                    reply_markup=_build_mode_selection_keyboard(model_id, model_spec.modes, user_lang),
                    parse_mode="HTML",
                )
                return ConversationHandler.END

            input_params, required_params, forced_media_required = _apply_media_required_overrides(
                model_spec,
                model_spec.schema_properties or {},
            )
            
            # Check user balance and calculate available generations
            user_balance = await get_user_balance_async(user_id)
            is_admin = get_is_admin(user_id)
            
            # IMPORTANT: Use get_is_admin() if user_id is available to respect admin_user_mode
            is_admin_check = get_is_admin(user_id) if user_id is not None else is_admin
            
            # Check for free generations for free models
            sku_id = session.get("sku_id", "")
            is_free_available = await is_free_generation_available(user_id, sku_id)
            from app.pricing.free_policy import is_sku_free_daily
            remaining_free = (
                await get_user_free_generations_remaining(user_id)
                if is_sku_free_daily(sku_id)
                else 0
            )

            price_value, price_line, price_note = _resolve_price_for_display(
                session,
                model_id=model_id,
                mode_index=_resolve_mode_index(model_id, session.get("params", {}), user_id),
                gen_type=session.get("gen_type"),
                params=session.get("params", {}),
                user_lang=user_lang,
                is_admin=is_admin_check,
                correlation_id=correlation_id,
                update_id=update_id,
                action_path="model_select_info",
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            
            # Calculate how many generations available
            if is_admin:
                available_count = "Безлимит"
            elif is_free_available:
                # For free models with free generations, show free count
                available_count = f"🎁 {remaining_free} бесплатно в день"
            elif price_value is not None and user_balance >= price_value:
                available_count = int(user_balance / price_value)
            else:
                available_count = 0
            
            # Show model info with premium formatting
            model_name = model_info.get('name', model_id)
            model_emoji = model_info.get('emoji', '🤖')
            model_desc = model_info.get('description', '')
            model_category = model_info.get('category', 'Общее')
            
            # Check if new user for hints
            is_new = await is_new_user_async(user_id)
            
            model_info_text = (
                _build_model_card(model_spec, model_info, required_params, user_lang)
                + "\n\n"
                + "━━━━━━━━━━━━━━━━━━━━\n\n"
            )
            free_counter_line = ""
            try:
                free_counter_line = await get_free_counter_line(
                    user_id,
                    user_lang=user_lang,
                    correlation_id=correlation_id,
                    action_path="model_select_info",
                    sku_id=sku_id,
                )
            except Exception as exc:
                logger.warning("Failed to resolve free counter line: %s", exc)
            
            balance_label = "Баланс" if user_lang == "ru" else "Balance"
            balance_line = f"💵 <b>{balance_label}:</b> {format_rub_amount(user_balance)}"
            model_info_text += f"{balance_line}\n{price_line}\n"
            if price_note:
                model_info_text += f"{price_note}\n"
            
            # Add hint for new users
            if is_new and sku_id in FREE_TOOL_SKU_IDS:
                model_info_text += (
                    f"\n💡 <b>Отлично для начала!</b>\n"
                    f"Эта модель бесплатна для первых {FREE_GENERATIONS_PER_DAY} генераций в день.\n"
                    f"Просто опишите, что хотите создать, и нажмите \"Генерировать\"!\n\n"
                )
            
            # КРИТИЧНО: Всегда показываем цену для всех пользователей
            if is_admin:
                model_info_text += (
                    f"✅ <b>Доступ:</b> <b>Безлимит</b>\n"
                    f"👑 <b>Статус:</b> Администратор\n\n"
                )
            else:
                # Для обычных пользователей всегда показываем цену и баланс
                if is_free_available:
                    model_info_text += (
                        f"🎁 <b>Бесплатно:</b> {remaining_free}/{FREE_GENERATIONS_PER_DAY} в день\n"
                    )
                    if price_value is not None and user_balance >= price_value:
                        paid_count = int(user_balance / price_value)
                        model_info_text += f"💳 <b>Платных:</b> {paid_count} генераций\n"
                    model_info_text += "\n"
                elif available_count > 0:
                    model_info_text += (
                        f"✅ <b>Доступно:</b> {available_count} генераций\n"
                        "\n"
                    )
                else:
                    # Not enough balance - show warning
                    model_info_text += (
                        f"\n❌ <b>Недостаточно средств</b>\n\n"
                        f"{balance_line}\n"
                        f"{price_line}\n\n"
                        f"💡 Пополните баланс для генерации"
                    )

                    if free_counter_line:
                        model_info_text = _append_free_counter_text(model_info_text, free_counter_line)
                    
                    keyboard = [
                        [InlineKeyboardButton(t('btn_top_up_balance', lang=user_lang), callback_data="topup_balance")],
                        [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
                    ]
                    
                    await query.edit_message_text(
                        model_info_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return ConversationHandler.END

            if free_counter_line:
                model_info_text = _append_free_counter_text(model_info_text, free_counter_line)
            
            # Check balance before starting generation (but allow free generations)
            if not is_admin and not is_free_available and price_value is not None and user_balance < price_value:
                user_lang = get_user_language(user_id)
                keyboard = [
                    [InlineKeyboardButton(t('btn_top_up_balance', lang=user_lang), callback_data="topup_balance")],
                    [InlineKeyboardButton(t('btn_back_to_models', lang=user_lang), callback_data="back_to_menu")]
                ]
                
                needed = price_value - user_balance
                needed_str = format_rub_amount(needed)
                remaining_free = await get_user_free_generations_remaining(user_id)
                
                if user_lang == 'ru':
                    insufficient_msg = (
                        f"❌ <b>Недостаточно средств для генерации</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{balance_line}\n"
                        f"{price_line}\n"
                        f"❌ <b>Не хватает:</b> {needed_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>Что делать:</b>\n"
                        f"• Пополните баланс через кнопку ниже\n"
                    )
                    
                    if remaining_free > 0:
                        insufficient_msg += f"• Используйте бесплатные генерации бесплатных моделей ({remaining_free} доступно)\n"
                    
                    insufficient_msg += (
                        f"• Пригласите друга и получите бонусы\n\n"
                        f"🔄 После пополнения попробуйте генерацию снова."
                    )
                else:
                    insufficient_msg = (
                        f"❌ <b>Insufficient Funds for Generation</b>\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"{balance_line}\n"
                        f"{price_line}\n"
                        f"❌ <b>Need:</b> {needed_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>What to do:</b>\n"
                        f"• Top up balance via button below\n"
                    )
                    
                    if remaining_free > 0:
                        insufficient_msg += f"• Use free models generations ({remaining_free} available)\n"
                    
                    insufficient_msg += (
                        f"• Invite a friend and get bonuses\n\n"
                        f"🔄 After topping up, try generation again."
                    )
                
                await query.edit_message_text(
                    insufficient_msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
            
            # Store selected model
            logger.debug(f"🔥🔥🔥 SELECT_MODEL: Created new session for user_id={user_id}")
            session['model_id'] = model_id
            session['model_info'] = model_info
            session['active_model_id'] = model_id
            session['active_gen_type'] = model_gen_type or session_gen_type or _resolve_session_gen_type(None, model_spec)
            session['gen_type'] = session['active_gen_type']
            set_session_context(
                user_id,
                to_context=UI_CONTEXT_WIZARD,
                reason="select_model",
                active_gen_type=session.get("active_gen_type"),
                active_model_id=model_id,
                correlation_id=correlation_id,
                update_id=update_id,
                chat_id=query.message.chat_id if query.message else None,
            )
            logger.debug(f"🔥🔥🔥 SELECT_MODEL: Stored model in session: model_id={model_id}, user_id={user_id}, session_keys={list(session.keys())}")

            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
                update_id=update.update_id,
                action="MODEL_SELECT",
                action_path=build_action_path(data),
                model_id=model_id,
                gen_type=session.get("gen_type"),
                stage="MODEL_SELECT",
                outcome="selected",
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
                update_id=update.update_id,
                action="MODEL_SELECTED",
                action_path=build_action_path(data),
                model_id=model_id,
                gen_type=session.get("gen_type"),
                stage="MODEL_SELECT",
                outcome="selected",
            )

            logger.info(
                "✅ SELECT_MODEL: Using SSOT schema: count=%s, keys=%s, user_id=%s",
                len(input_params),
                list(input_params.keys()),
                user_id,
            )

            # Store session data
            session['params'] = {}
            session['properties'] = input_params
            session['required'] = required_params
            session['required_original'] = (model_spec.schema_required or []).copy()
            session['required_forced_media'] = forced_media_required
            session['current_param'] = None
            session['param_history'] = []
            session['model_spec'] = model_spec
            session['param_order'] = _build_param_order(input_params)
            session['ssot_conflicts'] = _detect_ssot_conflicts(model_spec, input_params)
            session['optional_media_params'] = []
            session['image_ref_prompt'] = False
            session['skipped_params'] = set()
            mode_index = _resolve_mode_index(model_id, session.get("params"), user_id)
            _update_price_quote(
                session,
                model_id=model_id,
                mode_index=mode_index,
                gen_type=session.get("gen_type"),
                params=session.get("params", {}),
                correlation_id=correlation_id,
                update_id=update_id,
                action_path="select_model",
                user_id=user_id,
                chat_id=query.message.chat_id if query.message else None,
                is_admin=is_admin_check,
            )
            model_info.setdefault("input_params", input_params)
            if model_spec.model_type in {"text_to_image", "text_to_video", "text_to_audio", "text_to_speech", "text"}:
                if "image_input" in input_params or "image_urls" in input_params:
                    session['image_ref_prompt'] = True
            if "SSOT_CONFLICT_TEXT_MODEL_REQUIRES_IMAGE" in session['ssot_conflicts']:
                media_param = _first_required_media_param(input_params)
                if media_param:
                    session['optional_media_params'] = [media_param]
                    session['required'] = [
                        name for name in session['required'] if name != media_param
                    ]
            if session['ssot_conflicts']:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    update_id=update.update_id,
                    action="SSOT_CONFLICT",
                    action_path="select_model",
                    model_id=model_id,
                    outcome="detected",
                    error_code="SSOT_CONFLICT_DETECTED",
                    fix_hint="Проверьте модельный SSOT на противоречия.",
                    param={"conflicts": session['ssot_conflicts']},
                )
            if forced_media_required:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=query.message.chat_id if query.message else None,
                    update_id=update.update_id,
                    action="MEDIA_REQUIRED_OVERRIDE",
                    action_path="select_model",
                    model_id=model_id,
                    gen_type=session.get("gen_type"),
                    stage="MODEL_SELECT",
                    outcome="forced",
                    param={"forced_media": forced_media_required},
                )
            logger.info(
                "✅ SELECT_MODEL: Parameter order determined: %s, user_id=%s",
                session['param_order'],
                user_id,
            )

            if not input_params:
                return await send_confirmation_message(update, context, user_id, source="select_model")

            next_param_result = await start_next_parameter(update, context, user_id)
            if next_param_result is None:
                return await send_confirmation_message(update, context, user_id, source="select_model")
            return next_param_result
        
        # Handle confirm_generate as fallback (in case state didn't switch properly)
        if data == "confirm_generate":
            # Answer callback immediately
            try:
                await query.answer()
            except:
                pass
            
            logger.info(f"confirm_generate callback received in button_callback (fallback)")
            # Call confirm_generation function directly
            # 🔴 API CALL: confirm_generation может вызывать KIE API
            try:
                await confirm_generation(update, context)
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"❌❌❌ ERROR in confirm_generation fallback: {e}", exc_info=True)
                try:
                    user_lang = get_user_language(user_id) if user_id else 'ru'
                    error_msg = "Ошибка сервера, попробуйте позже" if user_lang == 'ru' else "Server error, please try later"
                    await query.answer(error_msg, show_alert=True)
                except Exception:
                    pass
                return ConversationHandler.END
    
    # If we get here and no handler matched, log and return END
    except Exception as e:
        logger.error(f"Error in button_callback for data '{data}': {e}", exc_info=True)
        try:
            correlation_id = None
            if context and getattr(context, "user_data", None) is not None:
                if context.user_data.get("correlation_update_id") == update_id:
                    correlation_id = context.user_data.get("correlation_id")
                if not correlation_id:
                    correlation_id = get_correlation_id(update_id, user_id)
                    context.user_data["correlation_id"] = correlation_id
                    context.user_data["correlation_update_id"] = update_id
            else:
                correlation_id = get_correlation_id(update_id, user_id)

            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=query.message.chat_id if query and query.message else None,
                update_id=update_id,
                action="CALLBACK",
                action_path=build_action_path(data),
                model_id=user_sessions.get(user_id, {}).get("model_id") if user_id else None,
                gen_type=user_sessions.get(user_id, {}).get("gen_type") if user_id else None,
                stage="router",
                waiting_for=user_sessions.get(user_id, {}).get("waiting_for") if user_id else None,
                param=user_sessions.get(user_id, {}).get("current_param") if user_id else None,
                outcome="exception",
                duration_ms=int((time.time() - start_time) * 1000),
                error_code="UX_CALLBACK_EXCEPTION",
                fix_hint="check is_admin_user/calc price",
            )
            trace_error(
                correlation_id,
                "INTERNAL_EXCEPTION",
                ERROR_CATALOG["INTERNAL_EXCEPTION"],
                e,
                callback_data=data,
                action_path=build_action_path(data),
            )
            user_lang = get_user_language(user_id) if user_id else "ru"
            error_text = (
                "⚠️ Сбой на этапе router, уже записал лог.\n"
                f"ID: {correlation_id or 'corr-na-na'}"
            ) if user_lang == "ru" else (
                "⚠️ Failure at stage router, logs captured.\n"
                f"ID: {correlation_id or 'corr-na-na'}"
            )
            if query and query.message:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=error_text,
                )
        except Exception as structured_log_error:
            logger.warning(
                "STRUCTURED_LOG error on callback exception: %s",
                structured_log_error,
                exc_info=True,
            )
        try:
            await query.answer(
                "❌ Произошла ошибка. Обновил меню — попробуйте снова.",
                show_alert=True,
            )
        except Exception:
            pass
        await show_main_menu(update, context, source="callback_exception")
        return ConversationHandler.END
    
    # 🔴 FALLBACK - универсальный обработчик для необработанных callback_data
    # Это защита от сбоев при обновлениях - если какая-то кнопка не обработана,
    # пользователь получит понятное сообщение вместо ошибки
    # ВАЖНО: Этот код выполняется ТОЛЬКО если ни один обработчик выше не сработал
    
    logger.warning(f"⚠️ Unhandled callback_data: '{data}' from user {user_id}")
    user_lang = "ru"
    try:
        correlation_id = ensure_correlation_id(update, context)
        user_lang = get_user_language(user_id) if user_id else "ru"
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=query.message.chat_id if query and query.message else None,
            update_id=update.update_id,
            action="UNKNOWN_CALLBACK",
            action_path=build_action_path(data),
            stage="UI_ROUTER",
            outcome="unknown_callback",
            error_code="UI_UNKNOWN_CALLBACK",
            fix_hint="register_callback_handler_or_validate_callback_data",
        )
    except Exception as structured_log_error:
        logger.warning("STRUCTURED_LOG unknown callback failed: %s", structured_log_error, exc_info=True)
    
    # Всегда отвечаем на callback, даже если не знаем что делать
    try:
        fallback_text = (
            "Команда устарела, обновляю меню." if user_lang == "ru" else "Command outdated, refreshing menu."
        )
        await query.answer(fallback_text, show_alert=False)
    except Exception:
        try:
            if context and query and query.id:
                await context.bot.answer_callback_query(query.id, text=fallback_text, show_alert=False)
        except Exception:
            pass
    await show_main_menu(update, context, source="unknown_callback")
    return ConversationHandler.END


def _get_chat_id_from_update(update: Update) -> int | None:
    if hasattr(update, 'effective_chat') and update.effective_chat:
        return update.effective_chat.id
    if hasattr(update, 'message') and update.message:
        return update.message.chat_id
    if hasattr(update, 'callback_query') and update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat_id
    return None


def _get_step_info(session: dict, param_name: str, user_lang: str) -> str:
    param_order = session.get('param_order', [])
    if param_name in param_order:
        step_index = param_order.index(param_name) + 1
        total_steps = len(param_order)
        if user_lang == 'en':
            return f"Step {step_index}/{total_steps}"
        return f"Шаг {step_index}/{total_steps}"
    return ""


def _get_param_example(param_name: str, param_info: dict, user_lang: str, enum_values: list | None = None) -> str:
    example = param_info.get('example')
    if not example and enum_values:
        example = enum_values[0]
    if not example and param_name == "prompt":
        example = "A cinematic night cityscape with neon lights" if user_lang == 'en' else "Фотореалистичный киберпанк-город ночью"
    if not example:
        return ""
    prefix = "Example" if user_lang == 'en' else "Пример"
    return f"{prefix}: {example}"


def _get_param_format_hint(param_type: str, enum_values: list | None, user_lang: str) -> str:
    if enum_values:
        return "Format: choose from list" if user_lang == 'en' else "Формат: выберите значение из списка"
    if param_type == "boolean":
        return "Format: yes/no" if user_lang == 'en' else "Формат: да/нет"
    return "Format: text" if user_lang == 'en' else "Формат: текст"


def _humanize_param_name(param_name: str, user_lang: str) -> str:
    fallback = param_name.replace("_", " ").strip()
    if user_lang != "ru":
        return fallback.title() if fallback else param_name
    ru_map = {
        "prompt": "Текст запроса",
        "text": "Текст запроса",
        "image_size": "Размер изображения",
        "aspect_ratio": "Соотношение сторон",
        "guidance_scale": "Сила соответствия",
        "enable_safety_checker": "Фильтр безопасности",
        "image_urls": "Изображение",
        "image_input": "Изображение",
        "audio_url": "Аудио",
        "audio_input": "Аудио",
        "video_url": "Видео",
        "video_input": "Видео",
    }
    return ru_map.get(param_name, fallback.capitalize() if fallback else param_name)


def _short_correlation_suffix(correlation_id: Optional[str]) -> str:
    if not correlation_id:
        return "corr-na"
    return correlation_id[-6:]


def _build_default_mode_label(index: int, user_lang: str) -> str:
    if user_lang == "ru":
        fallbacks = ["Стандартный", "Высокое качество", "Быстрый", "Дополнительный"]
    else:
        fallbacks = ["Standard", "High quality", "Fast", "Extra"]
    if index < len(fallbacks):
        return fallbacks[index]
    return fallbacks[-1]


def _resolve_mode_label(mode: Any, index: int, user_lang: str) -> str:
    title = getattr(mode, "title_ru", None)
    hint = getattr(mode, "short_hint_ru", None)
    if user_lang != "ru":
        title = getattr(mode, "notes", None) or getattr(mode, "title_ru", None)
        hint = getattr(mode, "notes", None)
    title = title or _build_default_mode_label(index, user_lang)
    if hint:
        return f"{title} · {hint}"
    return title


def _summarize_required_inputs(
    required_params: List[str],
    properties: Dict[str, Any],
    user_lang: str,
) -> str:
    kinds: List[str] = []
    for param in required_params:
        if param in {"prompt", "text"}:
            kinds.append("text")
            continue
        media_kind = _get_media_kind(param)
        if media_kind:
            kinds.append(media_kind)
    if not kinds:
        if "prompt" in properties or "text" in properties:
            kinds.append("text")
    labels_ru = {
        "text": "Текст",
        "image": "Картинка",
        "video": "Видео",
        "audio": "Аудио",
        "document": "Файл",
    }
    labels_en = {
        "text": "Text",
        "image": "Image",
        "video": "Video",
        "audio": "Audio",
        "document": "File",
    }
    labels = labels_ru if user_lang == "ru" else labels_en
    ordered = []
    for kind in ["text", "image", "video", "audio", "document"]:
        if kind in kinds and kind not in ordered:
            ordered.append(kind)
    if not ordered:
        return ""
    if user_lang == "ru":
        return "Входы: " + ", ".join(labels[k] for k in ordered)
    return "Inputs: " + ", ".join(labels[k] for k in ordered)


def _resolve_output_type_label(model_spec: "ModelSpec", user_lang: str) -> str:
    output_ru = model_spec.output_type_ru or ""
    output_media = (model_spec.output_media_type or "").lower()
    fallback_ru = {
        "image": "Изображение",
        "video": "Видео",
        "audio": "Аудио",
        "text": "Текст",
        "document": "Файл",
    }.get(output_media, "Файл")
    fallback_en = {
        "image": "Image",
        "video": "Video",
        "audio": "Audio",
        "text": "Text",
        "document": "File",
    }.get(output_media, "File")
    if user_lang == "ru":
        return output_ru or fallback_ru
    return fallback_en


def _build_model_card(
    model_spec: "ModelSpec",
    model_info: Dict[str, Any],
    required_params: List[str],
    user_lang: str,
) -> str:
    name = model_info.get("name") or model_spec.title_ru or model_spec.id
    description_ru = model_spec.description_ru or "Генерация результата по вашему запросу."
    inputs_line = _summarize_required_inputs(required_params, model_spec.schema_properties or {}, user_lang)
    output_label = _resolve_output_type_label(model_spec, user_lang)
    if user_lang == "ru":
        usage_line = "Как пользоваться: заполните обязательные входы и нажмите «Сгенерировать»."
        card_parts = [
            f"🪪 <b>Карточка модели</b>",
            f"🤖 <b>{name}</b>",
            f"📝 {description_ru}",
        ]
        if inputs_line:
            card_parts.append(f"📥 {inputs_line}")
        card_parts.append(f"📤 Результат: {output_label}")
        card_parts.append(f"💡 {usage_line}")
        return "\n".join(card_parts)
    usage_line = "How to use: provide required inputs and tap “Generate”."
    card_parts = [
        f"🪪 <b>Model card</b>",
        f"🤖 <b>{name}</b>",
        f"📝 {description_ru}",
    ]
    if inputs_line:
        card_parts.append(f"📥 {inputs_line}")
    card_parts.append(f"📤 Output: {output_label}")
    card_parts.append(f"💡 {usage_line}")
    return "\n".join(card_parts)


def _record_param_history(session: dict, param_name: str) -> None:
    history = session.setdefault('param_history', [])
    if not history or history[-1] != param_name:
        history.append(param_name)


def _get_settings_label(user_lang: str) -> str:
    return "⚙️ Параметры" if user_lang == 'ru' else "⚙️ Parameters"


def _get_reset_step_label(user_lang: str) -> str:
    return "🔄 Сбросить шаг" if user_lang == 'ru' else "🔄 Reset step"


def _format_required_label(is_optional: bool, user_lang: str) -> str:
    if user_lang == "ru":
        return "✅ Обязательный" if not is_optional else "⚪️ Опциональный"
    return "✅ Required" if not is_optional else "⚪️ Optional"


def _media_first_instruction(user_lang: str) -> str:
    if user_lang == "ru":
        return "📌 Сначала загрузите файл, затем сможете ввести текст и параметры."
    return "📌 Upload the file first, then you can enter text and parameters."


def _get_param_price_variants(
    model_id: str,
    param_name: str,
    current_params: dict,
) -> tuple[bool, dict[str, float]]:
    try:
        from app.pricing.price_ssot import list_model_skus, list_variants_with_prices
    except Exception:
        return False, {}
    skus = list_model_skus(model_id)
    if not any(param_name in sku.params for sku in skus):
        return False, {}
    variants = list_variants_with_prices(model_id, param_name, current_params or {})
    return True, {value: float(price) for value, price in variants}


def _format_param_price_rows(values: list[str], price_map: dict[str, float]) -> list[str]:
    from app.pricing.price_resolver import format_price_rub

    rows: list[str] = []
    for value in values:
        price_value = price_map.get(str(value))
        if price_value is None:
            continue
        rows.append(f"{value} — {format_price_rub(price_value)}₽")
    return rows


def build_enum_keyboard_with_prices(
    param_name: str,
    enum_values: list,
    is_optional: bool,
    default_value: str | None,
    user_lang: str,
    model_id: str,
    current_params: dict,
) -> tuple[list[list[InlineKeyboardButton]] | None, str, list]:
    price_depends, param_price_map = _get_param_price_variants(
        model_id,
        param_name,
        current_params or {},
    )
    display_values = list(enum_values)
    if price_depends:
        display_values = [value for value in enum_values if str(value) in param_price_map]
        if not display_values:
            return None, "", []

    price_variants_text = ""
    if price_depends:
        price_rows = _format_param_price_rows([str(value) for value in display_values], param_price_map)
        price_variants_text = "\n".join(price_rows)

    keyboard = []
    if price_depends:
        from app.pricing.price_resolver import format_price_rub
    for i in range(0, len(display_values), 2):
        first_value = display_values[i]
        first_label = str(first_value)
        if price_depends:
            price_value = param_price_map.get(str(first_value))
            if price_value is not None:
                first_label = f"{first_label} — {format_price_rub(price_value)}₽"
        row = [
            InlineKeyboardButton(first_label, callback_data=f"set_param:{param_name}:{first_value}")
        ]
        if i + 1 < len(display_values):
            second_value = display_values[i + 1]
            second_label = str(second_value)
            if price_depends:
                price_value = param_price_map.get(str(second_value))
                if price_value is not None:
                    second_label = f"{second_label} — {format_price_rub(price_value)}₽"
            row.append(InlineKeyboardButton(second_label, callback_data=f"set_param:{param_name}:{second_value}"))
        keyboard.append(row)

    if is_optional:
        if default_value is not None and default_value in display_values:
            default_text = (
                f"⏭️ Использовать по умолчанию ({default_value})"
                if user_lang == "ru"
                else f"⏭️ Use default ({default_value})"
            )
            keyboard.append([InlineKeyboardButton(default_text, callback_data=f"set_param:{param_name}:{default_value}")])
        elif default_value is None:
            skip_text = "⏭️ Пропустить (auto)" if user_lang == "ru" else "⏭️ Skip (auto)"
            keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])

    return keyboard, price_variants_text, display_values


async def prompt_for_specific_param(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    param_name: str,
    source: str = "manual_edit",
) -> int | None:
    if user_id not in user_sessions:
        logger.error("prompt_for_specific_param: session not found for user_id=%s", user_id)
        return None
    session = user_sessions[user_id]
    properties = session.get('properties', {})
    param_info = properties.get(param_name, {})
    param_type = param_info.get('type', 'string')
    enum_values = _normalize_enum_values(param_info)
    user_lang = get_user_language(user_id)
    step_info = _get_step_info(session, param_name, user_lang)
    step_prefix = f"{step_info}: " if step_info else ""
    is_optional = not param_info.get('required', False)
    default_value = param_info.get('default')
    format_hint = _get_param_format_hint(param_type, enum_values, user_lang)
    example_hint = _get_param_example(param_name, param_info, user_lang, enum_values)
    required_label = _format_required_label(is_optional, user_lang)
    chat_id = _get_chat_id_from_update(update)
    correlation_id = ensure_correlation_id(update, context)
    free_counter_line = await _resolve_free_counter_line(
        user_id,
        user_lang,
        correlation_id,
        action_path=f"param_prompt:{param_name}",
        sku_id=session.get("sku_id"),
    )
    model_id = session.get("model_id", "")
    mode_index = _resolve_mode_index(model_id, session.get("params", {}), user_id)
    price_line = _build_current_price_line(
        session,
        user_lang=user_lang,
        model_id=model_id,
        mode_index=mode_index,
        gen_type=session.get("gen_type"),
        params=session.get("params", {}),
        correlation_id=correlation_id,
        update_id=update.update_id,
        action_path=f"param_prompt:{param_name}",
        user_id=user_id,
        chat_id=chat_id,
        is_admin=get_is_admin(user_id),
    )
    price_depends, param_price_map = _get_param_price_variants(
        model_id,
        param_name,
        session.get("params", {}),
    )

    logger.info(
        "🧭 PARAM_PROMPT: action_path=%s model_id=%s param=%s waiting_for=%s current_param=%s outcome=prompt",
        source,
        session.get('model_id'),
        param_name,
        session.get('waiting_for'),
        session.get('current_param'),
    )

    if not chat_id:
        logger.error("Cannot determine chat_id in prompt_for_specific_param")
        return None

    if param_name in ['image_input', 'image_urls', 'image', 'mask_input', 'reference_image_input']:
        old_waiting_for = session.get("waiting_for")
        session['current_param'] = param_name
        session['waiting_for'] = param_name
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="WIZARD_TRANSITION",
            action_path="prompt_for_specific_param",
            model_id=session.get("model_id"),
            param={"from": old_waiting_for, "to": param_name, "reason": "image_prompt"},
            outcome="updated",
        )
        if param_name not in session:
            session[param_name] = []
        skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
        keyboard = [
            [
                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
            ]
        ]
        if is_optional:
            keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
        keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
        keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
        instruction_line = _media_first_instruction(user_lang) if not is_optional else ""
        prompt_text = (
            f"📷 <b>{step_prefix}{param_name.replace('_', ' ').title()}</b>\n\n"
            f"{param_info.get('description', '')}\n\n"
            f"💡 {format_hint}\n"
            f"{required_label}\n"
        )
        if instruction_line:
            prompt_text += f"{instruction_line}\n"
        if example_hint:
            prompt_text += f"🧪 {example_hint}\n"
        prompt_text += "📏 Максимальный размер: 10 MB" if user_lang == 'ru' else "📏 Max size: 10 MB"
        prompt_text += f"\n\n{price_line}"
        prompt_text = _append_free_counter_text(prompt_text, free_counter_line)
        await context.bot.send_message(
            chat_id=chat_id,
            text=prompt_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="PARAM_PROMPTED",
            action_path="prompt_for_specific_param",
            model_id=session.get("model_id"),
            outcome="shown",
            param={"param_name": param_name, "media_kind": "image"},
        )
        return INPUTTING_PARAMS

    if param_name in ['audio_url', 'audio_input']:
        old_waiting_for = session.get("waiting_for")
        session['current_param'] = param_name
        session['waiting_for'] = param_name
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="WIZARD_TRANSITION",
            action_path="prompt_for_specific_param",
            model_id=session.get("model_id"),
            param={"from": old_waiting_for, "to": param_name, "reason": "audio_prompt"},
            outcome="updated",
        )
        skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
        keyboard = [
            [
                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
            ]
        ]
        if is_optional:
            keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
        keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
        keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
        instruction_line = _media_first_instruction(user_lang) if not is_optional else ""
        prompt_text = (
            f"🎤 <b>{step_prefix}{param_name.replace('_', ' ').title()}</b>\n\n"
            f"{param_info.get('description', '')}\n\n"
            f"💡 {format_hint}\n"
            f"{required_label}\n"
        )
        if instruction_line:
            prompt_text += f"{instruction_line}\n"
        if example_hint:
            prompt_text += f"🧪 {example_hint}\n"
        prompt_text += (
            "Максимальный размер: 200 MB" if user_lang == 'ru' else "Max size: 200 MB"
        )
        prompt_text += f"\n\n{price_line}"
        prompt_text = _append_free_counter_text(prompt_text, free_counter_line)
        await context.bot.send_message(
            chat_id=chat_id,
            text=prompt_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="PARAM_PROMPTED",
            action_path="prompt_for_specific_param",
            model_id=session.get("model_id"),
            outcome="shown",
            param={"param_name": param_name, "media_kind": "audio"},
        )
        return INPUTTING_PARAMS

    if param_type == 'boolean':
        true_label = "✅ Да (true)"
        false_label = "❌ Нет (false)"
        if price_depends and param_price_map:
            true_price = param_price_map.get("true")
            false_price = param_price_map.get("false")
            from app.pricing.price_resolver import format_price_rub
            if true_price is not None:
                true_label = f"{true_label} — {format_price_rub(true_price)}₽"
            if false_price is not None:
                false_label = f"{false_label} — {format_price_rub(false_price)}₽"
        keyboard = [
            [
                InlineKeyboardButton(true_label, callback_data=f"set_param:{param_name}:true"),
                InlineKeyboardButton(false_label, callback_data=f"set_param:{param_name}:false")
            ]
        ]
        if is_optional:
            if default_value is None:
                skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
                keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
            else:
                skip_text = "⏭️ Использовать по умолчанию" if user_lang == 'ru' else "⏭️ Use default"
                keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{str(default_value).lower()}")])
        keyboard.append([
            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
        ])
        keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
        keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
        description = param_info.get('description', '')
        detail_lines = [format_hint, required_label]
        if example_hint:
            detail_lines.append(example_hint)
        detail_text = "\n".join(detail_lines)
        price_rows = []
        if price_depends:
            price_rows = _format_param_price_rows(["true", "false"], param_price_map)
            if not price_rows:
                blocked_text = (
                    "⛔️ <b>Нет цены для выбранного параметра</b>"
                    if user_lang == "ru"
                    else "⛔️ <b>No price for the selected parameter</b>"
                )
                blocked_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu"),
                    ]
                ])
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=blocked_text,
                    reply_markup=blocked_keyboard,
                    parse_mode="HTML",
                )
                return INPUTTING_PARAMS
        price_variants_text = "\n".join(price_rows)
        detail_block = (
            f"📝 <b>{step_prefix}{param_name.replace('_', ' ').title()}</b>\n\n"
            f"{description}\n\n"
            f"💡 {detail_text}\n\n"
        )
        if price_variants_text:
            detail_block += f"{price_variants_text}\n\n"
        detail_block += f"{price_line}"
        message_text = _append_free_counter_text(detail_block, free_counter_line)
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="PARAM_PROMPTED",
            action_path="prompt_for_specific_param",
            model_id=session.get("model_id"),
            outcome="shown",
            param={"param_name": param_name, "type": param_type},
        )
        session['waiting_for'] = param_name
        session['current_param'] = param_name
        return INPUTTING_PARAMS

    if enum_values:
        keyboard, price_variants_text, display_values = build_enum_keyboard_with_prices(
            param_name=param_name,
            enum_values=enum_values,
            is_optional=is_optional,
            default_value=default_value,
            user_lang=user_lang,
            model_id=model_id,
            current_params=session.get("params", {}),
        )
        if not display_values:
            blocked_text = (
                "⛔️ <b>Нет цены для доступных вариантов</b>"
                if user_lang == "ru"
                else "⛔️ <b>No price for available variants</b>"
            )
            blocked_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                    InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu"),
                ]
            ])
            await context.bot.send_message(
                chat_id=chat_id,
                text=blocked_text,
                reply_markup=blocked_keyboard,
                parse_mode="HTML",
            )
            return INPUTTING_PARAMS
        keyboard.append([
            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
        ])
        keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
        keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
        description = param_info.get('description', '')
        detail_lines = [format_hint, required_label]
        if example_hint:
            detail_lines.append(example_hint)
        detail_text = "\n".join(detail_lines)
        detail_block = (
            f"📝 <b>{step_prefix}{param_name.replace('_', ' ').title()}</b>\n\n"
            f"{description}\n\n"
            f"💡 {detail_text}\n\n"
        )
        if price_variants_text:
            detail_block += f"{price_variants_text}\n\n"
        detail_block += f"{price_line}"
        message_text = _append_free_counter_text(detail_block, free_counter_line)
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="PARAM_PROMPTED",
            action_path="prompt_for_specific_param",
            model_id=session.get("model_id"),
            outcome="shown",
            param={"param_name": param_name, "type": param_type},
        )
        session['waiting_for'] = param_name
        session['current_param'] = param_name
        return INPUTTING_PARAMS

    keyboard = []
    if is_optional:
        if default_value:
            default_text = f" (по умолчанию: {default_value})" if user_lang == 'ru' else f" (default: {default_value})"
            keyboard.append([InlineKeyboardButton(f"⏭️ Использовать по умолчанию{default_text}", callback_data=f"set_param:{param_name}:{default_value}")])
        else:
            skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
            keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
    keyboard.append([
        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
    ])
    keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
    keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
    description = param_info.get('description', '')
    detail_lines = [format_hint, required_label]
    if example_hint:
        detail_lines.append(example_hint)
    detail_text = "\n".join(detail_lines)
    message_text = _append_free_counter_text(
        (
            f"📝 <b>{step_prefix}{param_name.replace('_', ' ').title()}</b>\n\n"
            f"{description}\n\n"
            f"💡 {detail_text}\n\n"
            f"{price_line}"
        ),
        free_counter_line,
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        action="PARAM_PROMPTED",
        action_path="prompt_for_specific_param",
        model_id=session.get("model_id"),
        outcome="shown",
        param={"param_name": param_name, "type": param_type},
    )
    session['waiting_for'] = param_name
    session['current_param'] = param_name
    return INPUTTING_PARAMS


async def send_confirmation_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    source: str = "confirmation",
) -> int | None:
    if user_id not in user_sessions:
        return None
    correlation_id = ensure_correlation_id(update, context)
    session = user_sessions[user_id]
    model_id = session.get('model_id', '')
    model_name = session.get('model_info', {}).get('name', 'Unknown')
    params = session.get('params', {})
    params_text = "\n".join([f"  • {k}: {str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in params.items()])
    user_lang = get_user_language(user_id)
    is_admin_user = get_is_admin(user_id)
    sku_id = session.get("sku_id", "")
    is_free = await is_free_generation_available(user_id, sku_id)
    mode_index = _resolve_mode_index(model_id, params, user_id)
    price_quote = _update_price_quote(
        session,
        model_id=model_id,
        mode_index=mode_index,
        gen_type=session.get("gen_type"),
        params=params,
        correlation_id=correlation_id,
        update_id=update.update_id,
        action_path="confirm_screen",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        is_admin=is_admin_user,
    )
    if is_free:
        price_display = "0.00"
    elif price_quote:
        from app.pricing.price_resolver import format_price_rub as format_price_value

        price_display = format_price_value(price_quote.get("price_rub"))
    else:
        price_display = None
    if not is_free and not price_display:
        blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
        if update.callback_query:
            await update.callback_query.edit_message_text(blocked_text, parse_mode="HTML")
        elif update.message:
            await update.message.reply_text(blocked_text, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=user_id, text=blocked_text, parse_mode="HTML")
        return ConversationHandler.END
    price_str = price_display
    price_line = (
        f"Цена по прайсу: {price_display} ₽"
        if price_display and user_lang == "ru"
        else (
            f"Price (RUB): {price_display} ₽"
            if price_display
            else ("Цена: уточняется" if user_lang == "ru" else "Price: уточняется")
        )
    )
    if is_free:
        remaining = await get_user_free_generations_remaining(user_id)
        price_info = (
            f"🎁 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ!</b>\nОсталось бесплатных: {remaining}/{FREE_GENERATIONS_PER_DAY} в день\n{price_line}"
            if user_lang == 'ru'
            else f"🎁 <b>FREE GENERATION!</b>\nRemaining free: {remaining}/{FREE_GENERATIONS_PER_DAY} per day\n{price_line}"
        )
    elif not price_display:
        price_info = price_line
    else:
        price_info = (
            f"💰 <b>{price_line}</b>"
            if user_lang == 'ru'
            else f"💰 <b>{price_line}</b>"
        )

    free_counter_line = ""
    sku_id = session.get("sku_id")
    try:
        free_counter_line = await get_free_counter_line(
            user_id,
            user_lang=user_lang,
            correlation_id=correlation_id,
            action_path="confirm_screen",
            sku_id=sku_id,
        )
    except Exception as exc:
        logger.warning("Failed to resolve free counter line: %s", exc)

    settings_label = _get_settings_label(user_lang)
    keyboard = [
        [InlineKeyboardButton(settings_label, callback_data="show_parameters")],
        [
            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
        ],
        [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
    ]
    if price_str:
        keyboard.insert(0, [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")])

    confirm_msg = _append_free_counter_text(
        (
            f"📋 <b>Подтверждение генерации</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 <b>Модель:</b> {model_name}\n\n"
            f"⚙️ <b>Параметры:</b>\n{params_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{price_info}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 <b>Что будет дальше:</b>\n"
            f"• Генерация начнется после подтверждения\n"
            f"• Результат придет автоматически\n"
            f"• Обычно это занимает от 10 секунд до 2 минут\n\n"
            f"🚀 <b>Готовы начать?</b>"
            if user_lang == 'ru'
            else (
                f"📋 <b>Generation Confirmation</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🤖 <b>Model:</b> {model_name}\n\n"
                f"⚙️ <b>Parameters:</b>\n{params_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{price_info}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💡 <b>What's next:</b>\n"
                f"• Generation will start after confirmation\n"
                f"• Result will come automatically\n"
                f"• Usually takes from 10 seconds to 2 minutes\n\n"
                f"🚀 <b>Ready to start?</b>"
            )
        ),
        free_counter_line,
    )

    logger.info(
        "✅ CONFIRMATION: action_path=%s model_id=%s waiting_for=%s current_param=%s outcome=sent",
        source,
        model_id,
        session.get('waiting_for'),
        session.get('current_param'),
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            confirm_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    elif update.message:
        await update.message.reply_text(
            confirm_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=confirm_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    return CONFIRMING_GENERATION


async def start_next_parameter(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Start input for next parameter."""
    if user_id not in user_sessions:
        logger.error(f"User {user_id} session not found in start_next_parameter")
        return None
    session = user_sessions[user_id]
    properties = session.get('properties', {})
    params = session.get('params', {})
    required = session.get('required', [])
    model_id = session.get('model_id', '')
    sku_id = session.get("sku_id")
    user_lang = get_user_language(user_id)
    correlation_id = ensure_correlation_id(update, context)
    mode_index = _resolve_mode_index(model_id, params, user_id)
    price_line = _build_current_price_line(
        session,
        user_lang=user_lang,
        model_id=model_id,
        mode_index=mode_index,
        gen_type=session.get("gen_type"),
        params=params,
        correlation_id=correlation_id,
        update_id=update.update_id,
        action_path="start_next_parameter",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        is_admin=get_is_admin(user_id),
    )

    logger.info(
        "🧭🧭🧭 START_NEXT_PARAMETER: user_id=%s model_id=%s required=%s params_keys=%s properties_keys=%s session_keys=%s",
        user_id,
        model_id,
        required[:20],
        list(params.keys())[:20],
        list(properties.keys())[:20],
        list(session.keys())[:20],
    )
    trace_event(
        "info",
        correlation_id,
        event="TRACE_IN",
        stage="SESSION_LOAD",
        update_type="message" if update.message else "callback",
        action="PARAM_NEXT",
        action_path="start_next_parameter",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        session_exists=True,
        model_id=model_id,
        waiting_for=session.get("waiting_for"),
        current_param=session.get("current_param"),
        params_keys=list(params.keys())[:15],
        required=required[:15],
        param_order=session.get("param_order")[:15] if session.get("param_order") else None,
    )

    param_order = session.get("param_order") or _build_param_order(properties)
    session["param_order"] = param_order
    required_order = [param_name for param_name in param_order if param_name in required]
    if not required_order:
        required_order = [param_name for param_name in required if param_name in properties]

    for param_name in required_order:
        if param_name in params:
            continue

        param_info = properties.get(param_name, {})
        param_type = param_info.get('type', 'string')
        enum_values = _normalize_enum_values(param_info)
        is_optional = not param_info.get('required', False)
        if param_name in required:
            is_optional = False
        required_label = _format_required_label(is_optional, user_lang)
        session['current_param'] = param_name
        media_kind = _get_media_kind(param_name)
        reason = "missing_required"
        if enum_values:
            reason = "enum_buttons"
        trace_event(
            "info",
            correlation_id,
            event="TRACE_IN",
            stage="STATE_VALIDATE",
            update_type="message" if update.message else "callback",
            action="PARAM_SELECT",
            action_path="start_next_parameter",
            user_id=user_id,
            chat_id=update.effective_chat.id if update.effective_chat else None,
            list_to_check=param_order[:15],
            selected_param=param_name,
            reason=reason,
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=update.effective_chat.id if update.effective_chat else None,
            action="PARAM_SELECT",
            action_path="start_next_parameter",
            param={"param_name": param_name, "reason": reason},
            outcome="selected",
        )

        chat_id = None
        if hasattr(update, 'effective_chat') and update.effective_chat:
            chat_id = update.effective_chat.id
        elif hasattr(update, 'message') and update.message:
            chat_id = update.message.chat_id
        elif hasattr(update, 'callback_query') and update.callback_query and update.callback_query.message:
            chat_id = update.callback_query.message.chat_id

        if not chat_id:
            logger.error("Cannot determine chat_id in start_next_parameter")
            return None

        if media_kind:
            old_waiting_for = session.get("waiting_for")
            session['waiting_for'] = param_name
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="WIZARD_TRANSITION",
                action_path="start_next_parameter",
                model_id=model_id,
                param={
                    "from": old_waiting_for,
                    "to": param_name,
                    "reason": "media_input",
                },
                outcome="updated",
            )
            param_desc = param_info.get('description', '')
            step_info = _get_step_info(session, param_name, user_lang)
            step_prefix = f"{step_info}: " if step_info else ""
            format_hint = _get_param_format_hint(param_type, enum_values, user_lang)
            example_hint = _get_param_example(param_name, param_info, user_lang, enum_values)
            example_line = f"🧪 {example_hint}\n" if example_hint else ""
            free_counter_line = await _resolve_free_counter_line(
                user_id,
                user_lang,
                correlation_id,
                action_path=f"param_prompt:{param_name}",
                sku_id=sku_id,
            )
            title_map = {
                "image": "Загрузите изображение",
                "video": "Загрузите видео",
                "audio": "Загрузите аудио",
            }
            title = title_map.get(media_kind, "Загрузите файл")
            instruction_line = _media_first_instruction(user_lang) if not is_optional else ""
            prompt_text = (
                f"📥 <b>{step_prefix}{title}</b>\n\n"
                f"{param_desc}\n\n"
                f"💡 {format_hint}\n"
                f"{required_label}\n"
            )
            if instruction_line:
                prompt_text += f"{instruction_line}\n"
            if example_hint:
                prompt_text += f"{example_line}"
            prompt_text += (
                f"📏 Максимальный размер: 30 MB\n\n"
                f"{price_line}"
            )
            prompt_text = _append_free_counter_text(prompt_text, free_counter_line)
            keyboard = [[
                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
            ]]
            if is_optional:
                skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
                keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
            keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
            keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])

            await context.bot.send_message(
                chat_id=chat_id,
                text=prompt_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="PARAM_PROMPTED",
                action_path="start_next_parameter",
                model_id=model_id,
                outcome="shown",
                param={"param_name": param_name, "media_kind": media_kind},
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="UX_STEP_PROMPTED",
                action_path="start_next_parameter",
                model_id=model_id,
                gen_type=session.get("gen_type"),
                waiting_for=param_name,
                outcome="shown",
                param={
                    "param_name": param_name,
                    "media_kind": media_kind,
                    "optional": is_optional,
                },
            )
            return INPUTTING_PARAMS

        if param_type == 'boolean':
            default_value = param_info.get('default')
            keyboard = [[
                InlineKeyboardButton("✅ Да (true)", callback_data=f"set_param:{param_name}:true"),
                InlineKeyboardButton("❌ Нет (false)", callback_data=f"set_param:{param_name}:false")
            ]]
            if is_optional:
                if default_value is None:
                    skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
                    keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
                else:
                    skip_text = "⏭️ Использовать по умолчанию" if user_lang == 'ru' else "⏭️ Use default"
                    keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{str(default_value).lower()}")])

            keyboard.append([
                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
            ])
            keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
            keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])

            param_desc = param_info.get('description', '')
            default_text = ""
            if is_optional and default_value is not None:
                default_text = f"\n\nПо умолчанию: {'Да' if default_value else 'Нет'}"
            step_info = _get_step_info(session, param_name, user_lang)
            step_prefix = f"{step_info}: " if step_info else ""
            format_hint = _get_param_format_hint(param_type, enum_values, user_lang)
            example_hint = _get_param_example(param_name, param_info, user_lang, enum_values)
            example_line = f"🧪 {example_hint}\n" if example_hint else ""
            details_text = "\n".join([format_hint, required_label, example_hint] if example_hint else [format_hint, required_label])
            free_counter_line = await _resolve_free_counter_line(
                user_id,
                user_lang,
                correlation_id,
                action_path=f"param_prompt:{param_name}",
                sku_id=sku_id,
            )
            message_text = _append_free_counter_text(
                (
                    f"📝 <b>{step_prefix}Выберите {param_name}:</b>\n\n"
                    f"{param_desc}{default_text}\n\n"
                    f"💡 {details_text}\n{example_line}\n"
                    f"{price_line}"
                ),
                free_counter_line,
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="PARAM_PROMPTED",
                action_path="start_next_parameter",
                model_id=model_id,
                outcome="shown",
                param={"param_name": param_name, "type": param_type},
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="UX_STEP_PROMPTED",
                action_path="start_next_parameter",
                model_id=model_id,
                gen_type=session.get("gen_type"),
                waiting_for=param_name,
                outcome="shown",
                param={
                    "param_name": param_name,
                    "type": param_type,
                    "optional": is_optional,
                },
            )
            session['waiting_for'] = param_name
            return INPUTTING_PARAMS

        if enum_values:
            default_value = param_info.get('default')
            price_depends, param_price_map = _get_param_price_variants(
                model_id,
                param_name,
                session.get("params", {}),
            )
            display_values = list(enum_values)
            if price_depends:
                display_values = [value for value in enum_values if str(value) in param_price_map]
                if not display_values:
                    blocked_text = (
                        "⛔️ <b>Нет цены для доступных вариантов</b>"
                        if user_lang == "ru"
                        else "⛔️ <b>No price for available variants</b>"
                    )
                    blocked_keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu"),
                        ]
                    ])
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=blocked_text,
                        reply_markup=blocked_keyboard,
                        parse_mode="HTML",
                    )
                    return INPUTTING_PARAMS

            price_variants_text = ""
            if price_depends:
                price_rows = _format_param_price_rows([str(value) for value in display_values], param_price_map)
                price_variants_text = "\n".join(price_rows)

            keyboard = []
            if price_depends:
                from app.pricing.price_resolver import format_price_rub
            for i in range(0, len(display_values), 2):
                first_value = display_values[i]
                first_label = str(first_value)
                if price_depends:
                    price_value = param_price_map.get(str(first_value))
                    if price_value is not None:
                        first_label = f"{first_label} — {format_price_rub(price_value)}₽"
                row = [
                    InlineKeyboardButton(first_label, callback_data=f"set_param:{param_name}:{first_value}")
                ]
                if i + 1 < len(display_values):
                    second_value = display_values[i + 1]
                    second_label = str(second_value)
                    if price_depends:
                        price_value = param_price_map.get(str(second_value))
                        if price_value is not None:
                            second_label = f"{second_label} — {format_price_rub(price_value)}₽"
                    row.append(InlineKeyboardButton(second_label, callback_data=f"set_param:{param_name}:{second_value}"))
                keyboard.append(row)

            if is_optional:
                if default_value is not None and default_value in display_values:
                    default_text = (
                        f"⏭️ Использовать по умолчанию ({default_value})"
                        if user_lang == "ru"
                        else f"⏭️ Use default ({default_value})"
                    )
                    keyboard.append([InlineKeyboardButton(default_text, callback_data=f"set_param:{param_name}:{default_value}")])
                elif default_value is None:
                    skip_text = "⏭️ Пропустить (auto)" if user_lang == "ru" else "⏭️ Skip (auto)"
                    keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])

            keyboard.append([
                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
            ])
            keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])

            param_desc = param_info.get('description', '')
            default_info = ""
            if default_value and default_value in display_values:
                default_info = (
                    f"\n\n💡 По умолчанию: <b>{default_value}</b>"
                    if user_lang == 'ru'
                    else f"\n\n💡 Default: <b>{default_value}</b>"
                )
            param_label = _humanize_param_name(param_name, user_lang)
            free_counter_line = await _resolve_free_counter_line(
                user_id,
                user_lang,
                correlation_id,
                action_path=f"param_prompt:{param_name}",
                sku_id=sku_id,
            )
            header_text = (
                f"⚙️ <b>Выберите {param_label}:</b>"
                if user_lang == "ru"
                else f"⚙️ <b>Select {param_label}:</b>"
            )
            instructions_text = (
                "💡 Нажмите одну из кнопок ниже"
                if user_lang == "ru"
                else "💡 Tap one of the buttons below"
            )
            variants_block = f"\n\n{price_variants_text}" if price_variants_text else ""
            message_text = _append_free_counter_text(
                (
                    f"{header_text}\n\n"
                    f"{param_desc}{default_info}\n\n"
                    f"{instructions_text}"
                    f"{variants_block}\n\n"
                    f"{price_line}"
                ),
                free_counter_line,
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="PARAM_PROMPTED",
                action_path="start_next_parameter",
                model_id=model_id,
                outcome="shown",
                param={"param_name": param_name, "type": param_type},
            )
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="UX_STEP_PROMPTED",
                action_path="start_next_parameter",
                model_id=model_id,
                gen_type=session.get("gen_type"),
                waiting_for=param_name,
                outcome="shown",
                param={
                    "param_name": param_name,
                    "type": param_type,
                    "optional": is_optional,
                },
            )
            session['waiting_for'] = param_name
            return INPUTTING_PARAMS

        param_desc = param_info.get('description', '')
        max_length = param_info.get('max') or param_info.get('max_length')
        max_text = f"\n\nМакс. длина: {max_length} символов" if max_length else ""
        default_value = param_info.get('default')
        format_hint = _get_param_format_hint(param_type, enum_values, user_lang)
        example_hint = _get_param_example(param_name, param_info, user_lang, enum_values)
        example_line = f"🧪 {example_hint}\n" if example_hint else ""

        keyboard = []
        if is_optional:
            if default_value:
                default_text = f" (по умолчанию: {default_value})" if default_value else ""
                keyboard.append([InlineKeyboardButton(f"⏭️ Использовать по умолчанию{default_text}", callback_data=f"set_param:{param_name}:{default_value}")])
            else:
                skip_text = "⏭️ Пропустить (auto)" if user_lang == 'ru' else "⏭️ Skip (auto)"
                keyboard.append([InlineKeyboardButton(skip_text, callback_data=f"set_param:{param_name}:{SKIP_PARAM_VALUE}")])
        keyboard.append([
            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
        ])
        keyboard.append([InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")])
        keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])

        default_info = f"\n\nПо умолчанию: {default_value}" if default_value and is_optional else ""
        optional_text = "\n\n(Этот параметр опциональный)" if is_optional else ""
        param_display_name = param_name.replace('_', ' ').title()
        step_info = _get_step_info(session, param_name, user_lang)
        step_prefix = f"{step_info}: " if step_info else ""
        if default_value:
            action_hint = "• Или используйте кнопку «⏭️ Использовать по умолчанию» ниже"
        elif is_optional:
            action_hint = "• Или используйте кнопку «⏭️ Пропустить (auto)» ниже"
        else:
            action_hint = "• Отправьте значение текстом"
        if user_lang != 'ru':
            if default_value:
                action_hint = "• Or use the “⏭️ Use default” button below"
            elif is_optional:
                action_hint = "• Or use the “⏭️ Skip (auto)” button below"
            else:
                action_hint = "• Send the value as text"

        free_counter_line = await _resolve_free_counter_line(
            user_id,
            user_lang,
            correlation_id,
            action_path=f"param_prompt:{param_name}",
            sku_id=sku_id,
        )
        message_text = _append_free_counter_text(
            (
                f"📝 <b>{step_prefix}Введите {param_display_name.lower()}:</b>\n\n"
                f"{param_desc}{max_text}{default_info}{optional_text}\n\n"
                f"💡 {format_hint}\n"
                f"{example_line}\n"
                f"💡 <b>Что делать:</b>\n"
                f"• Введите значение в текстовом сообщении\n"
                f"{action_hint}\n\n"
                f"{price_line}"
            ),
            free_counter_line,
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="PARAM_PROMPTED",
            action_path="start_next_parameter",
            model_id=model_id,
            outcome="shown",
            param={"param_name": param_name, "type": param_type},
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="UX_STEP_PROMPTED",
            action_path="start_next_parameter",
            model_id=model_id,
            gen_type=session.get("gen_type"),
            waiting_for=param_name,
            outcome="shown",
            param={
                "param_name": param_name,
                "type": param_type,
                "optional": is_optional,
            },
        )
        session['waiting_for'] = param_name
        return INPUTTING_PARAMS

    trace_event(
        "info",
        correlation_id,
        event="TRACE_IN",
        stage="STATE_VALIDATE",
        update_type="message" if update.message else "callback",
        action="PARAM_SELECT",
        action_path="start_next_parameter",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        fallback_mode=True,
        reason="no_next_param",
    )
    return None


async def input_parameters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Latency wrapper for parameter input."""
    start_ts = time.monotonic()
    try:
        return await _input_parameters_impl(update, context)
    finally:
        _log_handler_latency("input_parameters", start_ts, update)


async def _input_parameters_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle parameter input."""
    import time
    start_time = time.time()
    user_id = update.effective_user.id
    upsert_user_registry_entry(update.effective_user)
    
    # ==================== NO-SILENCE GUARD: Track outgoing actions ====================
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action
    guard = get_no_silence_guard()
    update_id = update.update_id
    # ==================== END NO-SILENCE GUARD ====================

    # CRITICAL: Log function entry IMMEDIATELY
    logger.info(f"🚨🚨🚨 INPUT_PARAMETERS FUNCTION CALLED: user_id={user_id}, update_type={type(update).__name__}")
    
    # 🔥 MAXIMUM LOGGING: Log ALL input_parameters calls
    has_photo = bool(update.message and update.message.photo)
    has_text = bool(update.message and update.message.text)
    has_audio = bool(update.message and (update.message.audio or update.message.voice))
    has_document = bool(update.message and update.message.document)
    logger.debug(f"🔥🔥🔥 INPUT_PARAMETERS ENTRY: user_id={user_id}, has_photo={has_photo}, has_text={has_text}, has_audio={has_audio}, has_document={has_document}, update_type={type(update).__name__}")

    correlation_id = ensure_correlation_id(update, context)
    if _should_dedupe_update(
        update,
        context,
        action="INPUT",
        action_path="input_parameters",
        user_id=user_id,
        chat_id=update.message.chat_id if update.message else None,
    ):
        return ConversationHandler.END
    input_type = "unknown"
    if has_text:
        input_type = "text"
    elif has_photo:
        input_type = "photo"
    elif has_audio:
        input_type = "audio"
    elif has_document:
        input_type = "document"
    chat_id = update.message.chat_id if update.message else None
    guard.set_trace_context(
        update,
        context,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        message_id=update.message.message_id if update.message else None,
        update_type="message",
        correlation_id=correlation_id,
        action="INPUT",
        action_path="input_parameters",
        stage="UI_ROUTER",
        outcome="received",
        input_type=input_type,
    )
    trace_event(
        "info",
        correlation_id,
        event="TRACE_IN",
        stage="UI_ROUTER",
        update_type="message",
        action="INPUT",
        action_path="input_parameters",
        user_id=user_id,
        chat_id=chat_id,
        input_type=input_type,
        message_id=update.message.message_id if update.message else None,
    )
    session = user_sessions.get(user_id, {})
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update_id,
        action="INPUT_COLLECT",
        action_path="input_parameters",
        model_id=session.get("model_id") if isinstance(session, dict) else None,
        gen_type=session.get("gen_type") if isinstance(session, dict) else None,
        stage="INPUT_COLLECT",
        param={
            "waiting_for": session.get("waiting_for") if isinstance(session, dict) else None,
            "current_param": session.get("current_param") if isinstance(session, dict) else None,
            "input_type": input_type,
        },
        outcome="received",
    )
    
    # CRITICAL: Log photo details if photo is present
    if has_photo and update.message and update.message.photo:
        photo_count = len(update.message.photo) if update.message.photo else 0
        photo_file_id = update.message.photo[-1].file_id if update.message.photo else 'None'
        logger.debug(f"🔥🔥🔥 PHOTO DETECTED: user_id={user_id}, photo_count={photo_count}, file_id={photo_file_id}")
    
    if update.message:
        logger.debug(f"🔥🔥🔥 INPUT_PARAMETERS MESSAGE: message_id={update.message.message_id}, chat_id={update.message.chat_id}, date={update.message.date}, from_user_id={update.message.from_user.id if update.message.from_user else 'None'}")
        if has_photo:
            photo_count = len(update.message.photo) if update.message.photo else 0
            logger.debug(f"🔥🔥🔥 INPUT_PARAMETERS PHOTO: photo_count={photo_count}, file_id={update.message.photo[-1].file_id if update.message.photo else 'None'}, file_size={update.message.photo[-1].file_size if update.message.photo and update.message.photo[-1].file_size else 'Unknown'}")
    
    if user_id not in user_sessions:
        logger.error(f"❌❌❌ CRITICAL ERROR: User {user_id} not in user_sessions in input_parameters!")
        logger.error(f"   This means session was lost. User needs to select model again.")
        logger.error(f"   Available sessions: {list(user_sessions.keys())[:10]}")
        logger.error(f"   Total sessions: {len(user_sessions)}")
        if update.message:
            if has_photo:
                # Photo sent but no session - try to help user
                await update.message.reply_text(
                    "❌ <b>Сессия не найдена</b>\n\n"
                    "Похоже, сессия была потеряна. Пожалуйста:\n"
                    "1. Выберите модель заново через /start\n"
                    "2. Затем загрузите изображение\n\n"
                    "Или используйте /cancel для отмены.",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text("❌ Сессия не найдена. Начните заново с /start")
        return ConversationHandler.END
    
    session = user_sessions[user_id]
    model_id = session.get('model_id', 'Unknown')
    waiting_for = session.get('waiting_for', 'None')
    _log_route_decision_once(
        update,
        context,
        waiting_for=waiting_for if waiting_for != "None" else None,
        chosen_handler="input_parameters",
        reason="conversation_handler",
    )
    properties = session.get('properties', {})
    params = session.get('params', {})
    has_image_input = 'image_input' in properties
    has_image_urls = 'image_urls' in properties
    logger.debug(f"🔥🔥🔥 INPUT_PARAMETERS SESSION: user_id={user_id}, model_id={model_id}, waiting_for={waiting_for}, has_image_input={has_image_input}, has_image_urls={has_image_urls}")
    
    image_only_model = _is_image_only_model(properties)
    logger.debug(f"🔥🔥🔥 INPUT_PARAMETERS SESSION KEYS: {list(session.keys())[:15]}")
    logger.debug(f"🔥🔥🔥 INPUT_PARAMETERS PARAMS: keys={list(params.keys())}, values={[(k, type(v).__name__, len(v) if isinstance(v, (list, dict)) else 'N/A') for k, v in params.items()][:5]}")

    missing_media = _collect_missing_required_media(session) if model_id and properties else []
    if update.message and update.message.text and missing_media:
        user_lang = get_user_language(user_id) if user_id else "ru"
        missing_param = missing_media[0]
        param_label = _humanize_param_name(missing_param, user_lang)
        media_kind = _get_media_kind(missing_param) or "media"
        media_label_ru = {
            "image": "изображение",
            "video": "видео",
            "audio": "аудио",
            "document": "файл",
            "media": "медиа",
        }.get(media_kind, "медиа")
        media_label_en = {
            "image": "image",
            "video": "video",
            "audio": "audio",
            "document": "file",
            "media": "media",
        }.get(media_kind, "media")
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="MEDIA_REQUIRED_FIRST",
            action_path="input_parameters",
            model_id=model_id,
            stage="INPUT_GUARD",
            waiting_for=waiting_for,
            outcome="blocked",
            param={"missing_media": missing_media},
        )
        await update.message.reply_text(
            (
                f"📎 <b>Сначала нужно загрузить {media_label_ru}</b>\n\n"
                f"Пожалуйста, загрузите: <b>{param_label}</b>.\n"
                "После загрузки сможете ввести текст и параметры."
                if user_lang == "ru"
                else (
                    f"📎 <b>Please upload the required {media_label_en} first</b>\n\n"
                    f"Please upload: <b>{param_label}</b>.\n"
                    "After upload you can enter text and parameters."
                )
            ),
            parse_mode="HTML",
        )
        await prompt_for_specific_param(update, context, user_id, missing_param, source="media_first_guard")
        return INPUTTING_PARAMS

    trace_event(
        "info",
        correlation_id,
        event="TRACE_IN",
        stage="SESSION_LOAD",
        update_type="message",
        action="INPUT",
        action_path="input_parameters",
        user_id=user_id,
        chat_id=chat_id,
        session_exists=True,
        model_id=model_id,
        waiting_for=waiting_for,
        current_param=session.get("current_param"),
        params_keys=list(params.keys())[:15],
        required=session.get("required", [])[:15],
        param_order=session.get("param_order")[:15] if session.get("param_order") else None,
    )

    def _trace_param_saved(param_name: str, value: Any, source: str) -> None:
        summary: Dict[str, Any] = {
            "param_name": param_name,
            "value_type": type(value).__name__,
            "source": source,
        }
        if isinstance(value, str):
            summary.update(prompt_summary(value))
        elif isinstance(value, list):
            summary["value_len"] = len(value)
        elif isinstance(value, dict):
            summary["value_keys"] = list(value.keys())[:10]
        trace_event(
            "info",
            correlation_id,
            event="TRACE_IN",
            stage="STATE_VALIDATE",
            update_type="message",
            action="PARAM_SAVE",
            action_path="input_parameters",
            user_id=user_id,
            chat_id=chat_id,
            **summary,
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="PARAM_SAVE",
            action_path="input_parameters",
            param=summary,
            outcome="saved",
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="PARAM_SET",
            action_path="input_parameters",
            param=summary,
            outcome="stored",
        )
    
    # CRITICAL: If photo is sent but session doesn't have waiting_for set, log warning
    if has_photo and not waiting_for:
        logger.warning(f"⚠️⚠️⚠️ PHOTO SENT BUT waiting_for is None! user_id={user_id}, model_id={model_id}, properties={list(properties.keys())}, session_keys={list(session.keys())[:10]}")
    
    # Universal handling for schema-based text/number inputs
    if update.message and update.message.text and waiting_for in properties:
        param_info = properties.get(waiting_for, {})
        param_type = param_info.get('type', 'string')
        enum_values = _normalize_enum_values(param_info)
        value_text = update.message.text.strip()

        if param_type in ('number', 'integer', 'float'):
            try:
                value = float(value_text)
                if param_type == 'integer':
                    value = int(value)
            except ValueError:
                await update.message.reply_text(
                    "❌ <b>Неверный формат числа</b>\n\nПожалуйста, отправьте числовое значение.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS

            min_value = param_info.get('min')
            max_value = param_info.get('max')
            if min_value is not None and value < min_value:
                await update.message.reply_text(
                    f"❌ <b>Значение должно быть не меньше {min_value}</b>",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            if max_value is not None and value > max_value:
                await update.message.reply_text(
                    f"❌ <b>Значение должно быть не больше {max_value}</b>",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS

            params[waiting_for] = value
            session['params'] = params
            session['waiting_for'] = None
            _trace_param_saved(waiting_for, value, "number_input")
            next_param_result = await start_next_parameter(update, context, user_id)
            if next_param_result is None:
                return await send_confirmation_message(update, context, user_id, source="number_input")
            return next_param_result

        if enum_values:
            if value_text not in enum_values:
                await update.message.reply_text(
                    "❌ <b>Недопустимое значение</b>\n\nВыберите одно из допустимых значений.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            params[waiting_for] = value_text
            session['params'] = params
            session['waiting_for'] = None
            _trace_param_saved(waiting_for, value_text, "enum_input")
            next_param_result = await start_next_parameter(update, context, user_id)
            if next_param_result is None:
                return await send_confirmation_message(update, context, user_id, source="enum_input")
            return next_param_result

        if param_type == 'boolean':
            normalized = value_text.lower()
            if normalized in {'true', '1', 'yes', 'да'}:
                params[waiting_for] = True
            elif normalized in {'false', '0', 'no', 'нет'}:
                params[waiting_for] = False
            else:
                await update.message.reply_text(
                    "❌ <b>Введите Да/Нет</b>",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            session['params'] = params
            session['waiting_for'] = None
            _trace_param_saved(waiting_for, params[waiting_for], "boolean_input")
            next_param_result = await start_next_parameter(update, context, user_id)
            if next_param_result is None:
                return await send_confirmation_message(update, context, user_id, source="boolean_input")
            return next_param_result

        # Default string handling
        params[waiting_for] = value_text
        session['params'] = params
        session['waiting_for'] = None
        _trace_param_saved(waiting_for, value_text, "text_input")
        next_param_result = await start_next_parameter(update, context, user_id)
        if next_param_result is None:
            return await send_confirmation_message(update, context, user_id, source="text_input")
        return next_param_result

    # Handle admin OCR test
    if user_id == ADMIN_ID and user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'admin_test_ocr':
        if update.message.photo:
            photo = update.message.photo[-1]
            loading_msg = await update.message.reply_text("🔍 Анализирую изображение...")
            
            try:
                file = await context.bot.get_file(photo.file_id)
                image_data = await file.download_as_bytearray()
                
                # Test OCR - extract text
                try:
                    image = Image.open(BytesIO(image_data))
                    try:
                        extracted_text = pytesseract.image_to_string(image, lang='rus+eng')
                    except Exception as e:
                        logger.warning(f"Error with rus+eng, trying eng only: {e}")
                        try:
                            extracted_text = pytesseract.image_to_string(image, lang='eng')
                        except Exception as e2:
                            logger.warning(f"Error with eng, trying default: {e2}")
                            extracted_text = pytesseract.image_to_string(image)
                except Exception as e:
                    error_msg = str(e)
                    if "tesseract is not installed" in error_msg.lower() or "not in your path" in error_msg.lower():
                        raise Exception("Tesseract OCR не найден. Убедитесь, что он установлен и добавлен в PATH.")
                    else:
                        raise Exception(f"Ошибка распознавания текста: {error_msg}")
                
                extracted_text_lower = extracted_text.lower()
                
                # Find amounts in text (improved patterns)
                amount_patterns = [
                    # With currency symbols
                    r'(\d+[.,]\d+)\s*[₽рубР]',
                    r'(\d+)\s*[₽рубР]',
                    r'[₽рубР]\s*(\d+[.,]\d+)',
                    r'[₽рубР]\s*(\d+)',
                    # Near payment keywords
                    r'(?:сумма|итого|перевод|amount|total)[:\s]+(\d+[.,]?\d*)',
                    r'(\d+[.,]?\d*)\s*(?:сумма|итого|перевод|amount|total)',
                    # Misrecognized currency (B instead of Р, 2 instead of Р)
                    r'(\d+)\s*[B2]',
                    r'(\d+)\s*[₽рубРB2]',
                    # Standalone numbers (filtered later)
                    r'\b(\d{2,6})\b',
                ]
                
                found_amounts = []
                for pattern in amount_patterns:
                    matches = re.findall(pattern, extracted_text, re.IGNORECASE)
                    for match in matches:
                        try:
                            amount = float(match.replace(',', '.'))
                            # Filter reasonable amounts (10-100000 rubles)
                            if 10 <= amount <= 100000:
                                found_amounts.append(amount)
                        except:
                            continue
                
                # Check for payment keywords
                payment_keywords = [
                    'перевод', 'оплата', 'платеж', 'спб', 'сбп', 'payment', 'transfer',
                    'отправлено', 'успешно', 'success', 'получатель', 'сумма', 'итого',
                    'квитанция', 'receipt', 'статус', 'status', 'комиссия', 'commission'
                ]
                has_keywords = any(keyword in extracted_text_lower for keyword in payment_keywords)
                
                # Prepare result
                result_text = "🧪 <b>Результаты теста OCR:</b>\n\n"
                
                result_text += f"📝 <b>Распознанный текст (первые 300 символов):</b>\n"
                result_text += f"<code>{extracted_text[:300].replace('<', '&lt;').replace('>', '&gt;')}</code>\n\n"
                
                if found_amounts:
                    result_text += f"💰 <b>Найденные суммы:</b>\n"
                    for amt in sorted(set(found_amounts), reverse=True)[:5]:
                        result_text += f"  • {format_rub_amount(amt)}\n"
                    result_text += "\n"
                else:
                    result_text += "⚠️ <b>Суммы не найдены</b>\n\n"
                
                if has_keywords:
                    result_text += "✅ <b>Признаки платежа обнаружены</b>\n"
                else:
                    result_text += "⚠️ <b>Признаки платежа не обнаружены</b>\n"
                
                result_text += f"\n📊 <b>Статистика:</b>\n"
                result_text += f"  • Символов распознано: {len(extracted_text)}\n"
                result_text += f"  • Сумм найдено: {len(found_amounts)}\n"
                result_text += f"  • Ключевых слов: {'Да' if has_keywords else 'Нет'}\n"
                
                try:
                    await loading_msg.delete()
                except:
                    pass
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Тест еще раз", callback_data="admin_test_ocr")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
                ]
                
                await update.message.reply_text(
                    result_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                
                # Clean up session
                if user_id in user_sessions:
                    del user_sessions[user_id]
                
                return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in admin OCR test: {e}", exc_info=True)
                try:
                    await loading_msg.delete()
                except:
                    pass
                
                error_msg = str(e)
                help_text = ""
                if "tesseract is not installed" in error_msg.lower() or "not in your path" in error_msg.lower() or "tesseract" in error_msg.lower():
                    help_text = (
                        "\n\n💡 <b>Решение:</b>\n"
                        "1. Убедитесь, что Tesseract установлен\n"
                        "2. Проверьте путь: C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n"
                        "3. Или добавьте Tesseract в PATH системы\n"
                        "4. Перезапустите бота после установки"
                    )
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Попробовать еще раз", callback_data="admin_test_ocr")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
                ]
                
                await update.message.reply_text(
                    f"❌ <b>Ошибка теста OCR:</b>\n\n{error_msg}{help_text}\n\n"
                    f"Попробуйте еще раз или нажмите /cancel.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ADMIN_TEST_OCR
        else:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте изображение (фото).\n\n"
                "Или нажмите /cancel для отмены."
            )
            return ADMIN_TEST_OCR
    
    # Handle broadcast message
    if user_id == ADMIN_ID and user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'broadcast_message':
        import time
        from datetime import datetime
        
        # Get message content
        message_text = None
        message_photo = None
        
        if update.message.text:
            message_text = update.message.text
        elif update.message.caption:
            message_text = update.message.caption
        
        if update.message.photo:
            message_photo = update.message.photo[-1]
        
        if not message_text and not message_photo:
            await update.message.reply_text(
                "❌ <b>Ошибка</b>\n\n"
                "Отправьте текст или изображение для рассылки.\n\n"
                "Или нажмите /cancel для отмены.",
                parse_mode='HTML'
            )
            return WAITING_BROADCAST_MESSAGE
        
        # Get all users
        all_users = get_all_users()
        total_users = len(all_users)
        
        if total_users == 0:
            await update.message.reply_text(
                "❌ <b>Нет пользователей для рассылки</b>\n\n"
                "В базе нет пользователей.",
                parse_mode='HTML'
            )
            if user_id in user_sessions:
                del user_sessions[user_id]['waiting_for']
            return ConversationHandler.END
        
        # Create broadcast record
        broadcast_data = {
            'id': len(get_broadcasts()) + 1,
            'message': message_text or '[Изображение]',
            'created_at': int(time.time()),
            'created_by': user_id,
            'total_users': total_users,
            'sent': 0,
            'delivered': 0,
            'failed': 0,
            'user_ids': []
        }
        
        broadcast_id = save_broadcast(broadcast_data)
        
        # Confirm and start sending
        await update.message.reply_text(
            f"📢 <b>Рассылка создана!</b>\n\n"
            f"👥 <b>Получателей:</b> {total_users}\n"
            f"📝 <b>Сообщение:</b> {message_text[:50] + '...' if message_text and len(message_text) > 50 else message_text or '[Изображение]'}\n\n"
            f"⏳ Начинаю отправку...",
            parse_mode='HTML'
        )
        
        # Clear waiting state
        if user_id in user_sessions:
            del user_sessions[user_id]['waiting_for']
        
        # Start broadcast in background
        asyncio.create_task(send_broadcast(context, broadcast_id, all_users, message_text, message_photo))
        
        return ConversationHandler.END
    
    # Handle currency rate input
    if user_id == ADMIN_ID and user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'currency_rate':
        if not update.message.text:
            await update.message.reply_text(
                "❌ <b>Ошибка</b>\n\n"
                "Отправьте числовое значение курса валюты.\n\n"
                "Например: <code>100</code> или <code>95.5</code>\n\n"
                "Или нажмите /cancel для отмены.",
                parse_mode='HTML'
            )
            return WAITING_CURRENCY_RATE
        
        try:
            # Parse currency rate
            rate_text = update.message.text.strip().replace(',', '.')
            new_rate = float(rate_text)
            
            if new_rate <= 0:
                await update.message.reply_text(
                    "❌ <b>Ошибка</b>\n\n"
                    "Курс валюты должен быть положительным числом.\n\n"
                    "Попробуйте еще раз или нажмите /cancel для отмены.",
                    parse_mode='HTML'
                )
                return WAITING_CURRENCY_RATE
            
            # Save currency rate (locked from pricing config)
            if set_usd_to_rub_rate(new_rate):
                current_rate = get_usd_to_rub_rate()
                await update.message.reply_text(
                    f"✅ <b>Курс валюты обновлен!</b>\n\n"
                    f"📊 <b>Новый курс:</b>\n"
                    f"1 USD = {current_rate:.2f} RUB\n\n"
                    f"💡 Все цены будут пересчитаны автоматически при следующем просмотре.",
                    parse_mode='HTML'
                )
                if user_id in user_sessions:
                    del user_sessions[user_id]['waiting_for']
                return ConversationHandler.END

            current_rate = get_usd_to_rub_rate()
            await update.message.reply_text(
                "❌ <b>Курс валюты зафиксирован</b>\n\n"
                f"1 USD = {current_rate:.2f} RUB\n\n"
                "Изменение курса временно отключено.\n"
                "Попробуйте позже или нажмите /cancel для отмены.",
                parse_mode='HTML'
            )
            return WAITING_CURRENCY_RATE
                
        except ValueError:
            await update.message.reply_text(
                "❌ <b>Ошибка</b>\n\n"
                "Неверный формат числа.\n\n"
                "Отправьте числовое значение, например: <code>100</code> или <code>95.5</code>\n\n"
                "Или нажмите /cancel для отмены.",
                parse_mode='HTML'
            )
            return WAITING_CURRENCY_RATE
        except Exception as e:
            logger.error(f"Error setting currency rate: {e}")
            await update.message.reply_text(
                "❌ <b>Ошибка</b>\n\n"
                f"Произошла ошибка: {str(e)}\n\n"
                "Попробуйте еще раз или нажмите /cancel для отмены.",
                parse_mode='HTML'
            )
            return WAITING_CURRENCY_RATE
    
    # Handle payment screenshot
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'payment_screenshot':
        if update.message.photo:
            # User sent payment screenshot
            if user_id not in user_sessions:
                await update.message.reply_text("❌ Сессия не найдена. Начните заново.")
                return ConversationHandler.END
            
            photo = update.message.photo[-1]
            screenshot_file_id = photo.file_id
            
            session = user_sessions[user_id]
            amount = session.get('topup_amount', 0)
            
            # Download and analyze screenshot (if OCR available)
            if OCR_AVAILABLE and PIL_AVAILABLE:
                loading_msg = await update.message.reply_text("🔍 <b>Анализирую скриншот платежа СБП...</b>\n\n⏳ Проверяю сумму, номер телефона и статус перевода...", parse_mode='HTML')
            else:
                loading_msg = await update.message.reply_text("⏳ <b>Обрабатываю платеж...</b>", parse_mode='HTML')
            
            try:
                # Check for duplicate screenshot
                if check_duplicate_payment(screenshot_file_id):
                    await loading_msg.delete()
                    await update.message.reply_text(
                        f"⚠️ <b>Этот скриншот уже был использован</b>\n\n"
                        f"❌ Пожалуйста, отправьте новый скриншот перевода.\n\n"
                        f"💡 Если вы уверены, что это новый платеж, обратитесь к администратору (@ferixdiii).",
                        parse_mode='HTML'
                    )
                    return WAITING_PAYMENT_SCREENSHOT
                
                file = await context.bot.get_file(photo.file_id)
                image_data = await file.download_as_bytearray()
                
                # Get expected phone from .env
                expected_phone = os.getenv('PAYMENT_PHONE', '')
                
                # Analyze screenshot (ALWAYS - strict check)
                analysis = None
                analysis_error = None
                
                if OCR_AVAILABLE and PIL_AVAILABLE:
                    try:
                        # STRICT OCR ANALYSIS - validates real receipt
                        analysis = await analyze_payment_screenshot(image_data, amount, expected_phone if expected_phone else None)
                        logger.info(f"✅ Payment analysis result: valid={analysis.get('valid')}, amount={analysis.get('found_amount')}, phone={analysis.get('phone_found')}")
                    except Exception as e:
                        logger.error(f"❌ OCR API ERROR in analyze_payment_screenshot: {e}", exc_info=True)
                        analysis_error = str(e)
                        # STRICT: On error, require manual review (don't auto-credit)
                        analysis = {
                            'valid': False,
                            'message': f'❌ <b>Ошибка анализа:</b> {analysis_error}\n\nПроверка требует <b>ручной верификации</b> администратором.'
                        }
                else:
                    # OCR not available - require manual review
                    logger.warning(f"⚠️ OCR not available, requiring manual payment verification")
                    analysis = {
                        'valid': False,
                        'message': '❌ <b>Система анализа изображений недоступна</b>\n\nПроверка платежа требует <b>ручной верификации</b> администратором.\n\nОбратитесь в поддержку: @ferixdiii'
                    }
                
                # Delete loading message
                try:
                    await loading_msg.delete()
                except:
                    pass
                
                # Check if screenshot passed validation - STRICT (default False)
                is_valid_payment = analysis.get('valid', False)
                
                if not is_valid_payment:
                    # Payment validation FAILED - reject and show error
                    support_info = get_support_contact()
                    
                    error_message = (
                        f"❌ <b>ПЛАТЕЖ НЕ ПОДТВЕРЖДЕН</b>\n\n"
                        f"{analysis.get('message', 'Скриншот не соответствует требованиям')}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💡 <b>Что делать:</b>\n"
                        f"1️⃣ Убедитесь, что скриншот четкий и видно:\n"
                        f"   • Сумму перевода ({format_rub_amount(amount)})\n"
                        f"   • Номер телефона получателя\n"
                        f"   • Статус платежа (\"успешно\", \"переведено\", \"отправлено\")\n\n"
                        f"2️⃣ Отправьте новый скриншот через 🔄 <b>Пополнить баланс</b>\n\n"
                        f"3️⃣ Если проблема сохраняется, напишите @ferixdiii для ручной верификации\n\n"
                        f"{support_info}"
                    )
                    
                    await update.message.reply_text(
                        error_message,
                        parse_mode='HTML'
                    )
                    
                    # Keep session for retry
                    return WAITING_PAYMENT_SCREENSHOT
                
                # PAYMENT PASSED VALIDATION - Add balance and credit user
                logger.info(f"✅ Payment validation PASSED for user {user_id}, amount {amount} RUB")
                
                # Show success analysis details
                analysis_msg = await update.message.reply_text(
                    f"{analysis.get('message', '')}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"⏳ Начисляю баланс...",
                    parse_mode='HTML'
                )
                
                # Add payment and auto-credit balance
                payment = await add_payment_async(user_id, amount, screenshot_file_id)
                new_balance = await get_user_balance_async(user_id)
                balance_str = format_rub_amount(new_balance)
                
                logger.info(f"✅ Balance credited: user={user_id}, added={amount} RUB, new_balance={new_balance} RUB")
                
                # Delete analysis message
                if analysis_msg:
                    try:
                        await analysis_msg.delete()
                    except:
                        pass
                
                # Clean up session
                if user_id in user_sessions:
                    del user_sessions[user_id]
                
                # Get user language for messages
                user_lang = get_user_language(user_id)
                
                # Create keyboard with main menu button
                keyboard = [
                    [
                        InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                        InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                    ],
                    [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                ]
                
                if user_lang == 'ru':
                    payment_success_msg = (
                        f"✅ <b>ОПЛАТА ПОЛУЧЕНА И ПРОВЕРЕНА!</b> ✅\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💵 <b>Сумма платежа:</b> {format_rub_amount(amount)}\n"
                        f"💰 <b>Новый баланс:</b> {balance_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🎉 <b>Отлично! Баланс пополнен!</b>\n\n"
                        f"💡 <b>Что дальше:</b>\n"
                        f"• Начните генерацию контента прямо сейчас\n"
                        f"• Используйте любую модель из каталога\n"
                        f"• Наслаждайтесь премиум возможностями!\n\n"
                        f"✨ <b>Спасибо за доверие!</b>"
                    )
                else:
                    payment_success_msg = (
                        f"✅ <b>PAYMENT RECEIVED AND VERIFIED!</b> ✅\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"💵 <b>Amount:</b> {format_rub_amount(amount)}\n"
                        f"💰 <b>New balance:</b> {balance_str}\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🎉 <b>Great! Balance topped up!</b>\n\n"
                        f"💡 <b>What's next:</b>\n"
                        f"• Start content generation right now\n"
                        f"• Use any model from the catalog\n"
                        f"• Enjoy premium features!\n\n"
                        f"✨ <b>Thank you for your trust!</b>"
                    )
                
                await update.message.reply_text(
                    payment_success_msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                return ConversationHandler.END
                
            except Exception as e:
                logger.error(f"❌ Error processing payment screenshot: {e}", exc_info=True)
                try:
                    await loading_msg.delete()
                except:
                    pass
                
                support_info = get_support_contact()
                await update.message.reply_text(
                    f"❌ <b>Ошибка обработки платежа</b>\n\n"
                    f"Произошла непредвиденная ошибка при анализе скриншота:\n"
                    f"<code>{str(e)[:100]}</code>\n\n"
                    f"💡 <b>Решение:</b>\n"
                    f"• Попробуйте отправить скриншот еще раз\n"
                    f"• Убедитесь, что скриншот четкий и хорошо виден\n"
                    f"• Если ошибка повторится, обратитесь к администратору\n\n"
                    f"{support_info}",
                    parse_mode='HTML'
                )
                return WAITING_PAYMENT_SCREENSHOT
        else:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте скриншот перевода (фото).\n\n"
                "Или нажмите /cancel для отмены."
            )
            return WAITING_PAYMENT_SCREENSHOT

    # Handle admin user lookup
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'admin_user_lookup':
        if not is_admin(user_id):
            await update.message.reply_text("❌ Эта функция доступна только администратору.")
            user_sessions.pop(user_id, None)
            return ConversationHandler.END
        if not update.message or not update.message.text:
            await update.message.reply_text("❌ Отправьте user_id текстом.")
            return ConversationHandler.END
        try:
            target_user_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")
            return ConversationHandler.END
        user_sessions.pop(user_id, None)
        text, keyboard = await build_admin_user_overview(target_user_id)
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
        return ConversationHandler.END

    # Handle admin manual topup
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'admin_manual_topup_amount':
        if not is_admin(user_id):
            await update.message.reply_text("❌ Эта функция доступна только администратору.")
            user_sessions.pop(user_id, None)
            return ConversationHandler.END
        if not update.message or not update.message.text:
            await update.message.reply_text("❌ Отправьте сумму текстом.")
            return ConversationHandler.END
        session = user_sessions[user_id]
        target_user_id = session.get("admin_target_user_id")
        if target_user_id is None:
            await update.message.reply_text("❌ Не найден пользователь для начисления.")
            user_sessions.pop(user_id, None)
            return ConversationHandler.END
        try:
            amount = float(update.message.text.strip().replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы. Используйте число.")
            return ConversationHandler.END
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0.")
            return ConversationHandler.END
        await add_payment_async(int(target_user_id), amount, screenshot_file_id=None)
        user_sessions.pop(user_id, None)
        text, keyboard = await build_admin_user_overview(int(target_user_id))
        await update.message.reply_text(
            f"✅ Баланс начислен.\n\n{text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    # Handle custom topup amount input
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for') == 'topup_amount_input':
        try:
            amount = float(update.message.text.replace(',', '.'))
            user_lang = get_user_language(user_id)
            
            if amount < 50:
                if user_lang == 'ru':
                    await update.message.reply_text("❌ Минимальная сумма пополнения: 50 ₽")
                else:
                    await update.message.reply_text("❌ Minimum top-up amount: 50 ₽")
                return SELECTING_AMOUNT
            
            if amount > 50000:
                if user_lang == 'ru':
                    await update.message.reply_text("❌ Максимальная сумма пополнения: 50000 ₽")
                else:
                    await update.message.reply_text("❌ Maximum top-up amount: 50000 ₽")
                return SELECTING_AMOUNT
            
            # Calculate what user can generate
            examples_count = int(amount / 0.62)  # free tools price
            video_count = int(amount / 3.86)  # Basic video price
            
            # Show payment method selection
            amount_display = format_rub_amount(amount)
            if user_lang == 'ru':
                payment_text = (
                    f'💳 <b>ОПЛАТА {amount_display}</b> 💳\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💵 <b>Сумма к оплате:</b> {amount_display}\n\n'
                    f'🎯 <b>ЧТО ТЫ ПОЛУЧИШЬ:</b>\n'
                    f'• ~{examples_count} изображений (free tools)\n'
                    f'• ~{video_count} видео (базовая модель)\n'
                    f'• Или комбинацию разных моделей!\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💳 <b>ОПЛАТА ТОЛЬКО ПО СБП:</b>'
                )
            else:
                payment_text = (
                    f'💳 <b>PAYMENT {amount_display}</b> 💳\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💵 <b>Amount to pay:</b> {amount_display}\n\n'
                    f'🎯 <b>WHAT YOU WILL GET:</b>\n'
                    f'• ~{examples_count} images (free tools)\n'
                    f'• ~{video_count} videos (basic model)\n'
                    f'• Or a combination of different models!\n\n'
                    f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                    f'💳 <b>PAYMENT ONLY VIA SBP:</b>'
                )
            
            # Store amount in session
            user_sessions[user_id] = {
                'topup_amount': amount,
                'waiting_for': 'payment_method'
            }
            
            keyboard = [
                [InlineKeyboardButton("💳 СБП / SBP", callback_data=f"pay_sbp:{amount}")],
                [
                    InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                    InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                ],
                [
                    InlineKeyboardButton(t('btn_support', lang=user_lang), callback_data="support_contact"),
                    InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")
                ]
            ]
            
            await update.message.reply_text(
                payment_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return SELECTING_AMOUNT
        except ValueError:
            user_lang = get_user_language(user_id)
            if user_lang == 'ru':
                await update.message.reply_text(
                    "❌ Пожалуйста, введите число (например: 1500)\n\n"
                    "Или нажмите /cancel для отмены."
                )
            else:
                await update.message.reply_text(
                    "❌ Please enter a number (e.g., 1500)\n\n"
                    "Or press /cancel to cancel."
                )
            return SELECTING_AMOUNT
    
    if user_id not in user_sessions:
        logger.warning(f"Session not found for user {user_id} in input_parameters")
        user_lang = get_user_language(user_id)
        error_msg = t('error_session_empty', lang=user_lang) if user_lang else "❌ Сессия не найдена. Начните заново с /start"
        await update.message.reply_text(error_msg)
        return ConversationHandler.END
    
    session = user_sessions[user_id]
    properties = session.get('properties', {})
    
    # CRITICAL: Log session state for debugging
    logger.info(f"Session state: user_id={user_id}, model_id={session.get('model_id', 'Unknown')}, waiting_for={session.get('waiting_for', 'None')}, has_properties={bool(properties)}")
    
    # Handle audio input (for audio_url or audio_input)
    waiting_for_audio = session.get('waiting_for') in ['audio_url', 'audio_input']
    if (update.message.audio or update.message.voice or (update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('audio/'))) and waiting_for_audio:
        # Get audio file
        audio_file = None
        if update.message.audio:
            audio_file = update.message.audio
        elif update.message.voice:
            audio_file = update.message.voice
        elif update.message.document:
            audio_file = update.message.document
        
        if not audio_file:
            await update.message.reply_text("❌ Не удалось получить аудио-файл. Попробуйте еще раз.")
            return INPUTTING_PARAMS
        
        file = await context.bot.get_file(audio_file.file_id)
        
        # Download audio from Telegram
        loading_msg = None
        try:
            # Show loading message
            loading_msg = await update.message.reply_text("📤 Загрузка аудио...")
            
            # Download audio
            try:
                audio_data = await file.download_as_bytearray()
            except Exception as e:
                logger.error(f"Error downloading audio file from Telegram: {e}", exc_info=True)
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Ошибка загрузки</b>\n\n"
                    "Не удалось скачать аудио-файл из Telegram.\n"
                    "Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            # Check file size (max 200MB as per API)
            if len(audio_data) > 200 * 1024 * 1024:
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Файл слишком большой</b>\n\n"
                    "Максимальный размер: 200 MB.\n"
                    "Попробуйте другой файл.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            if len(audio_data) == 0:
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Ошибка загрузки</b>\n\n"
                    "Аудио-файл пустой.\n"
                    "Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            logger.info(f"Downloaded audio: {len(audio_data)} bytes")
            
            # Determine file extension
            file_extension = "mp3"
            if update.message.audio:
                if update.message.audio.mime_type:
                    if "wav" in update.message.audio.mime_type:
                        file_extension = "wav"
                    elif "ogg" in update.message.audio.mime_type:
                        file_extension = "ogg"
                    elif "aac" in update.message.audio.mime_type:
                        file_extension = "aac"
                    elif "mp4" in update.message.audio.mime_type:
                        file_extension = "m4a"
            elif update.message.document and update.message.document.mime_type:
                if "wav" in update.message.document.mime_type:
                    file_extension = "wav"
                elif "ogg" in update.message.document.mime_type:
                    file_extension = "ogg"
                elif "aac" in update.message.document.mime_type:
                    file_extension = "aac"
                elif "mp4" in update.message.document.mime_type:
                    file_extension = "m4a"
            
            # Upload to public hosting
            filename = f"audio_{user_id}_{audio_file.file_id[:8]}.{file_extension}"
            public_url = await upload_image_to_hosting(audio_data, filename=filename)
            
            # Delete loading message
            if loading_msg:
                try:
                    await loading_msg.delete()
                except:
                    pass
            
            if not public_url:
                await update.message.reply_text(
                    "❌ <b>Ошибка загрузки</b>\n\n"
                    "Не удалось обработать аудио-файл.\n"
                    "Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            logger.info(f"Successfully uploaded audio to: {public_url}")
            
            # Set audio_url parameter
            audio_param_name = session.get('waiting_for', 'audio_url')
            if 'params' not in session:
                session['params'] = {}
            session['params'][audio_param_name] = public_url
            session[audio_param_name] = public_url  # Also store in session for consistency
            session['waiting_for'] = None
            session['current_param'] = None
            
            # Confirm audio was set
            await update.message.reply_text(
                f"✅ <b>Аудио-файл загружен!</b>\n\n"
                f"Обрабатываю...",
                parse_mode='HTML'
            )
            
            # Move to next parameter
            try:
                next_param_result = await start_next_parameter(update, context, user_id)
                if next_param_result:
                    return next_param_result
                else:
                    # All parameters collected, show confirmation
                    model_name = session.get('model_info', {}).get('name', 'Unknown')
                    params = session.get('params', {})
                    params_text = "\n".join([f"  • {k}: {str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in params.items()])
                    
                    user_lang = get_user_language(user_id)
                    keyboard = [
                        [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                        [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                        [
                            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                        ],
                        [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                    ]
                    
                    await update.message.reply_text(
                        f"📋 <b>Подтверждение:</b>\n\n"
                        f"Модель: <b>{model_name}</b>\n"
                        f"Параметры:\n{params_text}\n\n"
                        f"Продолжить генерацию?",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return CONFIRMING_GENERATION
            except Exception as e:
                logger.error(f"Error after audio input: {e}", exc_info=True)
                await update.message.reply_text("❌ Ошибка при переходе к следующему параметру.")
            
            return INPUTTING_PARAMS
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}", exc_info=True)
            # Try to delete loading message if exists
            if loading_msg:
                try:
                    await loading_msg.delete()
                except:
                    pass
            
            await update.message.reply_text(
                "❌ <b>Ошибка обработки</b>\n\n"
                "Не удалось обработать аудио-файл.\n"
                "Попробуйте еще раз.",
                parse_mode='HTML'
            )
            return INPUTTING_PARAMS
    
    # Handle image input (for image_input, image_urls, mask_input, reference_image_input or 'image')
    waiting_for = session.get('waiting_for')
    waiting_for_image = waiting_for in ['image_input', 'image_urls', 'image', 'mask_input', 'reference_image_input']
    
    # CRITICAL: Log for debugging
    model_id = session.get('model_id', 'Unknown')
    properties = session.get('properties', {})
    logger.info(f"🔍🔍🔍 Image input check: user_id={user_id}, waiting_for={waiting_for}, waiting_for_image={waiting_for_image}, has_photo={bool(update.message.photo)}, model_id={model_id}, has_image_input={bool('image_input' in properties)}, has_image_urls={bool('image_urls' in properties)}, session_keys={list(session.keys())[:10]}")
    
    # CRITICAL: If photo is sent and model requires image, but waiting_for is not set, auto-fix immediately
    if update.message.photo and not waiting_for_image:
        # Check if model requires image_input or image_urls
        if 'image_input' in properties or 'image_urls' in properties:
            # Determine which parameter name to use
            if 'image_input' in properties:
                image_param_name = 'image_input'
            elif 'image_urls' in properties:
                image_param_name = 'image_urls'
            else:
                image_param_name = 'image_input'  # Default fallback
            
            # Check if this parameter is required
            param_info = properties.get(image_param_name, {})
            is_required = param_info.get('required', False)
            
            # Models that definitely require image first
            models_require_image = [
                "recraft/remove-background",
                "recraft/crisp-upscale",
                "ideogram/v3-reframe",
                "topaz/image-upscale",
                "nano-banana-pro"
            ]
            
            # Auto-fix if model requires image or is in the list
            if model_id in models_require_image or is_required:
                logger.warning(f"🔧 AUTO-FIX: Photo sent for {model_id} but waiting_for={waiting_for}, fixing session immediately...")
                session['waiting_for'] = image_param_name
                session['current_param'] = image_param_name
                if image_param_name not in session:
                    session[image_param_name] = []
                waiting_for_image = True
                waiting_for = image_param_name
                logger.info(f"✅✅✅ AUTO-FIX COMPLETE: waiting_for={image_param_name}, model={model_id}, continuing image processing...")
    
    # CRITICAL: Check if waiting for URL parameter but file was sent
    waiting_for = session.get('waiting_for')
    if waiting_for and waiting_for.endswith('_url') and waiting_for != 'image_urls':
        # For URL parameters (except image_urls which accepts files), check if file was sent
        if update.message.photo or update.message.video or update.message.document or update.message.audio:
            user_lang = get_user_language(user_id)
            param_name = waiting_for.replace('_url', '').replace('_', ' ').title()
            if user_lang == 'en':
                error_msg = (
                    f"❌ <b>URL required, not file</b>\n\n"
                    f"Parameter <b>{waiting_for}</b> requires a URL (link), not a file.\n\n"
                    f"Please send the URL as text (e.g., https://example.com/file.mp4)\n\n"
                    f"If you have a file, upload it to a hosting service first and send the URL."
                )
            else:
                error_msg = (
                    f"❌ <b>Требуется URL, а не файл</b>\n\n"
                    f"Параметр <b>{waiting_for}</b> требует URL (ссылку), а не файл.\n\n"
                    f"Пожалуйста, отправьте URL текстом (например, https://example.com/file.mp4)\n\n"
                    f"Если у вас есть файл, сначала загрузите его на хостинг и отправьте URL."
                )
            await update.message.reply_text(error_msg, parse_mode='HTML')
            return INPUTTING_PARAMS
    
    # If photo sent but not waiting for image, try to auto-fix session
    if update.message.photo and not waiting_for_image:
        model_id = session.get('model_id', 'Unknown')
        user_lang = get_user_language(user_id)
        
        # Check if model requires image_input
        properties = session.get('properties', {})
        has_image_param = 'image_input' in properties or 'image_urls' in properties
        
        # CRITICAL: Auto-fix session for models that require image_input
        # This handles cases where photo is sent but session state is lost or incorrect
        if has_image_param:
            # Check which parameter name to use
            if 'image_input' in properties:
                image_param_name = 'image_input'
            elif 'image_urls' in properties:
                image_param_name = 'image_urls'
            else:
                image_param_name = 'image_input'  # Default fallback
            
            # Auto-fix for models that require image (nano-banana-pro, recraft models, ideogram, topaz, etc.)
            models_require_image_first = [
                "nano-banana-pro",
                "recraft/remove-background",
                "recraft/crisp-upscale",
                "ideogram/v3-reframe",
                "topaz/image-upscale",
                "recraft/remove-background"  # Explicitly include this
            ]
            if model_id in models_require_image_first or \
               (properties.get(image_param_name, {}).get('required', False)):
                logger.warning(f"⚠️ Photo sent for {model_id} but waiting_for={waiting_for}, fixing session...")
                session['waiting_for'] = image_param_name
                session['current_param'] = image_param_name
                if image_param_name not in session:
                    session[image_param_name] = []
                # Update local variables to continue processing
                waiting_for_image = True
                waiting_for = image_param_name
                logger.info(f"✅✅✅ Session fixed: waiting_for={image_param_name}, model={model_id}, continuing image processing...")
                # Continue to process the image below
            else:
                # Photo sent but not expected - show helpful message
                if user_lang == 'en':
                    error_msg = (
                        "⚠️ <b>Image not expected now</b>\n\n"
                        f"Current step: {waiting_for or 'none'}\n\n"
                        "Please follow the instructions or use /cancel to start over."
                    )
                else:
                    error_msg = (
                        "⚠️ <b>Изображение не ожидается сейчас</b>\n\n"
                        f"Текущий шаг: {waiting_for or 'нет'}\n\n"
                        "Пожалуйста, следуйте инструкциям или используйте /cancel для начала заново."
                    )
                await update.message.reply_text(error_msg, parse_mode='HTML')
                return INPUTTING_PARAMS
        else:
            # Photo sent but not expected - show helpful message
            if user_lang == 'en':
                error_msg = (
                    "⚠️ <b>Image not expected now</b>\n\n"
                    f"Current step: {waiting_for or 'none'}\n\n"
                    "Please follow the instructions or use /cancel to start over."
                )
            else:
                error_msg = (
                    "⚠️ <b>Изображение не ожидается сейчас</b>\n\n"
                    f"Текущий шаг: {waiting_for or 'нет'}\n\n"
                    "Пожалуйста, следуйте инструкциям или используйте /cancel для начала заново."
                )
            await update.message.reply_text(error_msg, parse_mode='HTML')
            return INPUTTING_PARAMS
    
    # Process image if photo is sent and we're waiting for image
    if update.message.photo and waiting_for_image:
        logger.info(f"✅✅✅ Processing image for user {user_id}, waiting_for={waiting_for}, model={session.get('model_id', 'Unknown')}, image_param_name will be determined from waiting_for")
        photo = update.message.photo[-1]  # Get largest photo
        file = await context.bot.get_file(photo.file_id)
        
        # Download image from Telegram
        loading_msg = None
        try:
            # Show loading message
            loading_msg = await update.message.reply_text("📤 Загрузка...")
            
            # Download image
            try:
                image_data = await file.download_as_bytearray()
            except Exception as e:
                logger.error(f"❌❌❌ ERROR DOWNLOADING IMAGE: user_id={user_id}, error={str(e)}, error_type={type(e).__name__}, file_id={photo.file_id if 'photo' in locals() else 'Unknown'}", exc_info=True)
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Ошибка загрузки</b>\n\n"
                    "Не удалось скачать изображение из Telegram.\n"
                    "Попробуйте еще раз или пропустите этот шаг.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            # Check file size (max 30MB as per KIE API)
            if len(image_data) > 30 * 1024 * 1024:
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Файл слишком большой</b>\n\n"
                    "Максимальный размер: 30 MB.\n"
                    "Попробуйте другое изображение или пропустите этот шаг.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            if len(image_data) == 0:
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Ошибка загрузки</b>\n\n"
                    "Изображение пустое.\n"
                    "Попробуйте еще раз или пропустите этот шаг.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            logger.debug(f"🔥🔥🔥 IMAGE DOWNLOADED: size={len(image_data)} bytes, user_id={user_id}, file_id={photo.file_id[:8]}")
            
            # Upload to public hosting
            logger.debug(f"🔥🔥🔥 UPLOADING TO HOSTING: user_id={user_id}, filename=image_{user_id}_{photo.file_id[:8]}.jpg")
            # 🔴 API CALL: File Upload API - upload_image_to_hosting
            try:
                public_url = await upload_image_with_fallback(
                    image_data,
                    filename=f"image_{user_id}_{photo.file_id[:8]}.jpg",
                )
            except Exception as e:
                logger.error(f"❌❌❌ FILE UPLOAD API ERROR in upload_image_to_hosting (image): {e}", exc_info=True)
                user_lang = get_user_language(user_id) if user_id else 'ru'
                error_msg = "Ошибка сервера, попробуйте позже" if user_lang == 'ru' else "Server error, please try later"
                await update.message.reply_text(
                    f"❌ <b>{error_msg}</b>\n\n"
                    f"Не удалось загрузить изображение.\n"
                    f"Попробуйте еще раз через несколько секунд.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            # Delete loading message
            if loading_msg:
                try:
                    await loading_msg.delete()
                except:
                    pass
            
            if not public_url:
                logger.error(f"❌❌❌ IMAGE UPLOAD FAILED: user_id={user_id}, model_id={session.get('model_id', 'Unknown')}, file_size={len(image_data)} bytes, upload_image_to_hosting returned None")
                try:
                    log_structured_event(
                        correlation_id=ensure_correlation_id(update, context),
                        user_id=user_id,
                        chat_id=update.effective_chat.id if update.effective_chat else None,
                        update_id=update.update_id,
                        action="IMAGE_UPLOAD",
                        action_path="image_upload>fallback",
                        stage="image_upload",
                        outcome="upload_unavailable",
                        error_code="IMAGE_HOSTING_HTTP_CLIENT_NOT_INITIALIZED",
                        fix_hint="declare_global_http_client_and_init_aiohttp_session",
                    )
                except Exception as log_error:
                    logger.warning("STRUCTURED_LOG image upload unavailable failed: %s", log_error, exc_info=True)
                await update.message.reply_text(
                    "⚠️ <b>Аплоад временно недоступен</b>\n\n"
                    "Не удалось загрузить изображение.\n"
                    "Попробуйте еще раз позже или пропустите этот шаг.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            logger.debug(f"🔥🔥🔥 IMAGE UPLOADED TO HOSTING: public_url={public_url}, user_id={user_id}, file_size={len(image_data)} bytes, model_id={session.get('model_id', 'Unknown')}")
            
            # Add to image_input array
            # Determine which parameter name to use
            waiting_for = session.get('waiting_for', 'image_input')
            logger.debug(f"🔥🔥🔥 IMAGE PROCESSING: waiting_for={waiting_for}, user_id={user_id}, model_id={session.get('model_id', 'Unknown')}")
            # Normalize: if waiting_for is 'image', use the actual parameter name from properties
            if waiting_for == 'image':
                properties = session.get('properties', {})
                if 'image_input' in properties:
                    image_param_name = 'image_input'
                elif 'image_urls' in properties:
                    image_param_name = 'image_urls'
                else:
                    image_param_name = 'image_input'  # Default fallback
            else:
                image_param_name = waiting_for  # image_input or image_urls
            if image_param_name not in session:
                session[image_param_name] = []
            session[image_param_name].append(public_url)
            logger.debug(f"🔥🔥🔥 IMAGE ADDED TO SESSION: param={image_param_name}, count={len(session[image_param_name])}, model={session.get('model_id', 'Unknown')}, user_id={user_id}, urls={session[image_param_name][:2]}")
            
        except Exception as e:
            logger.error(f"❌❌❌ ERROR PROCESSING IMAGE: user_id={user_id}, error={str(e)}, error_type={type(e).__name__}", exc_info=True)
            if user_id in user_sessions:
                session_error = user_sessions[user_id]
                logger.error(f"❌❌❌ ERROR CONTEXT: model_id={session_error.get('model_id', 'Unknown')}, waiting_for={session_error.get('waiting_for', 'None')}, session_keys={list(session_error.keys())[:10]}")
            else:
                logger.error(f"❌❌❌ ERROR CONTEXT: No session found for user_id={user_id}")
            # Try to delete loading message if exists
            if loading_msg:
                try:
                    await loading_msg.delete()
                except:
                    pass
            
            await update.message.reply_text(
                "❌ <b>Ошибка обработки</b>\n\n"
                "Не удалось обработать изображение.\n"
                "Попробуйте еще раз или пропустите этот шаг.",
                parse_mode='HTML'
            )
            return INPUTTING_PARAMS
        
        # Determine image parameter name (normalize 'image' to actual param name)
        waiting_for = session.get('waiting_for', 'image_input')
        if waiting_for == 'image':
            properties_check = session.get('properties', {})
            if 'image_input' in properties_check:
                image_param_name = 'image_input'
            elif 'image_urls' in properties_check:
                image_param_name = 'image_urls'
            else:
                image_param_name = 'image_input'  # Default fallback
        else:
            image_param_name = waiting_for
        
        image_count = len(session.get(image_param_name, []))
        
        # Check if model requires only 1 image (max_items = 1)
        properties = session.get('properties', {})
        param_info = properties.get(image_param_name, {})
        max_items = param_info.get('max_items', 8)  # Default to 8 if not specified
        
        model_id = session.get('model_id', 'Unknown')
        
        # CRITICAL: For models that only require image (no prompt), force max_items=1
        # This ensures they always show the button immediately after image upload
        if image_only_model:
            max_items = 1  # Force to 1 for these models
            logger.info(f"🔍 Model {model_id} is image-only, forcing max_items=1")
        
        logger.info(f"🔍 Image processing: model={model_id}, image_param_name={image_param_name}, max_items={max_items}, image_count={image_count}, session_keys={list(session.keys())}")
        
        # If max_items is 1, immediately move to next parameter (or show button for image-only models)
        if max_items == 1:
            user_lang = get_user_language(user_id)
            if user_lang == 'en':
                success_msg = "✅ Image uploaded!\n\nContinuing..."
            else:
                success_msg = "✅ Изображение загружено!\n\nПродолжаю..."
            await update.message.reply_text(success_msg)
            
            if 'params' not in session:
                session['params'] = {}
            
            # Store image_input as array (API expects array)
            # CRITICAL: Ensure image_input is properly stored in params
            if image_param_name not in session:
                logger.error(f"ERROR: {image_param_name} not in session after upload!")
                session[image_param_name] = []
            
            # CRITICAL: Store image_input as array (API expects array)
            # Ensure we have the image data before storing
            if image_param_name not in session or not session[image_param_name]:
                logger.error(f"CRITICAL ERROR: {image_param_name} not in session or empty after upload!")
                await update.message.reply_text(
                    "❌ <b>Ошибка</b>\n\nНе удалось сохранить изображение. Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            # Store in params
            if isinstance(session[image_param_name], list):
                session['params'][image_param_name] = session[image_param_name].copy()  # Use copy to avoid reference issues
            else:
                session['params'][image_param_name] = [session[image_param_name]]
            
            # CRITICAL: Double-check that params contains the image
            if image_param_name not in session.get('params', {}) or not session.get('params', {}).get(image_param_name):
                logger.error(f"ERROR: {image_param_name} not properly stored in params! Fixing...")
                if image_param_name in session and session[image_param_name]:
                    if isinstance(session[image_param_name], list):
                        session['params'][image_param_name] = session[image_param_name].copy()
                    else:
                        session['params'][image_param_name] = [session[image_param_name]]
                else:
                    logger.error(f"CRITICAL: Cannot fix - {image_param_name} not in session!")
                    await update.message.reply_text(
                        "❌ <b>Ошибка</b>\n\nНе удалось сохранить изображение. Попробуйте еще раз.",
                        parse_mode='HTML'
                    )
                    return INPUTTING_PARAMS
            
            # TRIPLE-CHECK: Verify the image is actually in params
            if not session.get('params', {}).get(image_param_name):
                logger.error(f"CRITICAL: {image_param_name} still not in params after all fixes!")
                await update.message.reply_text(
                    "❌ <b>Ошибка</b>\n\nНе удалось сохранить изображение. Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            
            logger.debug(f"🔥🔥🔥 IMAGE VERIFIED IN PARAMS: param={image_param_name}, count={len(session['params'][image_param_name])}, user_id={user_id}, model_id={model_id}, urls={session['params'][image_param_name][:1]}")
            
            session['waiting_for'] = None
            session['current_param'] = None
            logger.debug(f"🔥🔥🔥 SESSION UPDATED: waiting_for=None, current_param=None, user_id={user_id}, model_id={model_id}")

            next_param_result = await start_next_parameter(update, context, user_id)
            if next_param_result is None:
                return await send_confirmation_message(update, context, user_id, source="image_upload")
            return next_param_result
            
            # CRITICAL: If all_required_collected is still False but this is an image-only model with image uploaded,
            # FORCE show the button anyway - this is a safety net
            if not all_required_collected and image_only_model:
                params_safety = session.get('params', {})
                if image_param_name in params_safety and params_safety.get(image_param_name):
                    logger.warning(f"⚠️⚠️⚠️ SAFETY NET: all_required_collected=False but {model_id} has image, FORCING button show")
                    all_required_collected = True
                    # Jump directly to showing button (code below will handle it)
                elif image_param_name in session and session.get(image_param_name):
                    logger.warning(f"⚠️⚠️⚠️ SAFETY NET: Moving image from session to params for {model_id}")
                    if 'params' not in session:
                        session['params'] = {}
                    if isinstance(session[image_param_name], list):
                        session['params'][image_param_name] = session[image_param_name].copy()
                    else:
                        session['params'][image_param_name] = [session[image_param_name]]
                    all_required_collected = True
            
            # Move to next parameter if not all collected (only if button wasn't shown above)
            if not all_required_collected:
                try:
                    next_param_result = await start_next_parameter(update, context, user_id)
                    logger.info(f"start_next_parameter returned: {next_param_result} for model {model_id}")
                    if next_param_result:
                        return next_param_result
                    else:
                        # All parameters collected, show confirmation
                        model_name = session.get('model_info', {}).get('name', 'Unknown')
                        params = session.get('params', {})
                        logger.info(f"All parameters collected for {model_id}, params: {list(params.keys())}")
                        params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in params.items()])
                        
                        user_lang = get_user_language(user_id)
                        keyboard = [
                            [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                            [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                            [
                                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                            ],
                            [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                        ]
                        
                        # Calculate price for confirmation
                        sku_id = session.get("sku_id", "")
                        is_free = await is_free_generation_available(user_id, sku_id)
                        price = calculate_price_rub(model_id, params, is_admin_user)
                        if price is None:
                            blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
                            await update.message.reply_text(blocked_text, parse_mode="HTML")
                            return INPUTTING_PARAMS
                        if is_free:
                            price = 0.0
                        price_str = format_rub_amount(price)
                        
                        # Prepare price info
                        if is_free:
                            remaining = await get_user_free_generations_remaining(user_id)
                            price_info = f"🎁 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ!</b>\nОсталось бесплатных: {remaining}/{FREE_GENERATIONS_PER_DAY} в день"
                        else:
                            price_info = f"💰 <b>Стоимость:</b> {price_str}"
                        
                        if user_lang == 'en':
                            price_info_en = f"🎁 <b>FREE GENERATION!</b>\nRemaining free: {remaining}/{FREE_GENERATIONS_PER_DAY} per day" if is_free else f"💰 <b>Cost:</b> {price_str}"
                            confirm_text = (
                                f"📋 <b>Generation Confirmation</b>\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"🤖 <b>Model:</b> {model_name}\n\n"
                                f"⚙️ <b>Parameters:</b>\n{params_text}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{price_info_en}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"💡 <b>What's next:</b>\n"
                                f"• Generation will start after confirmation\n"
                                f"• Result will come automatically\n"
                                f"• Usually takes from 10 seconds to 2 minutes\n\n"
                                f"🚀 <b>Ready to start?</b>"
                            )
                        else:
                            confirm_text = (
                                f"📋 <b>Подтверждение генерации</b>\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"🤖 <b>Модель:</b> {model_name}\n\n"
                                f"⚙️ <b>Параметры:</b>\n{params_text}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"{price_info}\n\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                f"💡 <b>Что будет дальше:</b>\n"
                                f"• Генерация начнется после подтверждения\n"
                                f"• Результат придет автоматически\n"
                                f"• Обычно это занимает от 10 секунд до 2 минут\n\n"
                                f"🚀 <b>Готовы начать?</b>"
                            )
                        
                        # Check if we have update.message or need to use context.bot
                        try:
                            if update.message:
                                await update.message.reply_text(
                                    confirm_text,
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='HTML'
                                )
                            elif update.callback_query:
                                try:
                                    await update.callback_query.edit_message_text(
                                        confirm_text,
                                        reply_markup=InlineKeyboardMarkup(keyboard),
                                        parse_mode='HTML'
                                    )
                                except Exception as edit_error:
                                    logger.warning(f"Could not edit message, sending new: {edit_error}")
                                    await update.callback_query.message.reply_text(
                                        confirm_text,
                                        reply_markup=InlineKeyboardMarkup(keyboard),
                                        parse_mode='HTML'
                                    )
                            else:
                                await context.bot.send_message(
                                    chat_id=user_id,
                                    text=confirm_text,
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='HTML'
                                )
                            logger.info(f"✅✅✅ Confirmation button shown for {model_id}, returning CONFIRMING_GENERATION")
                            return CONFIRMING_GENERATION
                        except Exception as send_error:
                            logger.error(f"❌ Error showing confirmation button: {send_error}", exc_info=True)
                            return INPUTTING_PARAMS
                except Exception as e:
                    logger.error(f"Error after image input: {e}", exc_info=True)
                    await update.message.reply_text(
                        f"❌ <b>Ошибка</b>\n\n"
                        f"Не удалось перейти к следующему шагу.\n"
                        f"Попробуйте еще раз или используйте /cancel.",
                        parse_mode='HTML'
                    )
        elif image_count < min(max_items, 8):
            keyboard = [
                [InlineKeyboardButton("📷 Добавить еще", callback_data="add_image")],
                [InlineKeyboardButton("✅ Готово", callback_data="image_done")]
            ]
            await update.message.reply_text(
                f"✅ Изображение {image_count} добавлено!\n\n"
                f"Загружено: {image_count}/{max_items}\n\n"
                f"Добавить еще изображение или продолжить?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"✅ Изображение {image_count} добавлено!\n\n"
                f"Достигнут максимум ({max_items} изображений). Продолжаю..."
            )
            if 'params' not in session:
                session['params'] = {}
            session['params'][image_param_name] = session[image_param_name]
            session['waiting_for'] = None
            # Move to next parameter
            try:
                next_param_result = await start_next_parameter(update, context, user_id)
                if next_param_result:
                    return next_param_result
                # КРИТИЧНО: Если start_next_parameter вернул None, проверяем что было отправлено сообщение
                await guard.check_and_ensure_response(update, context)
            except Exception as e:
                logger.error(f"Error after image input: {e}")
                # Отправляем сообщение об ошибке
                await update.message.reply_text(
                    f"❌ Ошибка при переходе к следующему параметру: {str(e)}",
                    parse_mode='HTML'
                )
                track_outgoing_action(update_id)
        
        return INPUTTING_PARAMS
    
    # Handle text input
    if not update.message.text:
        await update.message.reply_text("❌ Пожалуйста, отправьте текстовое сообщение.")
        track_outgoing_action(update_id)
        return INPUTTING_PARAMS

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Сообщение не должно быть пустым. Попробуйте снова.")
        track_outgoing_action(update_id)
        return INPUTTING_PARAMS
    
    # Handle /cancel command
    if text.lower() in ['/cancel', 'отмена', 'cancel']:
        user_lang = get_user_language(user_id)
        if user_id in user_sessions:
            del user_sessions[user_id]
        keyboard = [[InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]]
        await update.message.reply_text(
            t('msg_operation_cancelled', lang=user_lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return ConversationHandler.END
    
    # ==================== TASK 1: Гарантия ответа на каждый ввод ====================
    # Сразу отправляем подтверждение, чтобы пользователь не думал, что бот завис
    try:
        await update.message.reply_text("✅ Принято, обрабатываю...", parse_mode='HTML')
        # NO-SILENCE GUARD: Track outgoing action
        track_outgoing_action(update_id)
    except Exception as e:
        logger.warning(f"Не удалось отправить подтверждение: {e}")
    
    # ==================== TASK 1: Try/except вокруг обработки текста ====================
    try:
        # If waiting for text input (prompt or other text parameter)
        waiting_for = session.get('waiting_for')
        if waiting_for:
            model_info = session.get('model_info', {})
            model_id = session.get('model_id', '')
            input_params = model_info.get('input_params', {})
            user_lang = get_user_language(user_id)
            current_param = session.get('current_param', waiting_for)
            param_info = properties.get(current_param, {})
            max_length = param_info.get('max_length')
            if current_param == 'prompt' and not max_length:
                max_length = 1000
            
            # Validate max length
            if max_length and len(text) > max_length:
                await update.message.reply_text(
                    f"❌ Текст слишком длинный (макс. {max_length} символов). Попробуйте снова."
                )
                track_outgoing_action(update_id)
                return INPUTTING_PARAMS
        
            # For language_code, convert common language names to codes
            if current_param == 'language_code':
                lang_lower = text.lower()
                lang_map = {
                    'русский': 'ru',
                    'russian': 'ru',
                    'английский': 'en',
                    'english': 'en',
                    'eng': 'en',
                    'немецкий': 'de',
                    'german': 'de',
                    'французский': 'fr',
                    'french': 'fr',
                    'испанский': 'es',
                    'spanish': 'es',
                    'итальянский': 'it',
                    'italian': 'it',
                    'китайский': 'zh',
                    'chinese': 'zh',
                    'японский': 'ja',
                    'japanese': 'ja',
                    'корейский': 'ko',
                    'korean': 'ko'
                }
                if lang_lower in lang_map:
                    text = lang_map[lang_lower]
                # If it's already a code (2-3 letters), convert to lowercase
                elif len(text) <= 5 and text.replace('-', '').replace('_', '').isalpha():
                    text = text.lower()
            
            # For video_url in sora-watermark-remover, validate URL format
            if current_param == 'video_url' and model_id == 'sora-watermark-remover':
                # Validate URL format (should contain sora.chatgpt.com)
                if 'sora.chatgpt.com' not in text:
                    await update.message.reply_text(
                        f"❌ <b>Неверный формат URL</b>\n\n"
                        f"URL видео должен быть от OpenAI Sora 2 (должен содержать sora.chatgpt.com).\n\n"
                        f"Пример: https://sora.chatgpt.com/p/s_...\n\n"
                        f"Попробуйте снова.",
                        parse_mode='HTML'
                    )
                    return INPUTTING_PARAMS
                
                # Additional validation: check if URL starts with http:// or https://
                if not (text.startswith('http://') or text.startswith('https://')):
                    await update.message.reply_text(
                        f"❌ <b>Неверный формат URL</b>\n\n"
                        f"URL должен начинаться с http:// или https://\n\n"
                        f"Попробуйте снова.",
                        parse_mode='HTML'
                    )
                    return INPUTTING_PARAMS
            
            # Set parameter value
            if 'params' not in session:
                session['params'] = {}
            session['params'][current_param] = text
            session['waiting_for'] = None
            session['current_param'] = None
            session['language_code_custom'] = False
            _record_param_history(session, current_param)
            logger.info(
                "🧩 PARAM_SET: action_path=text_input model_id=%s waiting_for=%s current_param=%s outcome=stored",
                model_id,
                session.get('waiting_for'),
                current_param,
            )
            
            # Confirm parameter was set (КРИТИЧНО: это второй ответ после "✅ Принято, обрабатываю...")
            display_value = text[:100] + '...' if len(text) > 100 else text
            await update.message.reply_text(
                f"✅ <b>{current_param}</b> установлен!\n\n"
                f"Значение: {display_value}",
                parse_mode='HTML'
            )
            track_outgoing_action(update_id)  # Отслеживаем второй ответ
            
            # If prompt was entered and model supports image/audio input, offer next steps
            if current_param == 'prompt':
                # IMPORTANT: z-image does NOT support image input (text-to-image only)
                if model_id == "z-image":
                    session['has_image_input'] = False
                    session['waiting_for'] = None

                    # Check for audio_url requirement (unlikely for z-image, but check anyway)
                    if 'audio_url' in input_params or 'audio_input' in input_params:
                        audio_param_name = 'audio_url' if 'audio_url' in input_params else 'audio_input'
                        audio_required = input_params.get(audio_param_name, {}).get('required', False)
                        
                        if audio_required:
                            keyboard = [
                                [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")],
                                [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                            ]
                            free_counter_line = await _resolve_free_counter_line(
                                user_id,
                                user_lang,
                                correlation_id,
                                action_path=f"param_prompt:{audio_param_name}",
                                sku_id=session.get("sku_id"),
                            )
                            audio_text = _append_free_counter_text(
                                "🎤 <b>Загрузите аудио-файл для транскрибации</b>\n\n"
                                "Отправьте аудио-файл (MP3, WAV, OGG, M4A, FLAC, AAC, WMA, MPEG).\n"
                                "Максимальный размер: 200 MB",
                                free_counter_line,
                            )
                            await update.message.reply_text(
                                audio_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='HTML'
                            )
                            session['waiting_for'] = audio_param_name
                            session['current_param'] = audio_param_name
                            return INPUTTING_PARAMS
                    
                    try:
                        next_param_result = await start_next_parameter(update, context, user_id)
                        if next_param_result:
                            return next_param_result
                        await guard.check_and_ensure_response(update, context)
                    except Exception as e:
                        logger.error(f"Error in start_next_parameter for z-image: {e}", exc_info=True)
                        await update.message.reply_text(
                            "❌ Ошибка при переходе к следующему параметру. Попробуйте снова.",
                            parse_mode='HTML'
                        )
                        track_outgoing_action(update_id)
                    return INPUTTING_PARAMS

                # Check for audio_url requirement (for non-z-image models)
                if 'audio_url' in input_params or 'audio_input' in input_params:
                    audio_param_name = 'audio_url' if 'audio_url' in input_params else 'audio_input'
                    audio_required = input_params.get(audio_param_name, {}).get('required', False)
                    
                    if audio_required:
                        keyboard = [
                            [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")],
                            [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                        ]
                        free_counter_line = await _resolve_free_counter_line(
                            user_id,
                            user_lang,
                            correlation_id,
                            action_path=f"param_prompt:{audio_param_name}",
                            sku_id=session.get("sku_id"),
                        )
                        audio_text = _append_free_counter_text(
                            "🎤 <b>Загрузите аудио-файл для транскрибации</b>\n\n"
                            "Отправьте аудио-файл (MP3, WAV, OGG, M4A, FLAC, AAC, WMA, MPEG).\n"
                            "Максимальный размер: 200 MB",
                            free_counter_line,
                        )
                        await update.message.reply_text(
                            audio_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        session['waiting_for'] = audio_param_name
                        session['current_param'] = audio_param_name
                        return INPUTTING_PARAMS
                    else:
                        keyboard = [
                            [InlineKeyboardButton("🎤 Загрузить аудио (опционально)", callback_data="add_audio")],
                            [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_audio")],
                            [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")],
                            [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")]
                        ]
                        free_counter_line = await _resolve_free_counter_line(
                            user_id,
                            user_lang,
                            correlation_id,
                            action_path=f"param_prompt:{audio_param_name}",
                            sku_id=session.get("sku_id"),
                        )
                        audio_prompt = _append_free_counter_text(
                            "🎤 <b>Вы можете загрузить аудио-файл (опционально)</b>\n\n"
                            "Отправьте аудио-файл или нажмите 'Пропустить', чтобы продолжить.",
                            free_counter_line,
                        )
                        await update.message.reply_text(
                            audio_prompt,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        session['waiting_for'] = None
                        return INPUTTING_PARAMS

                if session.get('has_image_input'):
                    image_required = False
                    if 'image_urls' in input_params:
                        image_required = input_params['image_urls'].get('required', False)
                    elif 'image_input' in input_params:
                        image_required = input_params['image_input'].get('required', False)
                    optional_media = session.get("optional_media_params", [])
                    if optional_media:
                        image_required = False
                    
                    if image_required:
                        keyboard = [
                            [InlineKeyboardButton("📷 Загрузить изображение", callback_data="add_image")],
                            [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                        ]
                        image_param_name = 'image_urls' if 'image_urls' in input_params else 'image_input'
                        free_counter_line = await _resolve_free_counter_line(
                            user_id,
                            user_lang,
                            correlation_id,
                            action_path=f"param_prompt:{image_param_name}",
                            sku_id=session.get("sku_id"),
                        )
                        image_text = _append_free_counter_text(
                            "📷 <b>Загрузите изображение для редактирования</b>\n\n"
                            "Отправьте фото, которое хотите отредактировать.",
                            free_counter_line,
                        )
                        await update.message.reply_text(
                            image_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        session['waiting_for'] = image_param_name
                        session['current_param'] = image_param_name
                        return INPUTTING_PARAMS
                    else:
                        if session.get("image_ref_prompt"):
                            keyboard = [
                                [
                                    InlineKeyboardButton("✅ Да", callback_data="add_image"),
                                    InlineKeyboardButton("❌ Нет", callback_data="skip_image"),
                                ],
                                [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")],
                            ]
                            free_counter_line = await _resolve_free_counter_line(
                                user_id,
                                user_lang,
                                correlation_id,
                                action_path="param_prompt:image_ref",
                                sku_id=session.get("sku_id"),
                            )
                            image_prompt = _append_free_counter_text(
                                "📷 <b>Добавить реф-картинку?</b>\n\n"
                                "Реф-картинка поможет уточнить стиль или детали.\n"
                                "Вы можете пропустить этот шаг.",
                                free_counter_line,
                            )
                            await update.message.reply_text(
                                image_prompt,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='HTML'
                            )
                        else:
                            keyboard = [
                                [InlineKeyboardButton("📷 Добавить изображение", callback_data="add_image")],
                                [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_image")],
                                [InlineKeyboardButton(_get_reset_step_label(user_lang), callback_data="reset_step")]
                            ]
                            free_counter_line = await _resolve_free_counter_line(
                                user_id,
                                user_lang,
                                correlation_id,
                                action_path="param_prompt:image_optional",
                                sku_id=session.get("sku_id"),
                            )
                            image_prompt = _append_free_counter_text(
                                "📷 <b>Хотите добавить изображение?</b>\n\n"
                                "Вы можете загрузить изображение для использования как референс или для трансформации.\n"
                                "Или пропустите этот шаг.",
                                free_counter_line,
                            )
                            await update.message.reply_text(
                                image_prompt,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='HTML'
                            )
                        session['waiting_for'] = None
                        return INPUTTING_PARAMS
                
                # Check if there are more parameters
                required = session.get('required', [])
                params = session.get('params', {})
                properties = session.get('properties', {})
                model_info = session.get('model_info', {})
                input_params = model_info.get('input_params', {})
                
                # CRITICAL: Apply default values BEFORE checking missing parameters
                # This ensures parameters with default values are automatically applied
                for param_name, param_info in input_params.items():
                    if param_name not in params:
                        default_value = param_info.get('default')
                        if default_value is not None:
                            params[param_name] = default_value
                            logger.info(f"✅ Applied default value for {param_name}={default_value} for {model_id}")
                
                # Don't exclude image_input/image_urls/audio_url/audio_input from missing if they're required but not yet provided
                # Only exclude them if they're already in params (uploaded)
                excluded_params = ['prompt']  # Always exclude prompt as it's already processed
                # Only exclude image/audio params if they're already set in params
                if 'image_input' in params or (session.get('image_input') and len(session.get('image_input', [])) > 0):
                    excluded_params.append('image_input')
                if 'image_urls' in params or (session.get('image_urls') and len(session.get('image_urls', [])) > 0):
                    excluded_params.append('image_urls')
                if 'mask_input' in params or (session.get('mask_input') and len(session.get('mask_input', [])) > 0):
                    excluded_params.append('mask_input')
                if 'reference_image_input' in params or (session.get('reference_image_input') and len(session.get('reference_image_input', [])) > 0):
                    excluded_params.append('reference_image_input')
                if 'audio_url' in params or session.get('audio_url'):
                    excluded_params.append('audio_url')
                if 'audio_input' in params or session.get('audio_input'):
                    excluded_params.append('audio_input')
                missing = [p for p in required if p not in params and p not in excluded_params]
                
                # CRITICAL: Ensure image_input/image_urls/mask_input/reference_image_input are considered missing if required and not in params
                # Also check if they're in session but not in params (auto-fix)
                for image_param in ['image_input', 'image_urls', 'mask_input', 'reference_image_input']:
                    if image_param in input_params and input_params[image_param].get('required', False):
                        if image_param not in params:
                            # Check if it's in session but not in params (auto-fix)
                            if image_param in session and session.get(image_param):
                                logger.info(f"⚠️ {image_param} in session but not in params for {model_id}. Auto-fixing...")
                                if isinstance(session[image_param], list):
                                    session['params'][image_param] = session[image_param].copy()
                                else:
                                    session['params'][image_param] = [session[image_param]]
                                logger.info(f"✅ Fixed: {image_param} added to params")
                            else:
                                # Truly missing
                                if image_param not in excluded_params:
                                    missing.append(image_param)
                                    logger.warning(f"⚠️ Required {image_param} missing for {model_id}")
                        else:
                            # Already in params, verify it's not empty
                            if not params.get(image_param):
                                logger.warning(f"⚠️ {image_param} in params but empty for {model_id}")
                                if image_param not in excluded_params:
                                    missing.append(image_param)
                
                # For elevenlabs/speech-to-text, also check optional parameters
                model_id = session.get('model_id', '')
                if model_id == "elevenlabs/speech-to-text":
                    # Check optional parameters that haven't been set yet
                    for opt_param in ['language_code', 'tag_audio_events', 'diarize']:
                        if opt_param in properties and opt_param not in params:
                            missing.append(opt_param)
                
                if missing:
                    # Move to next parameter
                    try:
                        # Small delay to show confirmation
                        await asyncio.sleep(0.5)
                        next_param_result = await start_next_parameter(update, context, user_id)
                        if next_param_result:
                            return next_param_result
                        # КРИТИЧНО: Если start_next_parameter вернул None, проверяем что было отправлено сообщение
                        # Если нет - отправляем fallback через NO-SILENCE GUARD
                        await guard.check_and_ensure_response(update, context)
                    except Exception as e:
                        logger.error(f"Error starting next parameter: {e}", exc_info=True)
                        await update.message.reply_text(
                            f"❌ Ошибка при переходе к следующему параметру: {str(e)}",
                            parse_mode='HTML'
                        )
                        track_outgoing_action(update_id)
                        return INPUTTING_PARAMS
                else:
                    # All parameters collected, show confirmation
                    model_name = session.get('model_info', {}).get('name', 'Unknown')
                    model_id = session.get('model_id', '')
                    params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in params.items()])
                    
                    # КРИТИЧНО: Всегда показываем цену или информацию о бесплатной генерации
                    is_admin_user = get_is_admin(user_id)
                    sku_id = session.get("sku_id", "")
                    is_free = await is_free_generation_available(user_id, sku_id)
                    free_info = ""
                    if is_free:
                        remaining = await get_user_free_generations_remaining(user_id)
                        free_info = f"\n\n🎁 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ!</b>\n"
                        free_info += f"Осталось бесплатных: {remaining}/{FREE_GENERATIONS_PER_DAY} в день"
                    else:
                        # КРИТИЧНО: Всегда показываем цену
                        price = calculate_price_rub(model_id, params, is_admin_user)
                        if price is None:
                            blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
                            await update.message.reply_text(blocked_text, parse_mode="HTML")
                            return INPUTTING_PARAMS
                        price_str = format_rub_amount(price)
                        if is_admin_user:
                            free_info = f"\n\n💰 <b>Стоимость:</b> Безлимит (цена: {price_str})"
                        else:
                            free_info = f"\n\n💰 <b>Стоимость:</b> {price_str}"
                    
                    user_lang = get_user_language(user_id)
                    correlation_id = ensure_correlation_id(update, context)
                    free_counter_line = ""
                    try:
                        free_counter_line = await get_free_counter_line(
                            user_id,
                            user_lang=user_lang,
                            correlation_id=correlation_id,
                            action_path="confirm_screen",
                            sku_id=sku_id,
                        )
                    except Exception as exc:
                        logger.warning("Failed to resolve free counter line: %s", exc)
                    keyboard = [
                        [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                        [
                            InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                            InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                        ],
                        [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                    ]
                    
                    await update.message.reply_text(
                        _append_free_counter_text(
                            (
                                f"📋 <b>Подтверждение:</b>\n\n"
                                f"Модель: <b>{model_name}</b>\n"
                                f"Параметры:\n{params_text}{free_info}\n\n"
                                f"Продолжить генерацию?"
                            ),
                            free_counter_line,
                        ),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                    return CONFIRMING_GENERATION
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке текста в input_parameters: {e}", exc_info=True)
        # Отвечаем пользователю понятным сообщением
        try:
            user_lang = get_user_language(user_id)
            keyboard = [
                [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")],
                [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
            ]
            await update.message.reply_text(
                f"❌ <b>Ошибка при обработке ввода</b>\n\n"
                f"Попробуйте:\n"
                f"• Вернуться в главное меню\n"
                f"• Начать заново с выбора модели\n"
                f"• Отменить операцию",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
        except Exception as reply_error:
            logger.error(f"❌ Не удалось отправить сообщение об ошибке: {reply_error}", exc_info=True)
        track_outgoing_action(update_id)  # Отслеживаем ответ об ошибке
        return ConversationHandler.END
    
    # ==================== TASK 1: FALLBACK для waiting_for == None ====================
    # Если waiting_for не установлен, но пришёл текст - пытаемся понять, что делать
    if not waiting_for:
        try:
            # Сразу отправляем подтверждение, чтобы пользователь не думал, что бот завис
            await update.message.reply_text(
                "✅ Принято, обрабатываю...",
                parse_mode='HTML'
            )
            
            # Проверяем, есть ли у модели prompt в properties/input_params
            model_id = session.get('model_id')
            model_info = session.get('model_info', {})
            properties = session.get('properties', {})
            input_params = model_info.get('input_params', {})
            params = session.get('params', {})
            
            # Если у модели есть prompt в input_params и prompt ещё не в session['params']
            if 'prompt' in input_params and 'prompt' not in params:
                # Трактуем сообщение как prompt и продолжаем пайплайн
                logger.info(f"🔧 AUTO-FIX: Text received but waiting_for=None, treating as prompt for model {model_id}")
                
                # Устанавливаем prompt
                if 'params' not in session:
                    session['params'] = {}
                session['params']['prompt'] = text
                session['waiting_for'] = None
                session['current_param'] = None
                _record_param_history(session, 'prompt')
                
                # Продолжаем пайплайн как обычно
                # Проверяем, есть ли ещё параметры
                required = session.get('required', [])
                missing = [p for p in required if p not in params and p != 'prompt']
                
                if missing:
                    # Есть ещё параметры - переходим к следующему
                    try:
                        next_param_result = await start_next_parameter(update, context, user_id)
                        if next_param_result:
                            return next_param_result
                        # КРИТИЧНО: Если start_next_parameter вернул None, проверяем что было отправлено сообщение
                        await guard.check_and_ensure_response(update, context)
                    except Exception as e:
                        logger.error(f"Error starting next parameter after auto-fix prompt: {e}", exc_info=True)
                        # Отправляем сообщение об ошибке
                        await update.message.reply_text(
                            f"❌ Ошибка при переходе к следующему параметру: {str(e)}",
                            parse_mode='HTML'
                        )
                        track_outgoing_action(update_id)
                        return INPUTTING_PARAMS
                else:
                    # Все параметры собраны - показываем подтверждение
                    try:
                        model_name = model_info.get('name', 'Unknown')
                        params_text = "\n".join([f"  • {k}: {str(v)[:50]}..." for k, v in params.items()])
                        
                        is_admin_user = get_is_admin(user_id)
                        sku_id = session.get("sku_id", "")
                        is_free = await is_free_generation_available(user_id, sku_id)
                        free_info = ""
                        if is_free:
                            remaining = await get_user_free_generations_remaining(user_id)
                            free_info = f"\n\n🎁 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ!</b>\n"
                            free_info += f"Осталось бесплатных: {remaining}/{FREE_GENERATIONS_PER_DAY} в день"
                        else:
                            price = calculate_price_rub(model_id, params, is_admin_user)
                            if price is None:
                                logger.error("Missing price for refund on model %s", model_id)
                                price = 0.0
                            if price is None:
                                logger.error("Missing price for refund on model %s", model_id)
                                price = 0.0
                            if price is None:
                                blocked_text = format_pricing_blocked_message(model_id, user_lang=user_lang)
                                await update.message.reply_text(blocked_text, parse_mode="HTML")
                                return INPUTTING_PARAMS
                            price_str = format_rub_amount(price)
                            free_info = f"\n\n💰 <b>Стоимость:</b> {price_str}"
                        
                        user_lang = get_user_language(user_id)
                        keyboard = [
                            [InlineKeyboardButton(t('btn_confirm_generate', lang=user_lang), callback_data="confirm_generate")],
                            [InlineKeyboardButton(_get_settings_label(user_lang), callback_data="show_parameters")],
                            [
                                InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step"),
                                InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")
                            ],
                            [InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")]
                        ]
                        
                        await update.message.reply_text(
                            f"📋 <b>Подтверждение:</b>\n\n"
                            f"Модель: <b>{model_name}</b>\n"
                            f"Параметры:\n{params_text}{free_info}\n\n"
                            f"Продолжить генерацию?",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
                        return CONFIRMING_GENERATION
                    except Exception as e:
                        logger.error(f"Error showing confirmation after auto-fix prompt: {e}", exc_info=True)
            
            # Если не удалось автоматически определить - отвечаем понятным сообщением
            user_lang = get_user_language(user_id)
            settings_label = _get_settings_label(user_lang)
            keyboard = []
            if session.get('properties'):
                keyboard.append([InlineKeyboardButton(settings_label, callback_data="show_parameters")])
            if session.get('param_history'):
                keyboard.append([InlineKeyboardButton(t('btn_back', lang=user_lang), callback_data="back_to_previous_step")])
            keyboard.append([InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")])
            keyboard.append([InlineKeyboardButton(t('btn_cancel', lang=user_lang), callback_data="cancel")])
            
            model_name = model_info.get('name', 'Unknown')
            await update.message.reply_text(
                (
                    "💡 <b>Сейчас я жду действия через кнопки</b>\n\n"
                    f"🤖 <b>Модель:</b> {model_name}\n\n"
                    "Пожалуйста:\n"
                    "• Откройте параметры и выберите, что изменить\n"
                    "• Или вернитесь в меню\n"
                    "• Или отмените операцию\n\n"
                    "🧪 Пример: нажмите «⚙️ Параметры», чтобы изменить значения."
                    if user_lang == 'ru'
                    else (
                        "💡 <b>Please use buttons to continue</b>\n\n"
                        f"🤖 <b>Model:</b> {model_name}\n\n"
                        "Please:\n"
                        "• Open parameters and choose what to change\n"
                        "• Or return to the main menu\n"
                        "• Or cancel the operation\n\n"
                        "🧪 Example: tap “⚙️ Parameters” to edit values."
                    )
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            track_outgoing_action(update_id)  # Отслеживаем fallback ответ
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в fallback обработке текста: {e}", exc_info=True)
            # В случае ошибки всё равно отвечаем пользователю
            try:
                user_lang = get_user_language(user_id)
                keyboard = [
                    [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")]
                ]
                await update.message.reply_text(
                    "❌ Произошла ошибка. Вернитесь в главное меню.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                track_outgoing_action(update_id)  # Отслеживаем ответ об ошибке
            except:
                pass
            return ConversationHandler.END
    
    # ==================== NO-SILENCE GUARD: КРИТИЧЕСКАЯ ПРОВЕРКА ====================
    # Если мы дошли сюда без отправки сообщения - это КРИТИЧЕСКИЙ БАГ
    # ОБЯЗАТЕЛЬНО отправляем fallback
    try:
        outgoing_count = guard.outgoing_actions.get(update_id, 0)
        if outgoing_count > 0:
            logger.info(
                "✅ NO-SILENCE: action_path=input_parameters_end model_id=%s waiting_for=%s current_param=%s outcome=already_replied",
                session.get('model_id'),
                session.get('waiting_for'),
                session.get('current_param'),
            )
            return INPUTTING_PARAMS
        logger.warning(f"⚠️⚠️⚠️ NO-SILENCE VIOLATION: input_parameters reached end without response for user {user_id}, waiting_for={waiting_for}")
        await guard.check_and_ensure_response(update, context)
    except Exception as e:
        logger.error(f"❌ CRITICAL: Failed to check NO-SILENCE in input_parameters: {e}", exc_info=True)
        # Если даже check_and_ensure_response упал - отправляем напрямую
        try:
            user_lang = get_user_language(user_id) if user_id else 'ru'
            keyboard = [
                [InlineKeyboardButton(t('btn_home', lang=user_lang), callback_data="back_to_menu")],
                [InlineKeyboardButton("🔄 Повторить", callback_data="back_to_menu")]
            ]
            await update.message.reply_text(
                "⚠️ <b>Я не смог обработать ваш ввод.</b>\n\n"
                "Вернитесь в главное меню и попробуйте снова.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            track_outgoing_action(update_id)
        except Exception as e2:
            logger.error(f"❌ CRITICAL: Failed to send NO-SILENCE fallback in input_parameters: {e2}", exc_info=True)
    # ==================== END NO-SILENCE GUARD ====================
    
    return INPUTTING_PARAMS


async def start_generation_directly(
    user_id: int,
    model_id: str,
    params: dict,
    model_info: dict,
    status_message,
    context: ContextTypes.DEFAULT_TYPE
):
    """Start generation directly without callback query. Used for auto-start after photo upload."""
    logger.info(f"🚀 start_generation_directly called for user {user_id}, model {model_id}")
    
    is_admin_user = get_is_admin(user_id)
    correlation_id = get_correlation_id(None, user_id)
    chat_id = user_id
    
    # Check if user is blocked
    if not is_admin_user and is_user_blocked(user_id):
        await status_message.edit_text(
            "❌ <b>Ваш аккаунт заблокирован</b>\n\n"
            "Обратитесь к администратору для разблокировки.",
            parse_mode='HTML'
        )
        return ConversationHandler.END


async def active_session_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route active sessions to input_parameters before generic handlers."""
    from telegram.ext import ApplicationHandlerStop
    from app.observability.no_silence_guard import get_no_silence_guard

    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return
    session_store = get_session_store(context)
    session = session_store.get(user_id)
    waiting_for = session.get("waiting_for") if isinstance(session, dict) else None
    current_param = session.get("current_param") if isinstance(session, dict) else None
    if not waiting_for and not current_param:
        return

    _log_route_decision_once(
        update,
        context,
        waiting_for=waiting_for or current_param,
        chosen_handler="active_session_router->input_parameters",
        reason="waiting_for_active",
    )
    guard = get_no_silence_guard()
    try:
        await input_parameters(update, context)
    except Exception as exc:
        logger.error("Active session router failed: %s", exc, exc_info=True)
        await guard.check_and_ensure_response(update, context)
    raise ApplicationHandlerStop


async def global_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Latency wrapper for global text routing."""
    start_ts = time.monotonic()
    try:
        await _global_text_router_impl(update, context)
    finally:
        _log_handler_latency("global_text_router", start_ts, update)


async def _global_text_router_impl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global router for TEXT messages - shows main menu when no active session."""
    from telegram.ext import ApplicationHandlerStop
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action

    guard = get_no_silence_guard()
    update_id = update.update_id
    user_id = update.effective_user.id if update.effective_user else None
    if _should_dedupe_update(
        update,
        context,
        action="TEXT_ROUTER",
        action_path="global_text_router",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    ):
        return

    session_store = get_session_store(context)
    session = session_store.get(user_id) if user_id else None
    waiting_for = session.get("waiting_for") if isinstance(session, dict) else None
    current_param = session.get("current_param") if isinstance(session, dict) else None
    if waiting_for or current_param:
        return

    if isinstance(session, dict) and session.get("model_id") and session.get("properties"):
        _log_route_decision_once(
            update,
            context,
            waiting_for=None,
            chosen_handler="global_text_router->input_parameters",
            reason="active_model_session_without_waiting_for",
        )
        logger.info(
            "🔀 GLOBAL_TEXT_ROUTER: Active model session without waiting_for, routing to input_parameters"
        )
        await input_parameters(update, context)
        raise ApplicationHandlerStop

    _log_route_decision_once(
        update,
        context,
        waiting_for=None,
        chosen_handler="global_text_router->main_menu",
        reason="no_active_session",
    )
    logger.info("🔀 GLOBAL_TEXT_ROUTER: No waiting_for, showing main menu")
    try:
        await ensure_main_menu(update, context, source="global_text_router", prefer_edit=True)
        track_outgoing_action(update_id)
    except Exception as exc:
        logger.error("Error in global_text_router fallback: %s", exc, exc_info=True)
        await guard.check_and_ensure_response(update, context)
    raise ApplicationHandlerStop


async def global_photo_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Latency wrapper for global photo routing."""
    start_ts = time.monotonic()
    try:
        await _global_photo_router_impl(update, context)
    finally:
        _log_handler_latency("global_photo_router", start_ts, update)


async def _global_photo_router_impl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global router for PHOTO messages - routes to input_parameters if waiting_for expects image."""
    from telegram.ext import ApplicationHandlerStop
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action

    guard = get_no_silence_guard()
    update_id = update.update_id
    user_id = update.effective_user.id if update.effective_user else None
    if _should_dedupe_update(
        update,
        context,
        action="PHOTO_ROUTER",
        action_path="global_photo_router",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    ):
        return

    session_store = get_session_store(context)
    session = session_store.get(user_id) if user_id else None
    if isinstance(session, dict):
        waiting_for = session.get('waiting_for')
        current_param = session.get('current_param', waiting_for)
        if waiting_for and current_param in ['image_input', 'image_urls', 'mask_input', 'reference_image_input']:
            try:
                await update.message.reply_text("⏳ Принято. Обрабатываю фото…", parse_mode='HTML')
                track_outgoing_action(update_id)
            except Exception as exc:
                logger.warning("Could not send instant ACK: %s", exc)
            logger.info("🔀 GLOBAL_PHOTO_ROUTER: Routing to input_parameters (waiting_for=%s)", waiting_for)
            _log_route_decision_once(
                update,
                context,
                waiting_for=waiting_for,
                chosen_handler="global_photo_router->input_parameters",
                reason="waiting_for_image",
            )
            await input_parameters(update, context)
            raise ApplicationHandlerStop

    _log_route_decision_once(
        update,
        context,
        waiting_for=None,
        chosen_handler="global_photo_router->main_menu",
        reason="no_active_session",
    )
    logger.info("🔀 GLOBAL_PHOTO_ROUTER: Not expecting photo, showing guidance")
    try:
        await show_main_menu(update, context, source="global_photo_router")
        track_outgoing_action(update_id)
    except Exception as exc:
        logger.error("Error in global_photo_router fallback: %s", exc, exc_info=True)
        await guard.check_and_ensure_response(update, context)
    raise ApplicationHandlerStop


async def global_audio_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global router for AUDIO/VOICE messages - routes to input_parameters if waiting_for expects audio."""
    from telegram.ext import ApplicationHandlerStop
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action

    guard = get_no_silence_guard()
    update_id = update.update_id
    user_id = update.effective_user.id if update.effective_user else None
    if _should_dedupe_update(
        update,
        context,
        action="AUDIO_ROUTER",
        action_path="global_audio_router",
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else None,
    ):
        return

    session_store = get_session_store(context)
    session = session_store.get(user_id) if user_id else None
    if isinstance(session, dict):
        waiting_for = session.get('waiting_for')
        current_param = session.get('current_param', waiting_for)
        if waiting_for and current_param in ['audio_url', 'audio_input']:
            try:
                await update.message.reply_text("⏳ Принято. Обрабатываю аудио…", parse_mode='HTML')
                track_outgoing_action(update_id)
            except Exception as exc:
                logger.warning("Could not send instant ACK: %s", exc)
            logger.info("🔀 GLOBAL_AUDIO_ROUTER: Routing to input_parameters (waiting_for=%s)", waiting_for)
            _log_route_decision_once(
                update,
                context,
                waiting_for=waiting_for,
                chosen_handler="global_audio_router->input_parameters",
                reason="waiting_for_audio",
            )
            await input_parameters(update, context)
            raise ApplicationHandlerStop

    _log_route_decision_once(
        update,
        context,
        waiting_for=None,
        chosen_handler="global_audio_router->main_menu",
        reason="no_active_session",
    )
    logger.info("🔀 GLOBAL_AUDIO_ROUTER: Not expecting audio, showing guidance")
    try:
        await ensure_main_menu(update, context, source="global_audio_router", prefer_edit=True)
        track_outgoing_action(update_id)
    except Exception as exc:
        logger.error("Error in global_audio_router fallback: %s", exc, exc_info=True)
        await guard.check_and_ensure_response(update, context)
    raise ApplicationHandlerStop


async def unhandled_update_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Final fallback for any text/photo/audio/document update to prevent silence."""
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action

    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    correlation_id = ensure_correlation_id(update, context)
    session_store = get_session_store(context)
    session_snapshot = session_store.snapshot(user_id)
    session = session_store.get(user_id) if user_id else None
    waiting_for = session.get("waiting_for") if isinstance(session, dict) else None
    current_param = session.get("current_param") if isinstance(session, dict) else None
    update_type = _resolve_update_type(update)

    if waiting_for or current_param:
        if update.message:
            _log_route_decision_once(
                update,
                context,
                waiting_for=waiting_for or current_param,
                chosen_handler="unhandled_update_fallback->input_parameters",
                reason="waiting_for_in_fallback",
            )
            guard = get_no_silence_guard()
            try:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update.update_id,
                    action="UNHANDLED_UPDATE_FALLBACK_SAFE",
                    action_path="fallback",
                    stage="UI_ROUTER",
                    outcome="routed_to_input_parameters",
                    param={
                        "update_type": update_type,
                        "waiting_for": waiting_for,
                        "current_param": current_param,
                    },
                )
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update.update_id,
                    action="UX_UNHANDLED_UPDATE_RECOVERED",
                    action_path="fallback",
                    stage="UI_ROUTER",
                    outcome="routed_to_input_parameters",
                    param={
                        "update_type": update_type,
                        "waiting_for": waiting_for,
                        "current_param": current_param,
                    },
                )
                await input_parameters(update, context)
                return
            except Exception as exc:
                logger.error("Fallback routing failed: %s", exc, exc_info=True)
                await guard.check_and_ensure_response(update, context)
                return
        user_lang = get_user_language(user_id) if user_id else "ru"
        param_label = waiting_for or current_param or "параметр"
        message_text = (
            f"Я жду ввод параметра <b>{param_label}</b>."
            if user_lang == "ru"
            else f"I'm waiting for parameter <b>{param_label}</b>."
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="UNHANDLED_UPDATE_FALLBACK_SAFE",
            action_path="fallback",
            stage="UI_ROUTER",
            outcome="waiting_for_param",
            param={
                "update_type": update_type,
                "waiting_for": waiting_for,
                "current_param": current_param,
            },
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="UX_UNHANDLED_UPDATE_RECOVERED",
            action_path="fallback",
            stage="UI_ROUTER",
            outcome="waiting_for_param",
            param={
                "update_type": update_type,
                "waiting_for": waiting_for,
                "current_param": current_param,
            },
        )
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode="HTML")
            track_outgoing_action(update.update_id, action_type="fallback")
        return

    logger.warning(
        "UNHANDLED_UPDATE correlation_id=%s user_id=%s update_type=%s session=%s",
        correlation_id,
        user_id,
        update_type,
        session_snapshot,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="UNHANDLED_UPDATE",
        action_path="fallback",
        stage="UI_ROUTER",
        outcome="fallback",
        fix_hint="Ensure ConversationHandler and active-session router precede fallback handlers",
        param={
            "update_type": update_type,
            "session": session_snapshot,
            "waiting_for": waiting_for,
            "current_param": current_param,
        },
    )

    _log_route_decision_once(
        update,
        context,
        waiting_for=None,
        chosen_handler="unhandled_update_fallback->main_menu",
        reason="no_active_session",
    )
    logger.warning(
        "FIX_HINT fallback_triggered check handler order and session waiting_for state"
    )
    guard = get_no_silence_guard()
    try:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="UNHANDLED_UPDATE_FALLBACK_SAFE",
            action_path="fallback",
            stage="UI_ROUTER",
            outcome="menu_shown",
            param={
                "update_type": update_type,
                "waiting_for": waiting_for,
                "current_param": current_param,
            },
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="UX_UNHANDLED_UPDATE_RECOVERED",
            action_path="fallback",
            stage="UI_ROUTER",
            outcome="menu_shown",
            param={
                "update_type": update_type,
                "waiting_for": waiting_for,
                "current_param": current_param,
            },
        )
        await ensure_main_menu(update, context, source="unhandled_update_fallback", prefer_edit=True)
        track_outgoing_action(update.update_id, action_type="fallback")
    except Exception as exc:
        logger.error("Error in unhandled_update_fallback: %s", exc, exc_info=True)
        await guard.check_and_ensure_response(update, context)
    return


async def confirm_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle generation confirmation.
    
    ⚠️ КРИТИЧЕСКИЕ ПРАВИЛА KIE AI - ЗАФИКСИРОВАНО НАВСЕГДА:
    
    🔴 ОБЯЗАТЕЛЬНОЕ ПРАВИЛО #0 (ГЛАВНОЕ):
    ВСЕ модели ДОЛЖНЫ использовать API Endpoints строго по официальной документации:
    https://docs.kie.ai/market - Market Documentation (ОБЯЗАТЕЛЬНО!)
    https://docs.kie.ai/ - Comprehensive API Documentation
    https://kie.ai/ru - Русская версия сайта
    НИКАКИХ отклонений от официальной документации API Endpoints!
    
    1. ВСЕ параметры ДОЛЖНЫ строго соответствовать инструкциям KIE AI API
    2. НИЧЕГО от себя не придумывать - только по документации KIE AI
    3. ВСЕ обязательные параметры ДОЛЖНЫ быть запрошены у пользователя
    4. ВСЕ обязательные параметры ДОЛЖНЫ быть валидированы перед отправкой
    5. Формат параметров строго по валидационным файлам (validate_*.py)
    6. Конвертация параметров только согласно инструкциям KIE API
    7. Числа округляются согласно step (0.01 для strength, 0.1 для guidance_scale)
    8. output_format в lowercase для qwen моделей (png, jpeg)
    9. Никаких дополнительных параметров, которых нет в документации
    10. Логирование всех параметров перед отправкой в KIE API
    
    📚 ИСТОЧНИКИ ПРАВИЛ:
    - https://docs.kie.ai/market - Market Documentation (ОБЯЗАТЕЛЬНО! Image/Video/Audio Models)
    - https://docs.kie.ai/ - Comprehensive API Documentation
    - https://kie.ai/ru - Русская версия сайта
    - llms.txt: https://docs.kie.ai/llms.txt - для навигации по документации
    
    См. KIE_AI_STRICT_RULES.md и KIE_AI_API_ENDPOINTS_RULE.md для полных правил всех моделей.
    """
    import time
    start_time = time.time()
    query = update.callback_query
    user_id = update.effective_user.id
    logger.debug(f"🔥🔥🔥 CONFIRM_GENERATION ENTRY: user_id={user_id}, query_id={query.id if query else 'None'}, data={query.data if query else 'None'}")
    from app.observability.no_silence_guard import get_no_silence_guard, track_outgoing_action
    guard = get_no_silence_guard()
    correlation_id = ensure_correlation_id(update, context)
    chat_id = query.message.chat_id if query and query.message else None
    guard.set_trace_context(
        update,
        context,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        message_id=query.message.message_id if query and query.message else None,
        update_type="callback",
        correlation_id=correlation_id,
        action="CONFIRM_GENERATE",
        action_path="confirm_generate",
        stage="UI_ROUTER",
        outcome="received",
    )
    trace_event(
        "info",
        correlation_id,
        event="TRACE_IN",
        stage="UI_ROUTER",
        update_type="callback",
        action="CONFIRM_GENERATE",
        action_path="confirm_generate",
        user_id=user_id,
        chat_id=chat_id,
        message_id=query.message.message_id if query and query.message else None,
    )
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="CONFIRM_GENERATE",
        action_path="confirm_generate",
        outcome="received",
    )

    # Track running generation task for user-driven cancellation
    await register_active_generation_task(user_id)
    
    # Answer callback immediately if present
    if query:
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Could not answer callback query: {e}")
    
    is_admin_user = get_is_admin(user_id)
    
    # Helper function to send/edit messages safely
    async def send_or_edit_message(text, parse_mode='HTML', reply_markup=None):
        result_message = None
        try:
            action_type = "send_message"
            if query:
                try:
                    result_message = await query.edit_message_text(
                        text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                    action_type = "edit_message_text"
                except Exception as edit_error:
                    logger.warning(f"Could not edit message: {edit_error}, sending new")
                    try:
                        result_message = await query.message.reply_text(
                            text,
                            parse_mode=parse_mode,
                            reply_markup=reply_markup,
                        )
                        action_type = "reply_text"
                        try:
                            await query.message.delete()
                        except:
                            pass
                    except Exception as send_error:
                        logger.error(f"Could not send new message: {send_error}")
                        result_message = await context.bot.send_message(
                            chat_id=user_id,
                            text=text,
                            parse_mode=parse_mode,
                            reply_markup=reply_markup,
                        )
                        action_type = "send_message"
            else:
                result_message = await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
                action_type = "send_message"
            track_outgoing_action(update.update_id, action_type=action_type)
        except Exception as e:
            logger.error(f"Error in send_or_edit_message: {e}", exc_info=True)
            try:
                result_message = await context.bot.send_message(chat_id=user_id, text=text, parse_mode=parse_mode)
                track_outgoing_action(update.update_id, action_type="send_message")
            except:
                pass
        return result_message

    if not _acquire_generation_submit_lock(user_id):
        user_lang = get_user_language(user_id) if user_id else "ru"
        throttle_text = (
            "⏳ <b>Генерация уже запускается</b>\n\n"
            "Пожалуйста, подождите несколько секунд и попробуйте снова."
            if user_lang == "ru"
            else "⏳ <b>Generation already starting</b>\n\nPlease wait a few seconds and try again."
        )
        from app.ux.navigation import build_back_to_menu_keyboard

        await send_or_edit_message(
            throttle_text,
            reply_markup=build_back_to_menu_keyboard(user_lang),
        )
        return ConversationHandler.END
    
    # Check if user is blocked
    if not is_admin_user and is_user_blocked(user_id):
        await send_or_edit_message(
            "❌ <b>Ваш аккаунт заблокирован</b>\n\n"
            "Обратитесь к администратору для разблокировки."
        )
        return ConversationHandler.END
    
    if user_id not in user_sessions:
        logger.error(f"❌❌❌ CRITICAL: Session not found in confirm_generation! user_id={user_id}, available_sessions={list(user_sessions.keys())[:10]}")
        
        # CRITICAL: Try to restore from backup in context.user_data
        if hasattr(context, 'user_data') and context.user_data.get('session_backup_user_id') == user_id:
            session_backup = context.user_data.get('session_backup')
            if session_backup:
                logger.warning(f"⚠️⚠️⚠️ Restoring session from context.user_data backup for user_id={user_id}")
                user_sessions[user_id] = session_backup.copy()
                logger.info(f"✅✅✅ Session restored from context.user_data: user_id={user_id}, model_id={session_backup.get('model_id')}")
            else:
                await send_or_edit_message("❌ Сессия не найдена. Пожалуйста, начните заново с /start")
                return ConversationHandler.END
        else:
            await send_or_edit_message("❌ Сессия не найдена. Пожалуйста, начните заново с /start")
            return ConversationHandler.END
    
    session = user_sessions[user_id]
    logger.info(f"✅✅✅ Session found in confirm_generation: user_id={user_id}, model_id={session.get('model_id')}, params_keys={list(session.get('params', {}).keys())}")
    
    # CRITICAL: Check if task_id already exists in session (prevent duplicate)
    if 'task_id' in session:
        task_id_existing = session.get('task_id')
        logger.warning(f"⚠️⚠️⚠️ Task {task_id_existing} already exists in session for user {user_id}, preventing duplicate")
        await send_or_edit_message(
            f"⚠️ <b>Генерация уже запущена</b>\n\n"
            f"Задача уже создана.\n"
            f"Task ID: <code>{task_id_existing}</code>",
            parse_mode='HTML'
        )
        return ConversationHandler.END
    model_id = session.get('model_id')
    params = session.get('params', {})
    model_info = session.get('model_info', {})

    missing_media = _collect_missing_required_media(session)
    if missing_media:
        user_lang = get_user_language(user_id) if user_id else "ru"
        missing_param = missing_media[0]
        param_label = _humanize_param_name(missing_param, user_lang)
        media_kind = _get_media_kind(missing_param) or "media"
        media_label_ru = {
            "image": "изображение",
            "video": "видео",
            "audio": "аудио",
            "document": "файл",
            "media": "медиа",
        }.get(media_kind, "медиа")
        media_label_en = {
            "image": "image",
            "video": "video",
            "audio": "audio",
            "document": "file",
            "media": "media",
        }.get(media_kind, "media")
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="GEN_BLOCKED_MISSING_REQUIRED_INPUTS",
            action_path="confirm_generate",
            model_id=model_id,
            gen_type=session.get("gen_type"),
            stage="UI_VALIDATE",
            outcome="blocked",
            error_code="GEN_BLOCKED_MISSING_REQUIRED_INPUTS",
            fix_hint="Запросите загрузку обязательного медиа-входа.",
            missing_fields=missing_media,
        )
        await send_or_edit_message(
            (
                f"📎 <b>Нужно загрузить {media_label_ru}</b>\n\n"
                f"Пожалуйста, загрузите: <b>{param_label}</b>.\n"
                "После загрузки сможете подтвердить генерацию."
                if user_lang == "ru"
                else (
                    f"📎 <b>Please upload the required {media_label_en}</b>\n\n"
                    f"Please upload: <b>{param_label}</b>.\n"
                    "After upload you can confirm generation."
                )
            ),
            parse_mode="HTML",
        )
        await prompt_for_specific_param(update, context, user_id, missing_param, source="missing_media")
        return INPUTTING_PARAMS

    kie_ready, kie_state = _kie_readiness_state()
    if not kie_ready:
        user_lang = get_user_language(user_id) if user_id else "ru"
        fix_hint = "Проверьте переменные окружения (KIE_API_KEY) и перезапустите сервис."
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            action="KIE_NOT_READY",
            action_path="confirm_generate",
            model_id=model_id,
            gen_type=session.get("gen_type"),
            stage="KIE_SUBMIT",
            outcome="blocked",
            error_code="KIE_NOT_READY",
            fix_hint=fix_hint,
            param={"state": kie_state},
        )
        if user_lang == "ru":
            user_message = (
                "⚠️ <b>KIE API не настроен</b>\n\n"
                "Не задан KIE_API_KEY, генерации временно недоступны.\n"
                "Что сделать: проверьте ENV на Render или сообщите администратору."
            )
        else:
            user_message = (
                "⚠️ <b>KIE API not configured</b>\n\n"
                "KIE_API_KEY is missing. Generations are temporarily unavailable.\n"
                "Please check ENV or contact the admin."
            )
        await send_or_edit_message(user_message, parse_mode="HTML")
        return ConversationHandler.END

    # CRITICAL: Check if task already exists in active_generations to prevent duplicate
    async with active_generations_lock:
        user_active_generations = [(uid, tid) for (uid, tid) in active_generations.keys() if uid == user_id]
        if user_active_generations:
            # Check if there's a recent generation for this model (within last 10 seconds)
            import time
            current_time = time.time()
            for (uid, tid) in user_active_generations:
                gen_session = active_generations.get((uid, tid))
                if gen_session and gen_session.get('model_id') == model_id:
                    created_time = gen_session.get('created_at', current_time)
                    if current_time - created_time < 10:  # Within 10 seconds
                        logger.warning(f"⚠️⚠️⚠️ Duplicate generation detected! Task {tid} was created recently for user {user_id}, model {model_id}")
                        await send_or_edit_message(
                            f"⚠️ <b>Генерация уже запущена</b>\n\n"
                            f"Задача уже создана и обрабатывается.\n"
                            f"Task ID: <code>{tid}</code>",
                            parse_mode='HTML'
                        )
                        return ConversationHandler.END
    
    # Используем адаптер для нормализации параметров
    from kie_input_adapter import normalize_for_generation
    
    # Нормализуем параметры: применяем дефолты, валидируем, адаптируем к API
    api_params, validation_errors = normalize_for_generation(model_id, params)
    
    if validation_errors:
        # Ошибки валидации - показываем пользователю
        user_lang = get_user_language(user_id) if user_id else 'ru'
        error_text = (
            f"❌ <b>Ошибка валидации параметров</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{chr(10).join('• ' + err for err in validation_errors[:5])}\n\n"
            f"Пожалуйста, проверьте параметры и попробуйте снова."
        ) if user_lang == 'ru' else (
            f"❌ <b>Parameter validation error</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{chr(10).join('• ' + err for err in validation_errors[:5])}\n\n"
            f"Please check parameters and try again."
        )
        from app.ux.navigation import build_back_to_menu_keyboard

        await send_or_edit_message(
            error_text,
            reply_markup=build_back_to_menu_keyboard(user_lang),
        )
        return ConversationHandler.END
    
    # Параметры нормализованы, используем api_params вместо params
    params = api_params
    
    logger.info(
        "✅ Input normalized from SSOT: model_id=%s keys=%s",
        model_id,
        list(params.keys()),
    )
    
    # Check if this is a free generation (do not consume upfront)
    sku_id = session.get("sku_id", "")
    free_result = await check_free_generation_available(
        user_id,
        sku_id,
        correlation_id=correlation_id,
    )
    if free_result.get("status") == "deny":
        user_lang = get_user_language(user_id)
        deny_text = (
            f"❌ <b>Лимит бесплатных генераций исчерпан</b>\n\n"
            "Бесплатный лимит пополнится завтра.\n"
            "💳 Можете пополнить счет, чтобы продолжить пользоваться инструментами."
            if user_lang == "ru"
            else (
                f"❌ <b>Free generation limit reached</b>\n\n"
                "Free limit resets tomorrow.\n"
                "💳 Top up to keep using the tools."
            )
        )
        await send_or_edit_message(deny_text)
        return ConversationHandler.END
    is_free = free_result.get("status") == "ok"
    
    # Calculate price (admins pay admin price, users pay user price)
    mode_index = _resolve_mode_index(model_id, params, user_id)
    price_quote = _update_price_quote(
        session,
        model_id=model_id,
        mode_index=mode_index,
        gen_type=session.get("gen_type"),
        params=params,
        correlation_id=correlation_id,
        update_id=update.update_id,
        action_path="confirm_generate",
        user_id=user_id,
        chat_id=chat_id,
        is_admin=is_admin_user,
    )
    if not price_quote:
        user_lang = get_user_language(user_id)
        free_remaining = free_result.get("base_remaining") if isinstance(free_result, dict) else None
        if free_remaining is None and isinstance(free_result, dict):
            free_remaining = free_result.get("remaining")
        await respond_price_undefined(
            update,
            context,
            session=session,
            user_lang=user_lang,
            model_id=model_id,
            gen_type=session.get("gen_type"),
            sku_id=session.get("sku_id"),
            price_quote=price_quote,
            free_remaining=free_remaining,
            correlation_id=correlation_id,
            action_path="confirm_generate",
        )
        return ConversationHandler.END
    price = float(price_quote.get("price_rub", 0))
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        chat_id=chat_id,
        update_id=update.update_id,
        action="PRICE_CALC",
        action_path="confirm_generate",
        model_id=model_id,
        gen_type=session.get("gen_type"),
        stage="PRICE_CALC",
        outcome="success",
        param={
            "price_rub": price_quote.get("price_rub"),
            "mode_index": mode_index,
            "breakdown": price_quote.get("breakdown", {}),
            "is_admin": is_admin_user,
        },
    )
    trace_event(
        "info",
        correlation_id,
        event="PRICE_CALC",
        stage="PRICE_CALC",
        update_type="callback",
        action="CONFIRM_GENERATE",
        action_path="confirm_generate",
        user_id=user_id,
        chat_id=chat_id,
        model_id=model_id,
        price_rub=price_quote.get("price_rub"),
        is_admin=is_admin_user,
        pricing_source="catalog",
        always_fields=[
            "model_id",
            "price_rub",
            "is_admin",
            "pricing_source",
        ],
    )
    
    # For free generations, price is 0
    if is_free:
        price = 0.0
    
    user_balance: Optional[float] = None
    # Check balance/limit before generation
    if not is_admin_user:
        # Regular user - check balance (unless free generation)
        if not is_free:
            user_balance = await get_user_balance_async(user_id)
            if user_balance < price:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update.update_id,
                    action="BALANCE_GATE",
                    action_path="confirm_generate",
                    model_id=model_id,
                    gen_type=session.get("gen_type"),
                    stage="BALANCE_GATE",
                    outcome="failed",
                    error_code="ERR_BALANCE_LOW",
                    fix_hint="Пополните баланс или используйте бесплатные генерации.",
                    param={"price_rub": price, "balance_rub": user_balance},
                )
                user_lang = get_user_language(user_id)
                await send_or_edit_message(
                    _build_insufficient_funds_text(user_lang, price, user_balance),
                    reply_markup=_build_insufficient_funds_keyboard(user_lang),
                )
                return ConversationHandler.END
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update.update_id,
                action="BALANCE_GATE",
                action_path="confirm_generate",
                model_id=model_id,
                gen_type=session.get("gen_type"),
                stage="BALANCE_GATE",
                outcome="passed",
                param={"price_rub": price, "balance_rub": user_balance},
            )
    elif user_id != ADMIN_ID:
        # Limited admin - check limit
        remaining = get_admin_remaining(user_id)
        if remaining < price:
            price_str = format_rub_amount(price)
            remaining_str = format_rub_amount(remaining)
            limit = get_admin_limit(user_id)
            spent = get_admin_spent(user_id)
            await send_or_edit_message(
                f"❌ <b>Превышен лимит</b>\n\n"
                f"💰 <b>Требуется:</b> {price_str}\n"
                f"💳 <b>Лимит:</b> {format_rub_amount(limit)}\n"
                f"💸 <b>Потрачено:</b> {format_rub_amount(spent)}\n"
                f"✅ <b>Осталось:</b> {remaining_str}\n\n"
                f"Обратитесь к главному администратору для увеличения лимита."
            )
            return ConversationHandler.END
    
    if not is_admin_user and not is_free:
        user_lang = get_user_language(user_id)
        if user_balance is None:
            user_balance = await get_user_balance_async(user_id)
        await send_or_edit_message(
            _build_price_preview_text(user_lang, price, user_balance),
        )

    model_name = model_info.get('name', model_id) if model_info else model_id
    user_lang = get_user_language(user_id) if user_id else 'ru'
    free_counter_line = ""
    try:
        free_counter_line = await get_free_counter_line(
            user_id,
            user_lang=user_lang,
            correlation_id=correlation_id,
            action_path="confirm_generate",
            sku_id=sku_id,
        )
    except Exception as exc:
        logger.warning("Failed to resolve free counter line: %s", exc)
    loading_msg = (
        "🔄 <b>Создаю задачу генерации...</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⏳ <b>Подождите, обрабатываю ваш запрос</b>\n\n"
        "🤖 <b>Модель:</b> {model_name}\n\n"
        "💡 Обычно это занимает несколько секунд..."
    ).format(model_name=model_name) if user_lang == 'ru' else (
        "🔄 <b>Creating generation task...</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⏳ <b>Please wait, processing your request</b>\n\n"
        "🤖 <b>Model:</b> {model_name}\n\n"
        "💡 Usually takes a few seconds..."
    ).format(model_name=model_name)
    loading_msg = _append_free_counter_text(loading_msg, free_counter_line)
    status_message = await send_or_edit_message(loading_msg)

    accepted_msg = (
        "✅ <b>Принято!</b>\n\n"
        "Генерация запущена, ожидайте результат...\n"
        f"🤖 <b>Модель:</b> {model_name}"
        if user_lang == 'ru'
        else (
            "✅ <b>Accepted!</b>\n\n"
            "Generation started, please wait...\n"
            f"🤖 <b>Model:</b> {model_name}"
        )
    )
    accepted_msg = _append_free_counter_text(accepted_msg, free_counter_line)

    last_progress_ts = 0.0

    async def progress_callback(event: Dict[str, Any]) -> None:
        nonlocal last_progress_ts
        stage = event.get("stage")
        if stage == "KIE_CREATE":
            await send_or_edit_message(accepted_msg)
            return
        if stage == "KIE_POLL":
            now = time.monotonic()
            if now - last_progress_ts < 25:
                return
            last_progress_ts = now
            elapsed = int(event.get("elapsed") or 0)
            if user_lang == "ru":
                progress_text = f"⏳ Генерирую… прошло {elapsed} сек."
            else:
                progress_text = f"⏳ Generating… {elapsed}s elapsed."
            try:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    action="TG_SEND_ATTEMPT",
                    action_path="confirm_generate.progress",
                    model_id=model_id,
                    stage="TG_SEND",
                    outcome="attempt",
                    error_code="TG_SEND_ATTEMPT",
                    fix_hint="Прогресс-апдейт генерации.",
                    param={"tg_method": "send_message"},
                )
                await context.bot.send_message(chat_id=chat_id, text=progress_text)
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    action="TG_SEND_OK",
                    action_path="confirm_generate.progress",
                    model_id=model_id,
                    stage="TG_SEND",
                    outcome="success",
                    error_code="TG_SEND_OK",
                    fix_hint="Прогресс-апдейт доставлен.",
                    param={"tg_method": "send_message"},
                )
            except Exception as send_exc:
                logger.warning("Progress update failed: %s", send_exc)

    try:
        from app.generations.telegram_sender import deliver_result
        from app.generations.universal_engine import (
            run_generation,
            KIEJobFailed,
            KIEResultError,
            KIERequestFailed,
        )
        from app.kie_catalog import get_model
        from app.ux.navigation import build_back_to_menu_keyboard

        model_spec = get_model(model_id)
        if not model_spec:
            await send_or_edit_message("❌ <b>Модель не найдена в каталоге</b>")
            return ConversationHandler.END

        timeout_seconds = get_generation_timeout_seconds(model_spec)
        poll_interval = int(os.getenv("KIE_POLL_INTERVAL", "3"))

        dry_run = is_dry_run() or not allow_real_generation()
        if dry_run:
            is_video = any(kw in model_id.lower() for kw in ['video', 'sora', 'kling', 'wan', 'hailuo'])
            ext = '.mp4' if is_video else '.png'
            task_id = f"dry_run_{uuid.uuid4().hex[:12]}"
            mock_url = f"https://example.com/mock/{model_id.replace('/', '_')}/{task_id}{ext}"
            message_text = (
                f"✅ <b>DRY-RUN: генерация симулирована</b>\n\n🔗 {mock_url}"
                if user_lang == "ru"
                else f"✅ <b>DRY-RUN: generation simulated</b>\n\n🔗 {mock_url}"
            )
            await status_message.edit_text(message_text, parse_mode="HTML")
            return ConversationHandler.END

        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GENERATION_STARTED",
            action_path="confirm_generate",
            model_id=model_id,
            gen_type=session.get("gen_type"),
            stage="GEN_START",
            outcome="start",
        )
        job_result = await run_generation(
            user_id,
            model_id,
            params,
            correlation_id=correlation_id,
            progress_callback=progress_callback,
            timeout=timeout_seconds,
            poll_interval=poll_interval,
        )
        task_id = job_result.task_id

        if user_id not in saved_generations:
            saved_generations[user_id] = {}
        saved_generations[user_id] = {
            "model_id": model_id,
            "model_info": model_info,
            "params": params.copy(),
            "properties": session.get("properties", {}).copy(),
            "required": session.get("required", []).copy(),
        }

        delivered = False
        if job_result.urls or job_result.text:
            model_name_display = model_info.get("name", model_id) if model_info else model_id
            pending_payload = {
                "chat_id": user_id,
                "media_type": job_result.media_type,
                "urls": job_result.urls,
                "text": job_result.text,
                "model_id": model_id,
                "gen_type": session.get("gen_type"),
                "correlation_id": correlation_id,
                "params": params,
                "model_label": model_name_display,
                "task_id": job_result.task_id,
                "sku_id": sku_id,
                "price": price,
                "is_free": is_free,
                "is_admin_user": is_admin_user,
                "session": session,
            }
            async with pending_deliveries_lock:
                pending_deliveries[(user_id, job_result.task_id)] = pending_payload
            try:
                delivered = bool(
                    await deliver_result(
                        context.bot,
                        user_id,
                        job_result.media_type,
                        job_result.urls,
                        job_result.text,
                        model_id=model_id,
                        gen_type=session.get("gen_type"),
                        correlation_id=correlation_id,
                        params=params,
                        model_label=model_name_display,
                    )
                )
            except Exception as exc:
                delivered = False
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    action="DELIVERY_FAIL",
                    action_path="confirm_generate",
                    model_id=model_id,
                    stage="TG_DELIVER",
                    outcome="failed",
                    error_code="TG_DELIVER_EXCEPTION",
                    fix_hint=str(exc),
                    param={"task_id": job_result.task_id},
                )

            if delivered:
                async with pending_deliveries_lock:
                    pending_deliveries.pop((user_id, job_result.task_id), None)
                if not dry_run:
                    await _commit_post_delivery_charge(
                        session=session,
                        user_id=user_id,
                        chat_id=chat_id,
                        task_id=job_result.task_id,
                        sku_id=sku_id,
                        price=price,
                        is_free=is_free,
                        is_admin_user=is_admin_user,
                        correlation_id=correlation_id,
                        model_id=model_id,
                    )
                else:
                    logger.info(
                        "🔧 DRY-RUN: Skipping charge/free decrement for task %s user %s",
                        job_result.task_id,
                        user_id,
                    )
                if is_free:
                    try:
                        free_counter_line = await get_free_counter_line(
                            user_id,
                            user_lang=user_lang,
                            correlation_id=correlation_id,
                            action_path="confirm_generate.post_consume",
                            sku_id=sku_id,
                        )
                    except Exception as exc:
                        logger.warning("Failed to refresh free counter after consume: %s", exc)
                try:
                    snapshot = await get_free_counter_snapshot(user_id)
                    log_structured_event(
                        correlation_id=correlation_id,
                        user_id=user_id,
                        chat_id=chat_id,
                        action="FREE_QUOTA_REFRESH",
                        action_path="confirm_generate",
                        model_id=model_id,
                        stage="FREE_QUOTA",
                        outcome="snapshot",
                        param={
                            "remaining": snapshot.get("remaining"),
                            "used_today": snapshot.get("used_today"),
                            "limit_per_day": snapshot.get("limit_per_day"),
                        },
                    )
                except Exception as exc:
                    logger.warning("Failed to refresh free counter snapshot: %s", exc)
            else:
                log_structured_event(
                    correlation_id=correlation_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    action="DELIVERY_FAIL",
                    action_path="confirm_generate",
                    model_id=model_id,
                    stage="TG_DELIVER",
                    outcome="failed",
                    error_code="TG_DELIVER_NOT_CONFIRMED",
                    fix_hint="Проверьте доставку и повторите отправку.",
                    param={"task_id": job_result.task_id},
                )
                retry_keyboard = InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔁 Повторить доставку", callback_data=f"retry_delivery:{job_result.task_id}")],
                        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
                    ]
                )
                await send_or_edit_message(
                    "⚠️ <b>Не удалось доставить результат</b>\n\n"
                    "Результат готов, но Telegram не принял отправку.\n"
                    "Нажмите «Повторить доставку», чтобы отправить ещё раз.",
                    parse_mode="HTML",
                    reply_markup=retry_keyboard,
                )
                return ConversationHandler.END
        else:
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                action="DELIVERY_FAIL",
                action_path="confirm_generate",
                model_id=model_id,
                stage="TG_DELIVER",
                outcome="failed",
                error_code="EMPTY_RESULT",
                fix_hint="Проверьте ответ провайдера (urls/text).",
                param={"task_id": job_result.task_id},
            )
            await send_or_edit_message(
                "⚠️ <b>Результат пустой</b>\n\n"
                "Генерация завершилась без результата. Попробуйте ещё раз или выберите другую модель.",
                parse_mode="HTML",
            )
            return ConversationHandler.END

        if job_result.urls:
            save_generation_to_history(
                user_id=user_id,
                model_id=model_id,
                model_name=model_info.get("name", model_id) if model_info else model_id,
                params=params.copy(),
                result_urls=job_result.urls.copy(),
                task_id=task_id,
                price=price,
                is_free=is_free,
                correlation_id=correlation_id,
            )

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 Сгенерировать еще", callback_data="generate_again")],
                [InlineKeyboardButton("📚 Мои генерации", callback_data="my_generations")],
                [InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")],
            ]
        )
        summary_text = (
            "✅ <b>Генерация завершена!</b>\n\nРезультат готов."
            if user_lang == "ru"
            else "✅ <b>Generation completed!</b>\n\nResult is ready."
        )
        balance_line = ""
        if not is_free and not is_admin_user and session.get("balance_charged"):
            updated_balance = await get_user_balance_async(user_id)
            balance_line = (
                f"\n\n💳 Баланс: {format_rub_amount(updated_balance)}"
                if user_lang == "ru"
                else f"\n\n💳 Balance: {format_rub_amount(updated_balance)}"
            )
        await send_or_edit_message(
            _append_free_counter_text(f"{summary_text}{balance_line}", free_counter_line),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        user_sessions.pop(user_id, None)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GEN_COMPLETE",
            action_path="confirm_generate",
            model_id=model_id,
            stage="GEN_COMPLETE",
            outcome="sent",
            duration_ms=int((time.time() - start_time) * 1000),
        )
        return ConversationHandler.END
    except KIERequestFailed as exc:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="KIE_SUBMIT_FAILED",
            action_path="confirm_generate",
            model_id=model_id,
            gen_type=session.get("gen_type"),
            stage="KIE_SUBMIT",
            outcome="failed",
            error_code=exc.error_code or "KIE_SUBMIT_FAILED",
            fix_hint=exc.user_message or ERROR_CATALOG.get("KIE_FAIL_STATE"),
            param={"status": exc.status},
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GENERATION_FAILED",
            action_path="confirm_generate",
            model_id=model_id,
            stage="KIE_CREATE",
            outcome="failed",
            error_code=exc.error_code or "KIE_REQUEST_FAILED",
            fix_hint=exc.user_message or ERROR_CATALOG.get("KIE_FAIL_STATE"),
        )
        if exc.status == 422 and user_id in user_sessions:
            properties = session.get("properties", {})
            missing_param = _extract_missing_param(exc.user_message or str(exc), properties)
            if missing_param:
                session["waiting_for"] = missing_param
                session["current_param"] = missing_param
                user_lang = get_user_language(user_id) if user_id else "ru"
                param_label = _humanize_param_name(missing_param, user_lang)
                correlation_suffix = _short_correlation_suffix(correlation_id)
                fix_hint = (
                    f"Укажите параметр «{param_label}» и попробуйте снова."
                    if user_lang == "ru"
                    else f"Please provide “{param_label}” and try again."
                )
                await send_or_edit_message(
                    (
                        "⚠️ <b>Не хватает обязательного параметра</b>\n\n"
                        f"{fix_hint}\n"
                        f"ID: <code>{correlation_suffix}</code>"
                        if user_lang == "ru"
                        else (
                            "⚠️ <b>Missing required parameter</b>\n\n"
                            f"{fix_hint}\n"
                            f"ID: <code>{correlation_suffix}</code>"
                        )
                    ),
                    parse_mode="HTML",
                )
                await prompt_for_specific_param(update, context, user_id, missing_param, source="kie_validation")
                return INPUTTING_PARAMS
        await send_or_edit_message(
            _build_kie_request_failed_message(exc.status, user_lang, exc.user_message),
            reply_markup=build_back_to_menu_keyboard(user_lang),
        )
        return ConversationHandler.END
    except TimeoutError as exc:
        logger.error("❌ Generation timeout: %s", exc, exc_info=True)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GENERATION_FAILED",
            action_path="confirm_generate",
            model_id=model_id,
            stage="KIE_POLL",
            outcome="timeout",
            error_code="ERR_KIE_TIMEOUT",
            fix_hint=ERROR_CATALOG.get("KIE_TIMEOUT"),
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="KIE_POLL",
            action_path="confirm_generate",
            model_id=model_id,
            stage="KIE_POLL",
            outcome="timeout",
            error_code="ERR_KIE_TIMEOUT",
            fix_hint=ERROR_CATALOG.get("KIE_TIMEOUT"),
        )
        trace_error(
            correlation_id or "corr-na-na",
            "ERR_KIE_TIMEOUT",
            ERROR_CATALOG.get("KIE_TIMEOUT", "Проверьте timeout/backoff и статус KIE."),
            exc,
            action_path="confirm_generate",
            model_id=model_id,
            stage="KIE_POLL",
        )
        timeout_text = (
            "⏳ <b>Генерация заняла слишком много времени</b>\n\n"
            "Что случилось: превышен таймаут ожидания.\n"
            "Что сделать: попробуйте снова чуть позже.\n"
            "Код: <code>ERR_KIE_TIMEOUT</code>"
        )
        await send_or_edit_message(
            _append_free_counter_text(timeout_text, free_counter_line),
            parse_mode="HTML",
        )
        return ConversationHandler.END
    except KIEJobFailed as exc:
        from app.observability.redaction import redact_payload

        logger.error(f"❌ Generation failed: {exc}", exc_info=True)
        redacted_record = redact_payload(exc.record_info or {})
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GENERATION_FAILED",
            action_path="confirm_generate",
            model_id=model_id,
            stage="KIE_POLL",
            outcome="failed",
            error_code=exc.fail_code or "KIE_FAIL_STATE",
            fix_hint=ERROR_CATALOG.get("KIE_FAIL_STATE"),
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GEN_ERROR",
            action_path="confirm_generate",
            model_id=model_id,
            outcome="failed",
            error_code=exc.fail_code or "KIE_FAIL_STATE",
            fix_hint=ERROR_CATALOG.get("KIE_FAIL_STATE"),
            param={
                "fail_code": exc.fail_code,
                "fail_msg": exc.fail_msg,
                "record_info": redacted_record,
            },
        )
        from app.generations.failure_ui import build_kie_fail_ui

        fail_text, retry_keyboard = build_kie_fail_ui(correlation_id or "corr-na-na", model_id)
        await send_or_edit_message(
            _append_free_counter_text(fail_text, free_counter_line),
            parse_mode='HTML',
            reply_markup=retry_keyboard,
        )
        return ConversationHandler.END
    except (KIEResultError, ValueError) as exc:
        error_text = str(exc)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GENERATION_FAILED",
            action_path="confirm_generate",
            model_id=model_id,
            stage="KIE_PARSE",
            outcome="failed",
            error_code=getattr(exc, "error_code", "KIE_RESULT_ERROR"),
            fix_hint=getattr(exc, "fix_hint", ERROR_CATALOG.get("KIE_FAIL_STATE")),
        )
        if _is_missing_media_error(error_text) and user_id in user_sessions:
            properties = session.get("properties", {})
            image_param_name = None
            if "image_urls" in properties:
                image_param_name = "image_urls"
            elif "image_input" in properties:
                image_param_name = "image_input"
            if image_param_name:
                session["waiting_for"] = image_param_name
                session["current_param"] = image_param_name
                if image_param_name not in session:
                    session[image_param_name] = []
                await send_or_edit_message(
                    (
                        "📷 <b>Нужна реф-картинка</b>\n\n"
                        "KIE сообщил, что требуется изображение.\n"
                        "Пожалуйста, загрузите картинку для продолжения."
                        if user_lang == "ru"
                        else (
                            "📷 <b>Image required</b>\n\n"
                            "KIE reported a missing image input.\n"
                            "Please upload an image to continue."
                        )
                    )
                )
                return INPUTTING_PARAMS
        await send_or_edit_message(
            (
                "❌ <b>Ошибка подготовки запроса</b>\n\n"
                "Проверьте параметры и попробуйте снова."
                if user_lang == "ru"
                else "❌ <b>Request validation failed</b>\n\nPlease check parameters and try again."
            ),
            reply_markup=build_back_to_menu_keyboard(user_lang),
        )
        return ConversationHandler.END
    except asyncio.CancelledError:
        logger.info("Generation cancelled by user_id=%s", user_id)
        try:
            await send_or_edit_message(
                "❌ Генерация остановлена по запросу. Вы можете запустить новую.",
                parse_mode="HTML",
            )
        except Exception:
            # If editing/sending fails, silently continue to exit the flow
            pass
        user_sessions.pop(user_id, None)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"❌ Generation failed: {e}", exc_info=True)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GENERATION_FAILED",
            action_path="confirm_generate",
            model_id=model_id,
            stage="GEN_ERROR",
            outcome="failed",
            error_code="ERR_GEN_UNKNOWN",
            fix_hint=ERROR_CATALOG.get("KIE_FAIL_STATE"),
        )
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="GEN_ERROR",
            action_path="confirm_generate",
            model_id=model_id,
            outcome="failed",
            error_code="ERR_GEN_UNKNOWN",
            fix_hint=ERROR_CATALOG.get("KIE_FAIL_STATE"),
        )
        await send_or_edit_message(
            _append_free_counter_text(
                (
                    "❌ <b>Ошибка генерации</b>\n\n"
                    "Пожалуйста, попробуйте позже.\n"
                    f"ID: {correlation_id}\n"
                    "Код: <code>ERR_GEN_UNKNOWN</code>"
                ),
                free_counter_line,
            ),
            parse_mode='HTML'
        )
        return ConversationHandler.END



async def poll_task_status(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str, user_id: int):
    """Poll task status until completion."""
    max_attempts = 60  # 5 minutes max
    attempt = 0
    start_time = asyncio.get_event_loop().time()
    last_status_message = None
    last_state = None
    last_progress_update = 0.0
    status_message = update.message if update and hasattr(update, "message") else None

    async def _send_with_log(tg_method: str, **kwargs):
        correlation_id = ensure_correlation_id(update, context)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=kwargs.get("chat_id"),
            action="TG_SEND_ATTEMPT",
            action_path="poll_task_status",
            model_id=kwargs.get("model_id"),
            stage="TG_SEND",
            outcome="attempt",
            error_code="TG_SEND_ATTEMPT",
            fix_hint="Отправка сообщения пользователю.",
            param={"tg_method": tg_method},
        )
        try:
            result = await getattr(context.bot, tg_method)(**kwargs)
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=kwargs.get("chat_id"),
                action="TG_SEND_OK",
                action_path="poll_task_status",
                model_id=kwargs.get("model_id"),
                stage="TG_SEND",
                outcome="success",
                error_code="TG_SEND_OK",
                fix_hint="Сообщение доставлено.",
                param={"tg_method": tg_method},
            )
            return result
        except Exception as exc:
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=kwargs.get("chat_id"),
                action="TG_SEND_FAIL",
                action_path="poll_task_status",
                model_id=kwargs.get("model_id"),
                stage="TG_SEND",
                outcome="failed",
                error_code="TG_SEND_FAIL",
                fix_hint="Проверьте параметры отправки Telegram.",
                param={"tg_method": tg_method, "error": str(exc)},
            )
            raise
    
    # CRITICAL: Get chat_id from update or use user_id (for private chats, chat_id == user_id)
    chat_id = user_id
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id = update.effective_chat.id
    elif update and hasattr(update, 'message') and update.message:
        chat_id = update.message.chat_id
    elif update and hasattr(update, 'callback_query') and update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    
    while attempt < max_attempts:
        await asyncio.sleep(5)  # Wait 5 seconds between polls
        attempt += 1
        elapsed = asyncio.get_event_loop().time() - start_time
        if status_message and elapsed > 30 and (elapsed - last_progress_update) >= 20:
            last_progress_update = elapsed
            try:
                await status_message.edit_text(
                    f"⏳ Генерирую… {int(elapsed)} сек",
                    parse_mode='HTML'
                )
            except Exception:
                pass
        
        try:
            gateway = get_kie_gateway()
            status_result = await gateway.get_task_status(task_id)
            
            if not status_result.get('ok'):
                error = status_result.get('error', 'Unknown error')
                user_lang = get_user_language(user_id)
                free_counter_line = ""
                try:
                    free_counter_line = await get_free_counter_line(
                        user_id,
                        user_lang=user_lang,
                        correlation_id=ensure_correlation_id(update, context),
                        action_path="gen_error",
                    )
                except Exception:
                    free_counter_line = ""
                await _send_with_log(
                    "send_message",
                    chat_id=chat_id,
                    text=_append_free_counter_text(
                        f"❌ <b>Ошибка проверки статуса:</b>\n\n{error}",
                        free_counter_line,
                    ),
                    parse_mode='HTML',
                    model_id=None,
                )
                # Clean up active generation on error
                generation_key = (user_id, task_id)
                async with active_generations_lock:
                    if generation_key in active_generations:
                        del active_generations[generation_key]
                break
            
            state = status_result.get('state')
            if state and state != last_state:
                log_structured_event(
                    correlation_id=ensure_correlation_id(update, context),
                    user_id=user_id,
                    chat_id=chat_id,
                    action="KIE_STATUS",
                    action_path="poll_task_status",
                    model_id=model_id if 'model_id' in locals() else None,
                    param={"from": last_state, "to": state, "task_id": task_id},
                    outcome="transition",
                )
                last_state = state
            
            if state == 'success':
                log_structured_event(
                    correlation_id=ensure_correlation_id(update, context),
                    user_id=user_id,
                    chat_id=chat_id,
                    action="KIE_TASK_DONE",
                    action_path="poll_task_status",
                    model_id=model_id if 'model_id' in locals() else None,
                    outcome="success",
                    error_code="KIE_TASK_DONE_OK",
                    fix_hint="Задача завершена успешно.",
                    param={"task_id": task_id},
                )
                # Send notification immediately when generation completes
                free_counter_line = ""
                try:
                    free_counter_line = await get_free_counter_line(
                        user_id,
                        user_lang=user_lang,
                        correlation_id=ensure_correlation_id(update, context),
                        action_path="gen_done",
                    )
                except Exception:
                    free_counter_line = ""
                try:
                    await _send_with_log(
                        "send_message",
                        chat_id=chat_id,
                        text=_append_free_counter_text(
                            (
                                "✅ <b>Генерация завершена!</b>\n\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                "🎉 <b>Результат готов!</b>\n\n"
                                "⏳ <b>Загружаю результат...</b>\n\n"
                                "💡 <b>Что дальше:</b>\n"
                                "• Результат будет показан ниже\n"
                                "• Вы сможете сохранить или поделиться им\n"
                                "• Можете создать новую генерацию\n\n"
                                "✨ Скоро вы увидите созданный контент!"
                                if user_lang == 'ru'
                                else (
                                    "✅ <b>Generation Completed!</b>\n\n"
                                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                    "🎉 <b>Result is ready!</b>\n\n"
                                    "⏳ <b>Loading result...</b>\n\n"
                                    "💡 <b>What's next:</b>\n"
                                    "• Result will be shown below\n"
                                    "• You can save or share it\n"
                                    "• You can create a new generation\n\n"
                                    "✨ You'll see the created content shortly!"
                                )
                            ),
                            free_counter_line,
                        ),
                        parse_mode='HTML',
                        model_id=model_id,
                    )
                except Exception as e:
                    logger.warning(f"Could not send completion notification: {e}")
                
                # Task completed successfully - prepare pricing (charge after delivery only)
                generation_key = (user_id, task_id)
                saved_session_data = None
                model_id = ''
                params = {}
                sku_id = ''
                session = None

                async with active_generations_lock:
                    if generation_key in active_generations:
                        session = active_generations[generation_key]
                        saved_session_data = {
                            'model_id': session.get('model_id'),
                            'model_info': session.get('model_info'),
                            'params': session.get('params', {}).copy(),
                            'properties': session.get('properties', {}).copy(),
                            'required': session.get('required', []).copy()
                        }
                        model_id = session.get('model_id', '')
                        params = session.get('params', {})
                        sku_id = session.get('sku_id', '')
                        is_admin_user = get_is_admin(user_id)
                        is_free = session.get('is_free_generation', False)
                    else:
                        logger.warning(f"Generation session not found for {generation_key}")
                        is_admin_user = get_is_admin(user_id)
                        is_free = False

                if session is None:
                    session_store = get_session_store(context)
                    session = ensure_session_cached(context, session_store, user_id, update.update_id) or {}

                if is_free:
                    price = 0.0
                else:
                    price = calculate_price_rub(model_id, params, is_admin_user)
                if price is None:
                    logger.error("Missing price for model %s; skipping charge.", model_id)
                    price = 0.0

                dry_run = is_dry_run() or not allow_real_generation()
                
                # Task completed successfully
                result_json = status_result.get('resultJson', '{}')
                last_message = None
                try:
                    result_data = json.loads(result_json)
                    
                    # Determine if this is a video model
                    is_video_model = model_id in ['sora-2-text-to-video', 'sora-watermark-remover', 'kling-2.6/image-to-video', 'kling-2.6/text-to-video', 'kling/v2-5-turbo-text-to-video-pro', 'kling/v2-5-turbo-image-to-video-pro', 'wan/2-5-image-to-video', 'wan/2-5-text-to-video', 'wan/2-2-animate-move', 'wan/2-2-animate-replace', 'hailuo/02-text-to-video-pro', 'hailuo/02-image-to-video-pro', 'hailuo/02-text-to-video-standard', 'hailuo/02-image-to-video-standard', 'topaz/video-upscale', 'kling/v1-avatar-standard', 'kling/ai-avatar-v1-pro', 'infinitalk/from-audio', 'wan/2-2-a14b-speech-to-video-turbo', 'bytedance/v1-pro-fast-image-to-video', 'kling/v2-1-master-image-to-video', 'kling/v2-1-standard', 'kling/v2-1-pro', 'kling/v2-1-master-text-to-video', 'wan/2-2-a14b-text-to-video-turbo', 'wan/2-2-a14b-image-to-video-turbo']
                    
                    # For sora-2-text-to-video, check remove_watermark parameter
                    if model_id == 'sora-2-text-to-video':
                        remove_watermark = params.get('remove_watermark', True)
                        # If remove_watermark is True, use resultUrls (without watermark)
                        # If False, use resultWaterMarkUrls (with watermark)
                        if remove_watermark:
                            result_urls = result_data.get('resultUrls', [])
                        else:
                            result_urls = result_data.get('resultWaterMarkUrls', [])
                            # Fallback to resultUrls if resultWaterMarkUrls is empty
                            if not result_urls:
                                result_urls = result_data.get('resultUrls', [])
                    else:
                        # For other models, use resultUrls
                        result_urls = result_data.get('resultUrls', [])
                    
                    # Сохраняем результат в кеш
                    if result_urls and model_id:
                        try:
                            from optimization_results_cache import get_cache_key_for_generation, set_cached_result
                            cache_key = get_cache_key_for_generation(model_id, params)
                            set_cached_result(cache_key, {
                                'ok': True,
                                'result_urls': result_urls.copy(),
                                'model_id': model_id,
                                'params': params.copy()
                            })
                        except ImportError:
                            pass  # Кеш не доступен
                    
                    # Save to history
                    if result_urls and model_id:
                        model_info = saved_session_data.get('model_info', {}) if saved_session_data else {}
                        model_name = model_info.get('name', model_id)
                        save_generation_to_history(
                            user_id=user_id,
                            model_id=model_id,
                            model_name=model_name,
                            params=params.copy(),
                            result_urls=result_urls.copy(),
                            task_id=task_id,
                            price=price,
                            is_free=is_free,
                            correlation_id=ensure_correlation_id(update, context),
                        )
                    
                    # Prepare buttons for last message
                    # Save generation data for "generate_again" button
                    if saved_session_data:
                        if user_id not in saved_generations:
                            saved_generations[user_id] = {}
                        saved_generations[user_id] = saved_session_data.copy()
                    
                    keyboard = [
                        [InlineKeyboardButton("🔄 Сгенерировать еще", callback_data="generate_again")],
                        [InlineKeyboardButton("📚 Мои генерации", callback_data="my_generations")],
                        [InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    if result_urls:
                        from app.generations.telegram_sender import deliver_result
                        model_info = saved_session_data.get('model_info', {}) if saved_session_data else {}
                        model_name_display = model_name if model_name else model_id
                        pending_payload = {
                            "chat_id": chat_id,
                            "media_type": (model_info.get("output_media_type") if model_info else None) or "document",
                            "urls": result_urls[:5],
                            "text": None,
                            "model_id": model_id,
                            "gen_type": model_info.get('model_mode') if model_info else None,
                            "correlation_id": ensure_correlation_id(update, context),
                            "params": params,
                            "model_label": model_name_display,
                            "task_id": task_id,
                            "sku_id": sku_id,
                            "price": price,
                            "is_free": is_free,
                            "is_admin_user": is_admin_user,
                            "session": session,
                        }
                        async with pending_deliveries_lock:
                            pending_deliveries[(user_id, task_id)] = pending_payload
                        delivered = False
                        try:
                            delivered = bool(
                                await deliver_result(
                                    context.bot,
                                    chat_id,
                                    (model_info.get("output_media_type") if model_info else None) or "document",
                                    result_urls[:5],
                                    None,
                                    model_id=model_id,
                                    gen_type=model_info.get('model_mode') if model_info else None,
                                    correlation_id=ensure_correlation_id(update, context),
                                    params=params,
                                    model_label=model_name_display,
                                )
                            )
                        except Exception as exc:
                            log_structured_event(
                                correlation_id=ensure_correlation_id(update, context),
                                user_id=user_id,
                                chat_id=chat_id,
                                action="DELIVERY_FAIL",
                                action_path="poll_task_status",
                                model_id=model_id,
                                stage="TG_DELIVER",
                                outcome="failed",
                                error_code="TG_DELIVER_EXCEPTION",
                                fix_hint=str(exc),
                                param={"task_id": task_id},
                            )

                        if delivered:
                            async with pending_deliveries_lock:
                                pending_deliveries.pop((user_id, task_id), None)
                            if not dry_run:
                                await _commit_post_delivery_charge(
                                    session=session,
                                    user_id=user_id,
                                    chat_id=chat_id,
                                    task_id=task_id,
                                    sku_id=sku_id,
                                    price=price,
                                    is_free=is_free,
                                    is_admin_user=is_admin_user,
                                    correlation_id=ensure_correlation_id(update, context),
                                    model_id=model_id,
                                )
                            free_counter_line = ""
                            try:
                                free_counter_line = await get_free_counter_line(
                                    user_id,
                                    user_lang=user_lang,
                                    correlation_id=ensure_correlation_id(update, context),
                                    action_path="gen_done",
                                )
                            except Exception:
                                free_counter_line = ""
                            summary_text = (
                                "✅ <b>Генерация завершена!</b>\n\nРезультат готов."
                                if user_lang == 'ru'
                                else "✅ <b>Generation Completed!</b>\n\nResult is ready."
                            )
                            last_message = await _send_with_log(
                                "send_message",
                                chat_id=chat_id,
                                text=_append_free_counter_text(summary_text, free_counter_line),
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )
                        else:
                            log_structured_event(
                                correlation_id=ensure_correlation_id(update, context),
                                user_id=user_id,
                                chat_id=chat_id,
                                action="DELIVERY_FAIL",
                                action_path="poll_task_status",
                                model_id=model_id,
                                stage="TG_DELIVER",
                                outcome="failed",
                                error_code="TG_DELIVER_NOT_CONFIRMED",
                                fix_hint="Проверьте доставку и повторите отправку.",
                                param={"task_id": task_id},
                            )
                            retry_keyboard = InlineKeyboardMarkup(
                                [
                                    [InlineKeyboardButton("🔁 Повторить доставку", callback_data=f"retry_delivery:{task_id}")],
                                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
                                ]
                            )
                            await _send_with_log(
                                "send_message",
                                chat_id=chat_id,
                                text=(
                                    "⚠️ <b>Не удалось доставить результат</b>\n\n"
                                    "Результат готов, но Telegram не принял отправку.\n"
                                    "Нажмите «Повторить доставку», чтобы отправить ещё раз."
                                ),
                                parse_mode="HTML",
                                reply_markup=retry_keyboard,
                            )
                            break
                    else:
                        log_structured_event(
                            correlation_id=ensure_correlation_id(update, context),
                            user_id=user_id,
                            chat_id=chat_id,
                            action="DELIVERY_FAIL",
                            action_path="poll_task_status",
                            model_id=model_id,
                            stage="TG_DELIVER",
                            outcome="failed",
                            error_code="EMPTY_RESULT",
                            fix_hint="Проверьте ответ провайдера (resultUrls).",
                            param={"task_id": task_id},
                        )
                        await _send_with_log(
                            "send_message",
                            chat_id=chat_id,
                            text=(
                                "⚠️ <b>Результат пустой</b>\n\n"
                                "Генерация завершилась без результата. Попробуйте ещё раз или выберите другую модель."
                            ),
                            parse_mode='HTML'
                        )
                        break
                except json.JSONDecodeError:
                    last_message = await _send_with_log(
                        "send_message",
                        chat_id=chat_id,
                        text=_append_free_counter_text(
                            f"✅ <b>Генерация завершена!</b>\n\nРезультат: {result_json[:500]}",
                            free_counter_line,
                        ),
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                
                # Clean up active generation
                generation_key = (user_id, task_id)
                async with active_generations_lock:
                    if generation_key in active_generations:
                        del active_generations[generation_key]
                break
            
            elif state == 'fail':
                # Task failed - auto-refund if charge was made
                fail_msg = status_result.get('failMsg', 'Unknown error')
                fail_code = status_result.get('failCode', '')
                log_structured_event(
                    correlation_id=ensure_correlation_id(update, context),
                    user_id=user_id,
                    chat_id=chat_id,
                    action="KIE_TASK_DONE",
                    action_path="poll_task_status",
                    model_id=model_id if 'model_id' in locals() else None,
                    outcome="failed",
                    error_code=fail_code or "KIE_TASK_FAIL",
                    fix_hint="Проверьте параметры и повторите генерацию.",
                    param={"task_id": task_id, "fail_msg": fail_msg},
                )
                
                # CRITICAL: Log full error details for debugging
                logger.error(f"❌ Task {task_id} failed: code={fail_code}, msg={fail_msg}")
                logger.error(f"❌ Full status_result: {json.dumps(status_result, ensure_ascii=False, indent=2)}")
                
                # AUTO-REFUND: If balance was charged, refund it
                generation_key = (user_id, task_id)
                async with active_generations_lock:
                    if generation_key in active_generations:
                        session = active_generations[generation_key]
                        model_id = session.get('model_id', '')
                        params = session.get('params', {})
                        is_admin_user = get_is_admin(user_id)
                        is_free = session.get('is_free_generation', False)
                        
                        # Check if charge was made (shouldn't be, but check anyway)
                        if not is_free and user_id != ADMIN_ID:
                            price = calculate_price_rub(model_id, params, is_admin_user)
                            # Refund if charge was made (idempotent - safe to call multiple times)
                            try:
                                await add_user_balance_async(user_id, price)
                                logger.info(f"💰 AUTO-REFUND: Refunded {price} to user {user_id} for failed task {task_id}")
                            except Exception as refund_error:
                                logger.error(f"❌ Failed to refund user {user_id} for failed task {task_id}: {refund_error}")
                        
                        session['status'] = 'failed'
                        session['error'] = fail_msg
                        session['fail_code'] = fail_code
                
                # Используем обработчик ошибок для получения понятного сообщения
                try:
                    from error_handler_providers import get_error_handler
                    handler = get_error_handler()
                    
                    # Определяем провайдера из model_id
                    provider_name = model_id.split('/')[0] if '/' in model_id else "Unknown"
                    
                    # Обрабатываем ошибку провайдера
                    user_message, error_details = handler.handle_provider_error(
                        provider_name=provider_name,
                        error_message=fail_msg,
                        status_code=None,
                        request_details={
                            "task_id": task_id,
                            "model_id": model_id,
                            "fail_code": fail_code
                        }
                    )
                except ImportError:
                    # Fallback если обработчик недоступен
                    user_message = (
                        f"❌ <b>Генерация завершена с ошибкой</b>\n\n"
                        f"Ошибка: {fail_msg}\n\n"
                        "Это техническая проблема на стороне сервера, мы уже работаем над её решением.\n\n"
                        "Пожалуйста, попробуйте позже."
                    )
                
                free_counter_line = ""
                try:
                    free_counter_line = await get_free_counter_line(
                        user_id,
                        user_lang=get_user_language(user_id),
                        correlation_id=ensure_correlation_id(update, context),
                        action_path="gen_error",
                    )
                except Exception:
                    free_counter_line = ""
                # Отправляем понятное сообщение пользователю
                await _send_with_log(
                    "send_message",
                    chat_id=chat_id,
                    text=_append_free_counter_text(user_message, free_counter_line),
                    parse_mode='HTML'
                )
                
                break
            
            elif state in ['waiting', 'queuing', 'generating']:
                # Still processing, continue polling
                # Don't send status updates - user can work with other models
                # Result will be sent automatically when ready
                continue
            else:
                # Unknown state
                await _send_with_log(
                    "send_message",
                    chat_id=chat_id,
                    text=f"⚠️ Неизвестный статус: {state}\nПродолжаю ожидание...",
                    parse_mode='HTML'
                )
                continue
        
        except Exception as e:
            logger.error(f"Error polling task status: {e}", exc_info=True)
            if attempt >= max_attempts:
                # Timeout - auto-refund if charge was made
                generation_key = (user_id, task_id)
                async with active_generations_lock:
                    if generation_key in active_generations:
                        session = active_generations[generation_key]
                        model_id = session.get('model_id', '')
                        params = session.get('params', {})
                        is_admin_user = get_is_admin(user_id)
                        is_free = session.get('is_free_generation', False)
                        
                        # AUTO-REFUND on timeout
                        if not is_free and user_id != ADMIN_ID:
                            price = calculate_price_rub(model_id, params, is_admin_user)
                            try:
                                await add_user_balance_async(user_id, price)
                                logger.info(f"💰 AUTO-REFUND: Refunded {price} to user {user_id} for timeout task {task_id}")
                            except Exception as refund_error:
                                logger.error(f"❌ Failed to refund user {user_id} for timeout task {task_id}: {refund_error}")
                        
                        del active_generations[generation_key]
                
                await _send_with_log(
                    "send_message",
                    chat_id=chat_id,
                    text=f"❌ Превышено время ожидания. Попробуйте начать генерацию заново.",
                    parse_mode='HTML'
                )
                break
            # For non-fatal errors, continue polling (don't break the loop)
            continue
    
    if attempt >= max_attempts:
        # Timeout - auto-refund if charge was made
        generation_key = (user_id, task_id)
        async with active_generations_lock:
            if generation_key in active_generations:
                session = active_generations[generation_key]
                model_id = session.get('model_id', '')
                params = session.get('params', {})
                is_admin_user = get_is_admin(user_id)
                is_free = session.get('is_free_generation', False)
                
                # AUTO-REFUND on timeout
                if not is_free and user_id != ADMIN_ID:
                    price = calculate_price_rub(model_id, params, is_admin_user)
                    if price is None:
                        logger.error("Missing price for refund on model %s", model_id)
                        price = 0.0
                    try:
                        await add_user_balance_async(user_id, price)
                        logger.info(f"💰 AUTO-REFUND: Refunded {price} to user {user_id} for timeout task {task_id}")
                    except Exception as refund_error:
                        logger.error(f"❌ Failed to refund user {user_id} for timeout task {task_id}: {refund_error}")
                
                del active_generations[generation_key]
        
        await _send_with_log(
            "send_message",
            chat_id=chat_id,
            text=f"⏰ Время ожидания истекло. Попробуйте начать генерацию заново.",
            parse_mode='HTML'
        )


async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user balance in rubles. Использует helpers для устранения дублирования."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    
    # Используем helpers для получения информации о балансе
    balance_info = await get_balance_info(user_id, user_lang)
    balance_text = await format_balance_message(balance_info, user_lang)
    keyboard = get_balance_keyboard(balance_info, user_lang)
    
    await update.message.reply_text(
        balance_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation."""
    user_id = update.effective_user.id

    # If a generation is in-flight, cancel it first
    generation_cancelled = await cancel_active_generation(user_id)
    if generation_cancelled:
        if update.callback_query:
            try:
                await update.callback_query.answer("Останавливаю генерацию…")
            except Exception:
                pass
        cancel_text = (
            "❌ Генерация остановлена. Можете запустить новую."
            if get_user_language(user_id) == "ru"
            else "❌ Generation cancelled. You can start a new one."
        )
        try:
            if update.callback_query and update.callback_query.message:
                await update.callback_query.edit_message_text(cancel_text)
            elif update.message:
                await update.message.reply_text(cancel_text)
        except Exception:
            try:
                await context.bot.send_message(chat_id=user_id, text=cancel_text)
            except Exception:
                pass
        user_sessions.pop(user_id, None)
        await ensure_main_menu(update, context, source="cancel_generation", prefer_edit=False)
        return ConversationHandler.END
    
    # Handle callback query (button press)
    if update.callback_query:
        query = update.callback_query
        await query.answer("Операция отменена")

        try:
            await query.edit_message_text(
                "❌ Операция отменена.\n\n"
                "Используйте /start для возврата в главное меню."
            )
        except Exception as e:
            logger.error(f"Error editing message on cancel: {e}", exc_info=True)
            try:
                await query.message.reply_text("❌ Операция отменена.")
            except:
                pass
        await ensure_main_menu(update, context, source="cancel", prefer_edit=False)
        return ConversationHandler.END
    
    # Handle command
    if update.message:
        await update.message.reply_text("❌ Операция отменена.")
        await ensure_main_menu(update, context, source="cancel", prefer_edit=False)
        return ConversationHandler.END


# Keep existing handlers
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search queries."""
    query = ' '.join(context.args) if context.args else ''
    
    if not query:
        await update.message.reply_text('Пожалуйста, укажите запрос. Использование: /search [запрос]')
        return
    
    results = storage.search_entries(query)
    
    if results:
        response = f'Найдено {len(results)} результат(ов) для "{query}":\n\n'
        for i, result in enumerate(results[:5], 1):
            response += f'{i}. {result["content"][:100]}...\n'
    else:
        response = f'По запросу "{query}" ничего не найдено.'
    
    await update.message.reply_text(response)


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle questions."""
    question = ' '.join(context.args) if context.args else ''
    
    if not question:
        await update.message.reply_text('Пожалуйста, задайте вопрос. Использование: /ask [вопрос]')
        return
    
    results = storage.search_entries(question)
    
    if results:
        response = f'По вашему вопросу "{question}":\n\n'
        for i, result in enumerate(results[:3], 1):
            response += f'{i}. {result["content"]}\n\n'
    else:
        kie_model = os.getenv('KIE_DEFAULT_MODEL') or os.getenv('KIE_MODEL')
        if kie_model:
            try:
                await update.message.reply_text('🤔 Ищу ответ...')
                kie_resp = await kie.invoke_model(kie_model, {'text': question})
                if kie_resp.get('ok'):
                    result = kie_resp.get('result')
                    if isinstance(result, dict) and 'output' in result:
                        output = result['output']
                    else:
                        output = result
                    response = f'Вопрос: {question}\n\nОтвет:\n{output}'
                else:
                    response = f'Вопрос: {question}\n\nОшибка API: {kie_resp.get("error")}'
            except Exception as e:
                response = f'Вопрос: {question}\n\nОшибка: {e}'
        else:
            response = f'По вашему вопросу "{question}" ничего не найдено.'
    
    await update.message.reply_text(response)


async def add_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add new knowledge."""
    knowledge = ' '.join(context.args) if context.args else ''
    
    if not knowledge:
        await update.message.reply_text('Пожалуйста, укажите знание для добавления. Использование: /add [знание]')
        return
    
    success = storage.add_entry(knowledge, update.effective_user.id)
    
    if success:
        await update.message.reply_text(f'✅ Знание добавлено: "{knowledge[:50]}..."')
    else:
        await update.message.reply_text('❌ Не удалось добавить знание.')


async def pre_checkout_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout query for Telegram Stars payments."""
    query = update.pre_checkout_query
    user_id = query.from_user.id
    
    # Verify the payment amount matches what we expect
    # The payload format is: topup_{user_id}_{timestamp}
    payload_parts = query.invoice_payload.split('_')
    
    if len(payload_parts) >= 2 and payload_parts[0] == 'topup':
        # Extract user_id from payload to verify
        payload_user_id = int(payload_parts[1])
        
        if payload_user_id == user_id:
            # Check if user has a pending payment in session
            if user_id in user_sessions and 'topup_amount' in user_sessions[user_id]:
                # Approve the pre-checkout query
                await query.answer(ok=True)
                logger.info(f"Pre-checkout approved for user {user_id}, amount: {query.total_amount} XTR")
            else:
                # Reject if no pending payment
                await query.answer(ok=False, error_message="Payment session expired. Please try again.")
                logger.warning(f"Pre-checkout rejected for user {user_id}: no pending payment")
        else:
            await query.answer(ok=False, error_message="Invalid payment request.")
            logger.warning(f"Pre-checkout rejected for user {user_id}: invalid user_id in payload")
    else:
        await query.answer(ok=False, error_message="Invalid payment payload.")
        logger.warning(f"Pre-checkout rejected for user {user_id}: invalid payload format")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful Telegram Stars payment."""
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    
    user_lang = get_user_language(user_id)
    
    # Extract payment info
    payload_parts = payment.invoice_payload.split('_')
    amount_stars = payment.total_amount  # Amount in XTR (Stars)
    
    # Convert stars to rubles using exchange rate 1.6
    # 1 ruble = 1.6 stars, so 1 star = 1/1.6 rubles
    # But we use the amount from session if available (more accurate)
    if user_id in user_sessions and 'topup_amount' in user_sessions[user_id]:
        # Use the amount from session (more accurate - this is the original ruble amount)
        amount_rubles = user_sessions[user_id]['topup_amount']
    else:
        # Fallback: convert stars back to rubles (1 star = 1/1.6 rubles)
        amount_rubles = float(amount_stars) / 1.6
    
    # Add balance to user
    await add_user_balance_async(user_id, amount_rubles)
    
    # Clear payment session
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    # Save payment record
    # Ensure payments file exists
    if not os.path.exists(PAYMENTS_FILE):
        try:
            with open(PAYMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info(f"Created payments file {PAYMENTS_FILE}")
        except Exception as e:
            logger.error(f"Error creating payments file {PAYMENTS_FILE}: {e}")
    
    payments = load_json_file(PAYMENTS_FILE, {})
    payment_id = f"stars_{user_id}_{int(time.time())}"
    payments[payment_id] = {
        'user_id': user_id,
        'amount': amount_rubles,
        'currency': 'RUB',
        'payment_method': 'telegram_stars',
        'stars_amount': amount_stars,
        'timestamp': time.time(),
        'status': 'completed'
    }
    
    # Ensure directory exists
    dir_path = os.path.dirname(PAYMENTS_FILE)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"✅ Created directory for payments file: {dir_path}")
    
    # Force immediate save for payments (critical data)
    if PAYMENTS_FILE in _last_save_time:
        del _last_save_time[PAYMENTS_FILE]
    save_json_file(PAYMENTS_FILE, payments, use_cache=True)
    
    # Verify payment was saved (with retry)
    max_retries = 3
    for retry in range(max_retries):
        if os.path.exists(PAYMENTS_FILE):
            verify_payments = load_json_file(PAYMENTS_FILE, {})
            if payment_id in verify_payments:
                logger.info(f"✅ Saved Stars payment: user_id={user_id}, amount={amount_rubles}, payment_id={payment_id}")
                break
            elif retry < max_retries - 1:
                logger.warning(f"⚠️ Retry {retry + 1}/{max_retries}: Payment verification failed, retrying save...")
                save_json_file(PAYMENTS_FILE, payments, use_cache=False)
                time.sleep(0.1)  # Small delay before retry
            else:
                logger.error(f"❌ Stars payment saved but not found in file after {max_retries} retries! payment_id={payment_id}")
        elif retry < max_retries - 1:
            logger.warning(f"⚠️ Retry {retry + 1}/{max_retries}: Payment file not found, retrying save...")
            save_json_file(PAYMENTS_FILE, payments, use_cache=False)
            time.sleep(0.1)  # Small delay before retry
        else:
            logger.error(f"❌ Failed to save Stars payment file after {max_retries} retries: {PAYMENTS_FILE} does not exist after save!")
    
    # Send confirmation message
    balance_str = f"{await get_user_balance_async(user_id):.2f}"
    
    if user_lang == 'ru':
        success_text = (
            f'{t("msg_payment_success", lang=user_lang)}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{t("msg_payment_added", lang=user_lang, amount=amount_rubles)}\n'
            f'{t("msg_payment_method", lang=user_lang, stars=amount_stars)}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{t("msg_payment_balance", lang=user_lang, balance=balance_str)}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{t("msg_payment_use_funds", lang=user_lang)}'
        )
    else:
        success_text = (
            f'{t("msg_payment_success", lang=user_lang)}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{t("msg_payment_added", lang=user_lang, amount=amount_rubles)}\n'
            f'{t("msg_payment_method", lang=user_lang, stars=amount_stars)}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{t("msg_payment_balance", lang=user_lang, balance=balance_str)}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'{t("msg_payment_use_funds", lang=user_lang)}'
        )
    
    keyboard = [
        [InlineKeyboardButton(t('btn_check_balance', lang=user_lang), callback_data="check_balance")],
        [InlineKeyboardButton(t('btn_start_generation', lang=user_lang), callback_data="show_models")],
        [InlineKeyboardButton(t('btn_back_to_menu', lang=user_lang), callback_data="back_to_menu")]
    ]
    
    await update.message.reply_text(
        success_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    logger.info(f"Successful Stars payment for user {user_id}: {amount_rubles} RUB ({amount_stars} stars)")


def initialize_data_files():
    """Initialize all data files if they don't exist."""
    # Log GitHub storage status
    try:
        from app.storage.factory import get_storage

        storage_instance = get_storage()
        storage_ok = storage_instance.test_connection()
        logger.info(f"📁 GitHub storage status: {'ok' if storage_ok else 'degraded'}")
    except Exception as e:
        logger.error(f"📁 GitHub storage status: error ({e})")
    
    data_files = [
        BALANCES_FILE,
        USER_LANGUAGES_FILE,
        GIFT_CLAIMED_FILE,
        ADMIN_LIMITS_FILE,
        PAYMENTS_FILE,
        BLOCKED_USERS_FILE,
        FREE_GENERATIONS_FILE,
        PROMOCODES_FILE,
        CURRENCY_RATE_FILE,
        REFERRALS_FILE,
        BROADCASTS_FILE,
        GENERATIONS_HISTORY_FILE
    ]
    
    created_count = 0
    for filename in data_files:
        if not os.path.exists(filename):
            try:
                # Ensure directory exists
                dir_path = os.path.dirname(filename)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                
                # Create empty JSON file
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                logger.info(f"✅ Created data file: {filename}")
                created_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to create {filename}: {e}", exc_info=True)
        else:
            file_size = os.path.getsize(filename)
            logger.info(f"✓ Data file exists: {filename} ({file_size} bytes)")
    
    if created_count > 0:
        logger.info(f"✅ Initialized {created_count} new data files")
    else:
        logger.info("✅ All data files already exist")
    
    # Log critical files status
    critical_files = [BALANCES_FILE, GENERATIONS_HISTORY_FILE, PAYMENTS_FILE]
    for critical_file in critical_files:
        if os.path.exists(critical_file):
            file_size = os.path.getsize(critical_file)
            logger.info(f"🔒 Critical file: {critical_file} ({file_size} bytes)")
        else:
            logger.warning(f"⚠️ Critical file missing: {critical_file}")
    
    # Also initialize knowledge store
    try:
        storage = KnowledgeStorage()
        storage.ensure_storage_exists()
        logger.info("✅ Knowledge store initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize knowledge store: {e}")


    # ==================== SINGLE INSTANCE LOCK ====================
    # Используем единый модуль блокировки для предотвращения 409 Conflict
    from app.locking.single_instance import (
        acquire_single_instance_lock,
        release_single_instance_lock,
        is_lock_held,
    )
    
    logger.info("🔒 Acquiring single instance lock...")
    if not acquire_single_instance_lock():
        logger.error("❌❌❌ Failed to acquire single instance lock!")
        logger.error("   Another bot instance is already running")
        logger.error("   Exiting gracefully (exit code 0) to prevent restart loop")
        sys.exit(0)
    
    logger.info("✅ Single instance lock acquired - this is the leader instance")
    
    # Регистрируем освобождение lock при выходе
    import atexit
    def release_lock_on_exit():
        try:
            release_single_instance_lock()
        except Exception as e:
            logger.error(f"Error releasing lock on exit: {e}")
    atexit.register(release_lock_on_exit)


async def create_bot_application(settings) -> Application:
    """
    Создает и настраивает Telegram Application с зарегистрированными handlers.
    НЕ запускает polling/webhook - только создает и настраивает application.
    
    Args:
        settings: Настройки из app.config.Settings
        
    Returns:
        Application с зарегистрированными handlers
    """
    # Импортируем Settings для проверки типа
    from app.config import Settings
    
    # Проверяем тип settings (может быть Settings или dict)
    if not isinstance(settings, Settings):
        # Если передан dict, создаем Settings из него
        if isinstance(settings, dict):
            from app.config import get_settings
            settings = get_settings(validate=False)
        else:
            raise TypeError(f"settings must be Settings or dict, got {type(settings)}")
    
    if not settings.telegram_bot_token:
        raise ValueError("telegram_bot_token is required in settings")
    
    ensure_source_of_truth()

    # Verify models are loaded correctly (using registry)
    from app.models.registry import get_models_sync, get_model_registry
    from app.models.yaml_registry import get_registry_path
    models_list = get_models_sync()
    registry_info = get_model_registry()
    
    categories = get_categories_from_registry()
    
    # Логируем информацию о registry
    logger.info(
        f"📊 models_registry source={registry_info['used_source']} "
        f"path={get_registry_path()} count={registry_info['count']}"
    )
    if registry_info.get('yaml_total_models'):
        logger.info(f"📊 YAML total_models={registry_info['yaml_total_models']}")
    
    logger.info(f"Creating application with {len(models_list)} models in {len(categories)} categories: {categories}")
    
    # Create the Application через bootstrap (с dependency container)
    from app.bootstrap import create_application
    application = await create_application(settings)
    
    # Для обратной совместимости: сохраняем в глобальные переменные
    # NOTE: удалить после полного рефакторинга handlers
    global storage, kie
    deps = application.bot_data["deps"]
    storage = deps.get_storage()
    kie = deps.get_kie_client()
    
    # ==================== NO-SILENCE GUARD ====================
    from app.observability.no_silence_guard import get_no_silence_guard
    no_silence_guard = get_no_silence_guard()
    logger.info("✅ NO-SILENCE GUARD: Integrated in button_callback, input_parameters, error_handler")
    
    # Вызываем внутреннюю функцию для регистрации handlers
    # (см. _register_all_handlers_internal ниже в main())
    await _register_all_handlers_internal(application)
    
    logger.info("✅ Application created with all handlers registered")
    return application


async def _register_all_handlers_internal(application: Application):
    """
    Внутренняя функция для регистрации всех handlers.
    Используется и в create_bot_application, и в main().
    """
    # Inbound update logger/context middleware (must be first)
    application.add_handler(TypeHandler(Update, inbound_update_logger), group=-100)
    application.add_handler(CallbackQueryHandler(user_action_audit_callback, pattern=".*"), group=-100)
    application.add_handler(MessageHandler(filters.ALL, user_action_audit_message), group=-100)
    application.add_handler(TypeHandler(Update, inbound_rate_limit_guard), group=-99)
    # Create conversation handler for generation
    generation_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(confirm_generation, pattern='^confirm_generate$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^show_models$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^show_all_models_list$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^other_models$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^category:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^all_models$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^free_tools$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^claim_gift$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^model:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^modelk:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^start:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^example:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^info:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_set_currency_rate$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^view_payment_screenshots$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^payment_screenshot_nav:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_payments_back$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^pay_sbp:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^pay_card:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
            CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^retry_delivery:')
        ],
        states={
            SELECTING_MODEL: [
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^show_models$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^show_all_models_list$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^other_models$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^category:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^all_models$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^free_tools$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_previous_step$')
            ],
            CONFIRMING_GENERATION: [
                CallbackQueryHandler(confirm_generation, pattern='^confirm_generate$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^retry_generate:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^retry_delivery:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_previous_step$')
            ],
            INPUTTING_PARAMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                MessageHandler(filters.PHOTO, input_parameters),
                MessageHandler(filters.Document.ALL, input_parameters),
                MessageHandler(filters.AUDIO | filters.VOICE, input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^modelk:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^start:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^example:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^info:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_previous_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$')
            ]
        },
        fallbacks=[CallbackQueryHandler(button_callback, block=True, pattern='^cancel$'),
                   CommandHandler('cancel', cancel)]
    )
    
    # NOTE: Полная регистрация handlers находится в main() начиная со строки ~25292
    # Здесь мы регистрируем только базовые handlers, остальные будут добавлены в main()
    # Для полной функциональности нужно вызвать полную регистрацию из main()
    # Но для create_bot_application достаточно базовой регистрации
    
    # Error handler регистрируется сразу после Application.builder().build()
    # через app.telegram_error_handler.ensure_error_handler_registered
    
    # Регистрируем generation_handler
    application.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.Document.ALL,
            active_session_router,
        ),
        group=-2,
    )
    application.add_handler(generation_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_router), group=1)
    application.add_handler(MessageHandler(filters.PHOTO, global_photo_router), group=1)
    application.add_handler(
        MessageHandler(
            filters.AUDIO | filters.VOICE | (filters.Document.MimeType("audio/*")),
            global_audio_router,
        ),
        group=1,
    )
    # Базовые command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_wizard_command))
    application.add_handler(CommandHandler("reset", reset_wizard_command))
    application.add_handler(CommandHandler("reset", reset_wizard_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", check_balance))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler('generate', start_generation))
    application.add_handler(CommandHandler('models', list_models))
    
    # Базовые callback handlers
    application.add_handler(CallbackQueryHandler(button_callback, block=True))
    
    # Fallback handler for unknown callbacks (must be last, lowest priority)
    async def unknown_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fallback handler for unknown callbacks - ensures no silence"""
        query = update.callback_query
        if context and getattr(context, "user_data", None) is not None:
            if context.user_data.get("last_callback_handled_update_id") == update.update_id:
                return
        if query and is_known_callback_data(query.data):
            logger.debug(f"Skipping unknown_callback_handler for known callback: {query.data}")
            return
        correlation_id = ensure_correlation_id(update, context)
        user_id = query.from_user.id if query and query.from_user else None
        chat_id = query.message.chat_id if query and query.message else None
        from app.observability.no_silence_guard import get_no_silence_guard
        guard = get_no_silence_guard()
        guard.set_trace_context(
            update,
            context,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update.update_id,
            message_id=query.message.message_id if query and query.message else None,
            update_type="callback",
            correlation_id=correlation_id,
            action="UNKNOWN_CALLBACK",
            action_path=build_action_path(query.data if query else None),
            stage="UI_ROUTER",
            outcome="unknown_callback",
        )
        try:
            log_structured_event(
                correlation_id=correlation_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update.update_id,
                action="UNKNOWN_CALLBACK",
                action_path=build_action_path(query.data if query else None),
                stage="UI_ROUTER",
                outcome="unknown_callback",
                error_code="UI_UNKNOWN_CALLBACK",
                fix_hint="register_callback_handler_or_validate_callback_data",
            )
        except Exception as structured_log_error:
            logger.warning("STRUCTURED_LOG unknown callback handler failed: %s", structured_log_error, exc_info=True)
        trace_event(
            "info",
            correlation_id,
            event="TRACE_IN",
            stage="UI_ROUTER",
            update_type="callback",
            action="UNKNOWN_CALLBACK",
            action_path=build_action_path(query.data if query else None),
            user_id=user_id,
            chat_id=chat_id,
            callback_data=query.data if query else None,
            outcome="unknown_callback",
            reason="no_handler",
        )
        if query:
            try:
                await query.answer("Не понял нажатие, обновил меню.", show_alert=False)
                from app.observability.no_silence_guard import track_outgoing_action
                track_outgoing_action(update.update_id, action_type="answerCallbackQuery")
            except Exception as e:
                logger.error(f"Error in unknown_callback_handler: {e}", exc_info=True)
                try:
                    if context and query.id:
                        await context.bot.answer_callback_query(
                            query.id,
                            text="Не понял нажатие, обновил меню.",
                            show_alert=False,
                        )
                except Exception:
                    pass
                trace_error(
                    correlation_id,
                    "UI_UNKNOWN_CALLBACK",
                    ERROR_CATALOG["UI_UNKNOWN_CALLBACK"],
                    e,
                    callback_data=query.data if query else None,
                )
        await ensure_main_menu(update, context, source="unknown_callback", prefer_edit=True)
    
    # Add fallback handlers with lowest priority (group=100, added last)
    application.add_handler(CallbackQueryHandler(unknown_callback_handler), group=100)
    application.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND)
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.Document.ALL,
            unhandled_update_fallback,
            block=False,
        ),
        group=100,
    )
    
    logger.info("✅ Basic handlers registered (full registration happens in main())")


async def main():
    """Start the bot."""
    global storage, kie
    
    # ==================== НАЧАЛЬНАЯ ДИАГНОСТИКА ====================
    logger.info("=" * 60)
    logger.info("🚀 Starting KIE Telegram Bot")
    logger.info("=" * 60)
    logger.info(f"📦 Python version: {sys.version}")
    logger.info(f"📁 Working directory: {os.getcwd()}")
    logger.info(f"🆔 Process ID: {os.getpid()}")
    logger.info(f"🌍 Platform: {platform.system()} {platform.release()}")

    # ==================== PR-2: КРИТИЧЕСКАЯ ENV ВАЛИДАЦИЯ ====================
    # Проверяем обязательные переменные ПЕРЕД любой инициализацией
    validation_errors = []
    
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    kie_api_key = os.getenv("KIE_API_KEY", "").strip()
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    github_storage_repo = os.getenv("GITHUB_STORAGE_REPO", "").strip()
    
    if not telegram_bot_token:
        validation_errors.append("TELEGRAM_BOT_TOKEN is required")
    if not github_token:
        validation_errors.append("GITHUB_TOKEN is required for storage")
    if not github_storage_repo:
        validation_errors.append("GITHUB_STORAGE_REPO is required for storage")
    
    # Логируем статус всех критичных переменных
    logger.info(f"🔑 TELEGRAM_BOT_TOKEN: {'✅ Set' if telegram_bot_token else '❌ NOT SET'}")
    logger.info(f"🔑 KIE_API_KEY: {'✅ Set' if kie_api_key else '⚠️ NOT SET (degraded mode)'}")
    logger.info(f"🔑 GITHUB_TOKEN: {'✅ Set' if github_token else '❌ NOT SET'}")
    logger.info(f"📦 GITHUB_STORAGE_REPO: {'✅ Set' if github_storage_repo else '❌ NOT SET'}")
    logger.info("🗄️ STORAGE_MODE=GITHUB_JSON (DB_DISABLED=true)")
    
    # FAIL-FAST: если есть критические ошибки - выходим сразу
    if validation_errors:
        logger.error("=" * 60)
        logger.error("❌❌❌ CRITICAL ENV VALIDATION FAILED")
        logger.error("=" * 60)
        for error in validation_errors:
            logger.error(f"  ❌ {error}")
        logger.error("=" * 60)
        logger.error("🔧 Fix these in Render Dashboard → Environment Variables")
        logger.error("🔧 Then redeploy the service")
        logger.error("=" * 60)
        sys.exit(1)
    
    # Предупреждение о необязательных, но рекомендуемых переменных
    if not kie_api_key:
        logger.warning("⚠️ KIE_API_KEY not set - KIE AI features will NOT work")
        logger.warning("   Bot will start but generation features will fail")
    
    logger.info("✅ ENV validation passed - all critical variables present")
    logger.info("=" * 60)

    from app.config import get_settings
    settings = get_settings(validate=True)
    
    # CRITICAL: Ensure GitHub storage is reachable before anything else
    logger.info("🔒 Ensuring GitHub storage persistence...")
    try:
        from app.storage.factory import get_storage

        storage_instance = get_storage()
        storage_ok = storage_instance.test_connection()
        if storage_ok:
            logger.info("✅ GitHub storage read/write ok")
        else:
            logger.warning("⚠️ GitHub storage test did not pass")
    except Exception as e:
        logger.error(f"❌ CRITICAL: GitHub storage health check failed: {e}")
        logger.error("❌ Persistence may be unavailable!")
    
    # Storage initialization is handled by app.storage.factory (already initialized above)
    
    # Initialize all data files first (for JSON fallback)
    logger.info("🔧 Initializing data files...")
    initialize_data_files()

    # ==================== SINGLE INSTANCE LOCK ====================
    # Lock is acquired during initialize_data_files; verify it is held.
    from app.locking.single_instance import is_lock_held
    if not is_lock_held():
        logger.error("❌❌❌ CRITICAL: Single instance lock is not held!")
        logger.error("   Lock acquisition should have happened during initialization")
        logger.error("   Exiting to prevent 409 Conflict...")
        sys.exit(1)
    
    logger.info("✅ Single instance lock verified - proceeding with bot initialization")
    
    # Final verification of critical files (for JSON fallback)
    logger.info("🔒 Verifying critical data files...")
    critical_files = [BALANCES_FILE, GENERATIONS_HISTORY_FILE, PAYMENTS_FILE, GIFT_CLAIMED_FILE]
    all_critical_ok = True
    for critical_file in critical_files:
        if os.path.exists(critical_file):
            file_size = os.path.getsize(critical_file)
            if file_size > 0:
                logger.info(f"✅ Critical file OK: {critical_file} ({file_size} bytes)")
            else:
                logger.warning(f"⚠️ Critical file is empty: {critical_file}")
                all_critical_ok = False
        else:
            logger.warning(f"⚠️ Critical file missing: {critical_file}")
            all_critical_ok = False
    
    if all_critical_ok:
        logger.info("✅ All critical data files verified and ready (GitHub storage)")
    else:
        logger.warning("⚠️ Some critical files need attention, but bot will continue")
    
    # NOTE: Health check server для Render
    # Если нужен health check endpoint, раскомментируйте код ниже
    # ВАЖНО: Это Python проект, НЕ Node.js! Не используйте index.js!
    #
    # import threading
    # from http.server import HTTPServer, BaseHTTPRequestHandler
    # 
    # class HealthCheckHandler(BaseHTTPRequestHandler):
    #     def do_GET(self):
    #         if self.path == '/health' or self.path == '/':
    #             self.send_response(200)
    #             self.send_header('Content-type', 'application/json')
    #             self.end_headers()
    #             self.wfile.write(b'{"status":"ok","service":"telegram-bot"}')
    #         else:
    #             self.send_response(404)
    #             self.end_headers()
    #     
    #     def log_message(self, format, *args):
    #         pass  # Suppress HTTP server logs
    # 
    # def start_health_server():
    #     port = int(os.getenv('PORT', 10000))
    #     try:
    #         server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    #         logger.info(f"✅ Health check server started on port {port}")
    #         server.serve_forever()
    #     except Exception as e:
    #         logger.error(f"❌ Failed to start health server: {e}")
    #         import traceback
    #         traceback.print_exc()
    # 
    # health_thread = threading.Thread(target=start_health_server, daemon=True)
    # health_thread.start()
    # logger.info("🚀 Health check server thread started")
    # time.sleep(2)
    
    logger.info("✅ Bot initialization complete (Python only, no Node.js needed)")
    
    # Инициализация через bootstrap (dependency container)
    # НЕ инициализируем storage/kie как глобальные - используем dependency container
    from app.config import get_settings
    
    settings = get_settings()
    
    if not settings.telegram_bot_token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables!")
        return
    logger.info("✅ STORAGE_MODE=GITHUB_JSON (DB_DISABLED=true)")
    
    ensure_source_of_truth()

    # Verify models are loaded correctly (using registry)
    from app.models.registry import get_models_sync, get_model_registry
    from app.models.yaml_registry import get_registry_path
    models_list = get_models_sync()
    registry_info = get_model_registry()
    
    categories = get_categories_from_registry()
    sora_models = [m for m in models_list if m.get('id') == 'sora-watermark-remover']
    
    # Логируем информацию о registry (source, count)
    logger.info(
        f"📊 models_registry source={registry_info['used_source']} "
        f"path={get_registry_path()} count={registry_info['count']}"
    )
    if registry_info.get('yaml_total_models'):
        logger.info(f"📊 YAML total_models={registry_info['yaml_total_models']}")
    
    logger.info(f"Bot starting with {len(models_list)} models in {len(categories)} categories: {categories}")
    if sora_models:
        logger.info(f"[OK] Sora model loaded: {sora_models[0].get('name', 'unknown')} ({sora_models[0].get('category', 'unknown')})")
    else:
        logger.warning(f"[WARN] Sora model NOT found! Available models: {[m.get('id') for m in models_list[:10]]}")
    
    # Create the Application через bootstrap (с dependency container)
    from app.bootstrap import create_application
    application = await create_application(settings)
    
    # Для обратной совместимости: сохраняем в глобальные переменные
    # NOTE: удалить после полного рефакторинга handlers
    global storage, kie
    deps = application.bot_data["deps"]
    storage = deps.get_storage()
    kie = deps.get_kie_client()
    
    # ==================== P1 FIX: ПРОГРЕВ КЕША МОДЕЛЕЙ ====================
    # ПРОБЛЕМА: get_models_sync() при запущенном event loop читает YAML на каждый запрос
    # РЕШЕНИЕ: прогреваем кеш _model_cache ВНУТРИ event loop при старте
    logger.info("🔥 Warming up models cache inside event loop...")
    import time as time_module
    warmup_start = time_module.monotonic()
    
    # Принудительно загружаем модели (это установит _model_cache)
    from app.models.registry import get_models_sync, _model_cache, _model_source
    warmup_models = get_models_sync()
    warmup_elapsed_ms = int((time_module.monotonic() - warmup_start) * 1000)
    
    logger.info(
        f"✅ Models cache warmed up: {len(warmup_models)} models loaded in {warmup_elapsed_ms}ms "
        f"(source={_model_source})"
    )
    logger.info("   Next get_models_sync() calls will use cached data (0ms latency)")
    # ==================== END P1 FIX ====================
    
    # ==================== NO-SILENCE GUARD (КРИТИЧЕСКИЙ ИНВАРИАНТ) ====================
    # Гарантирует ответ на каждый входящий update
    # NO-SILENCE GUARD реализован через:
    # 1. app/observability/no_silence_guard.py - middleware для отслеживания outgoing actions
    # 2. Интеграция в button_callback - отслеживает query.answer() и все send/edit
    # 3. Интеграция в input_parameters - отслеживает reply_text и все send/edit
    # 4. Улучшенный error_handler - отправляет fallback при ошибках
    # 5. Гарантия ответа в button_callback (всегда вызывает query.answer())
    # 6. Гарантия ответа в input_parameters (отправляет "✅ Принято, обрабатываю...")
    from app.observability.no_silence_guard import get_no_silence_guard
    no_silence_guard = get_no_silence_guard()
    logger.info("✅ NO-SILENCE GUARD: Integrated in button_callback, input_parameters, error_handler")
    # ==================== END NO-SILENCE GUARD ====================
    
    # Create conversation handler for generation
    # Note: # D) per_message=True removed to avoid PTBUserWarning
    # So we handle commands separately and use only callbacks for conversation
    generation_handler = ConversationHandler(
        entry_points=[
            # Only CallbackQueryHandler for # D) per_message=True removed to avoid PTBUserWarning
        CallbackQueryHandler(button_callback, block=True, pattern='^show_models$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^show_all_models_list$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^category:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^all_models$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^free_tools$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^claim_gift$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^model:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^modelk:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^start:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^example:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^info:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_set_currency_rate$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^view_payment_screenshots$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^payment_screenshot_nav:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_payments_back$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^pay_sbp:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^pay_card:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
            CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
            CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$')
        ],
        states={
            SELECTING_MODEL: [
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^show_models$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^show_all_models_list$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^category:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^all_models$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^free_tools$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_previous_step$')
            ],
            CONFIRMING_GENERATION: [
                CallbackQueryHandler(confirm_generation, pattern='^confirm_generate$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^retry_generate:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^retry_delivery:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^modelk:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^start:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^example:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^info:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_previous_step$')
            ],
            INPUTTING_PARAMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                MessageHandler(filters.PHOTO, input_parameters),
                MessageHandler(filters.AUDIO | filters.VOICE | (filters.Document.MimeType("audio/*")), input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^set_param:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^add_image$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^skip_image$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^image_done$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^add_audio$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^skip_audio$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^modelk:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^start:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^example:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^info:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$')
            ],
            SELECTING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^pay_stars:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^pay_sbp:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^pay_card:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^claim_gift$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$')
            ],
            WAITING_PAYMENT_SCREENSHOT: [
                MessageHandler(filters.PHOTO, input_parameters),
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$')
            ],
            ADMIN_TEST_OCR: [
                MessageHandler(filters.PHOTO, input_parameters),
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'),
                CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_view_generations$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_nav:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_gen_view:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_search$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_add$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_promocodes$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_create_broadcast$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_broadcast_stats$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_test_ocr$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_mode$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_back_to_admin$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^select_model:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$')
            ],
            WAITING_BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                MessageHandler(filters.PHOTO, input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'),
            ],
            WAITING_CURRENCY_RATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters),
                CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^reset_step$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^admin_settings$'),
                CallbackQueryHandler(button_callback, block=True, pattern='^cancel$')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_info:'),
            CallbackQueryHandler(button_callback, block=True, pattern='^admin_topup_user:'),
            CallbackQueryHandler(cancel, pattern='^cancel$'),
            CommandHandler('cancel', cancel)
        ]
        # REMOVED # D) per_message=True removed to avoid PTBUserWarning
        # - it prevents MessageHandler from working!
        # # D) per_message=True removed to avoid PTBUserWarning
        # requires ALL handlers to be CallbackQueryHandler, which breaks photo/audio handling
    )

    # Inbound update logger/context middleware (must be first)
    application.add_handler(TypeHandler(Update, inbound_update_logger), group=-100)
    application.add_handler(CallbackQueryHandler(user_action_audit_callback, pattern=".*"), group=-100)
    application.add_handler(MessageHandler(filters.ALL, user_action_audit_message), group=-100)
    
    # ==================== PHASE 1: GLOBAL INPUT ROUTERS (BEFORE ConversationHandler) ====================
    # These routers catch TEXT/PHOTO/AUDIO OUTSIDE conversation and route to input_parameters if waiting_for exists
    # This ensures NO SILENCE even if ConversationHandler doesn't catch the message
    
    # ==================== END PHASE 1: GLOBAL INPUT ROUTERS ====================
    
    # Add command handlers separately (not in conversation, as # D) per_message=True removed to avoid PTBUserWarning
    application.add_handler(CommandHandler('generate', start_generation))
    application.add_handler(CommandHandler('models', list_models))
    application.add_handler(CommandHandler('cancel', cancel))
    
    # Add handlers
    # Admin commands
    async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin user lookup and manual top-up."""
        user_id = update.effective_user.id if update.effective_user else None
        logger.info("ADMIN_COMMAND: user_id=%s", user_id)
        if user_id is None or not is_admin(user_id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        upsert_user_registry_entry(update.effective_user)
        if not context.args or len(context.args) == 0:
            await render_admin_panel(update, context, is_callback=False)
            return
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")
            return
        text, keyboard = await build_admin_user_overview(target_user_id)
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')

    async def show_admin_payments(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Show all payments (admin only). Can be called from command or callback."""
        # Determine if it's a callback query or message
        if is_callback:
            query = update_or_query
            user_id = query.from_user.id
            message_func = query.edit_message_text
        else:
            update = update_or_query
            user_id = update.effective_user.id
            message_func = update.message.reply_text
        
        if not is_admin(user_id):
            if is_callback:
                await query.answer("❌ Эта функция доступна только администратору.", show_alert=True)
            else:
                await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        stats = get_payment_stats()
        payments = stats['payments']
        
        if not payments:
            await message_func("📊 <b>Платежи</b>\n\nНет зарегистрированных платежей.", parse_mode='HTML')
            return
        
        # Show last 10 payments
        total_amount = stats['total_amount']
        total_count = stats['total_count']
        total_str = format_rub_amount(total_amount)
        
        text = f"📊 <b>Статистика платежей:</b>\n\n"
        text += f"💰 <b>Всего:</b> {total_str}\n"
        text += f"📝 <b>Количество:</b> {total_count}\n\n"
        text += f"<b>Последние платежи:</b>\n\n"
        
        import datetime
        payments_with_screenshots = 0
        for payment in payments[:10]:
            user_id_payment = payment.get('user_id', 0)
            amount = payment.get('amount', 0)
            timestamp = payment.get('timestamp', 0)
            amount_str = format_rub_amount(amount)
            
            if timestamp:
                dt = datetime.datetime.fromtimestamp(timestamp)
                date_str = dt.strftime("%d.%m.%Y %H:%M")
            else:
                date_str = "Неизвестно"
            
            # Create user link: tg://user?id=USER_ID
            user_link = f"tg://user?id={user_id_payment}"
            text += f"👤 <a href=\"{user_link}\">Пользователь {user_id_payment}</a> | 💵 {amount_str} | 📅 {date_str}\n"
            
            if payment.get('screenshot_file_id'):
                payments_with_screenshots += 1
        
        if total_count > 10:
            text += f"\n... и еще {total_count - 10} платежей"
        
        # Count total payments with screenshots
        total_with_screenshots = sum(1 for p in payments if p.get('screenshot_file_id'))
        
        # Add button to view screenshots
        keyboard = []
        if total_with_screenshots > 0:
            keyboard.append([InlineKeyboardButton("📸 Просмотр скриншотов", callback_data="view_payment_screenshots")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await message_func(text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all payments (admin only)."""
        await show_admin_payments(update, context, is_callback=False)
    
    async def admin_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Block a user (admin only)."""
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        if not context.args or len(context.args) == 0:
            await update.message.reply_text("Использование: /block_user [user_id]")
            return
        
        try:
            user_id = int(context.args[0])
            block_user(user_id)
            await update.message.reply_text(f"✅ Пользователь {user_id} заблокирован.")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")
    
    async def admin_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unblock a user (admin only)."""
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        if not context.args or len(context.args) == 0:
            await update.message.reply_text("Использование: /unblock_user [user_id]")
            return
        
        try:
            user_id = int(context.args[0])
            unblock_user(user_id)
            await update.message.reply_text(f"✅ Пользователь {user_id} разблокирован.")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")
    
    async def admin_user_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check user balance (admin only)."""
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        if not context.args or len(context.args) == 0:
            await update.message.reply_text("Использование: /user_balance [user_id]")
            return
        
        try:
            user_id = int(context.args[0])
            balance = await get_user_balance_async(user_id)
            balance_str = format_rub_amount(balance)
            is_blocked = is_user_blocked(user_id)
            blocked_text = "🔒 Заблокирован" if is_blocked else "✅ Активен"
            
            # Get user payments
            user_payments = get_user_payments(user_id)
            total_paid = sum(p.get('amount', 0) for p in user_payments)
            total_paid_str = format_rub_amount(total_paid)
            
            # Check if user is limited admin
            admin_info = ""
            if is_admin(user_id) and user_id != ADMIN_ID:
                limit = get_admin_limit(user_id)
                spent = get_admin_spent(user_id)
                remaining = get_admin_remaining(user_id)
                admin_info = (
                    f"\n👑 <b>Админ с лимитом:</b>\n"
                    f"💳 Лимит: {format_rub_amount(limit)}\n"
                    f"💸 Потрачено: {format_rub_amount(spent)}\n"
                    f"✅ Осталось: {format_rub_amount(remaining)}"
                )
            
            text = (
                f"👤 <b>Пользователь:</b> {user_id}\n"
                f"💰 <b>Баланс:</b> {balance_str}\n"
                f"💵 <b>Всего пополнено:</b> {total_paid_str}\n"
                f"📝 <b>Платежей:</b> {len(user_payments)}\n"
                f"🔐 <b>Статус:</b> {blocked_text}"
                f"{admin_info}"
            )
            
            await update.message.reply_text(text, parse_mode='HTML')
        except ValueError:
            await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")
    
    async def admin_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add admin with 100 rubles limit (main admin only)."""
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Эта команда доступна только главному администратору.")
            return
        
        if not context.args or len(context.args) == 0:
            await update.message.reply_text("Использование: /add_admin [user_id]\n\nДобавляет админа с лимитом 100 ₽ на тесты.")
            return
        
        try:
            new_admin_id = int(context.args[0])
            
            # Check if already admin
            if new_admin_id == ADMIN_ID:
                await update.message.reply_text("❌ Это главный администратор.")
                return
            
            admin_limits = get_admin_limits()
            if str(new_admin_id) in admin_limits:
                await update.message.reply_text(f"❌ Пользователь {new_admin_id} уже является админом.")
                return
            
            # Add admin with 100 rubles limit
            # NOTE: time already imported at top level
            admin_limits[str(new_admin_id)] = {
                'limit': 100.0,
                'spent': 0.0,
                'added_by': update.effective_user.id,
                'added_at': int(time.time())
            }
            save_admin_limits(admin_limits)
            
            await update.message.reply_text(
                f"✅ <b>Админ добавлен!</b>\n\n"
                f"👤 User ID: {new_admin_id}\n"
                f"💳 Лимит: 100.00 ₽\n"
                f"💸 Потрачено: 0.00 ₽\n"
                f"✅ Осталось: 100.00 ₽",
                parse_mode='HTML'
            )
        except ValueError:
            await update.message.reply_text("❌ Неверный формат user_id. Используйте число.")
    
    from app.telegram_error_handler import ensure_error_handler_registered
    ensure_error_handler_registered(application)
    
    # Add payment handlers for Telegram Stars
    # NOTE: MessageHandler and filters already imported at top level, don't re-import
    from telegram.ext import PreCheckoutQueryHandler
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    # CRITICAL FIX: Add universal photo handler as fallback to catch photos that ConversationHandler misses
    # This ensures photos are ALWAYS processed, even if ConversationHandler doesn't handle them
    async def universal_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Universal photo handler that processes photos if ConversationHandler doesn't."""
        user_id = update.effective_user.id
        logger.info(f"🔵🔵🔵 UNIVERSAL_PHOTO_HANDLER CALLED: user_id={user_id}, has_photo={bool(update.message and update.message.photo)}")
        
        # Check if user is in conversation
        if user_id in user_sessions:
            session = user_sessions[user_id]
            model_id = session.get('model_id', 'Unknown')
            waiting_for = session.get('waiting_for', 'None')
            logger.info(f"🔵 User {user_id} has session: model_id={model_id}, waiting_for={waiting_for}")
            
            # If user is waiting for image, process it
            if waiting_for in ['image_input', 'image_urls', 'image', 'mask_input', 'reference_image_input']:
                logger.info(f"🔵 User {user_id} is waiting for {waiting_for}, calling input_parameters...")
                # Call input_parameters directly
                return await input_parameters(update, context)
            else:
                logger.warning(f"🔵 User {user_id} sent photo but waiting_for={waiting_for}, not processing")
        else:
            logger.warning(f"🔵 User {user_id} sent photo but no session found")
    
    # Add universal photo handler AFTER generation_handler to catch missed photos
    application.add_handler(MessageHandler(filters.PHOTO, universal_photo_handler))
    
    # Self-test command (admin only)
    async def selftest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Self-test command для проверки конфигурации (admin only)."""
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        # Получаем конфигурацию
        config = get_config_summary()
        
        # Определяем gateway
        gateway = get_kie_gateway()
        from kie_gateway import MockKieGateway, RealKieGateway
        if isinstance(gateway, MockKieGateway):
            gateway_type = "MockKieGateway"
        elif isinstance(gateway, RealKieGateway):
            gateway_type = "RealKieGateway"
        else:
            gateway_type = f"{type(gateway).__name__}"
        
        # Проверяем storage
        storage_status = "❌ недоступно"
        try:
            from app.storage.factory import get_storage
            storage = get_storage()
            if storage.test_connection():
                storage_status = "✅ доступно"
            else:
                storage_status = "⚠️ тест соединения не прошел"
        except Exception as e:
            storage_status = f"❌ ошибка: {str(e)[:50]}"
        db_status = storage_status  # For compatibility with existing code
        
        # Собираем callback_data из клавиатур
        try:
            # Используем функцию из test_callbacks_smoke, но если недоступна - используем встроенную
            try:
                from tests.test_callbacks_smoke import get_all_known_callbacks
                callback_count = len(get_all_known_callbacks())
            except ImportError:
                # Fallback: считаем известные паттерны
                known_patterns = [
                    'show_models', 'show_all_models_list', 'category:', 'all_models',
                    'gen_type:', 'free_tools', 'check_balance',
                    'copy_bot', 'claim_gift', 'help_menu',
                    'support_contact', 'select_model:', 'back_to_menu', 'topup_balance',
                    'topup_amount:', 'topup_custom', 'referral_info', 'generate_again',
                    'my_generations', 'gen_view:', 'gen_repeat:', 'gen_history:',
                    'tutorial_start', 'tutorial_step', 'tutorial_complete', 'confirm_generate',
                    'retry_generate:', 'retry_delivery:', 'cancel', 'back_to_previous_step', 'set_param:',
                ]
                callback_count = len(known_patterns) + len(get_models_sync())  # Примерная оценка
        except Exception as e:
            callback_count = f"N/A ({str(e)[:30]})"
        
        # Формируем отчет
        report = (
            "🔍 <b>Self-Test Report</b>\n\n"
            f"📋 <b>Режимы:</b>\n"
            f"  TEST_MODE: {'✅' if config['TEST_MODE'] else '❌'}\n"
            f"  DRY_RUN: {'✅' if config['DRY_RUN'] else '❌'}\n"
            f"  ALLOW_REAL_GENERATION: {'✅' if config['ALLOW_REAL_GENERATION'] else '❌'}\n\n"
            f"🔧 <b>Gateway:</b> {gateway_type}\n\n"
            f"🗄️ <b>GitHub storage:</b> {db_status}\n\n"
            f"🔘 <b>Callback data:</b> {callback_count} найдено\n\n"
            f"⚠️ <b>Важно:</b> В TEST_MODE/DRY_RUN баланс НЕ списывается"
        )
        
        await update.message.reply_text(report, parse_mode='HTML')

    async def config_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Partner config check command (admin only)."""
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        from app.config_env import build_config_self_check_report

        report = build_config_self_check_report()
        await update.message.reply_text(report, parse_mode="HTML")
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", check_balance))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("add", add_knowledge))
    application.add_handler(CommandHandler("selftest", selftest_command))
    application.add_handler(CommandHandler("config_check", config_check_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("payments", admin_payments))
    application.add_handler(CommandHandler("block_user", admin_block_user))
    application.add_handler(CommandHandler("unblock_user", admin_unblock_user))
    application.add_handler(CommandHandler("user_balance", admin_user_balance))
    application.add_handler(CommandHandler("add_admin", admin_add_admin))
    # Add separate handlers for main menu buttons (works outside ConversationHandler)
    # This ensures the buttons work from main menu
    # NOTE: These handlers must be registered BEFORE generation_handler to catch callbacks first
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^show_models$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^show_all_models_list$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^other_models$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^back_to_menu$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^retry_delivery:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^gen_type:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^category:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^all_models$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^check_balance$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^topup_balance$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^topup_amount:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^topup_custom$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^referral_info$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^my_generations$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^gen_view:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^gen_repeat:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^gen_history:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^help_menu$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^support_contact$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^free_tools$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^claim_gift$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^generate_again$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^copy_bot$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_start$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_step'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^tutorial_complete$'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^admin_user_info:'))
    application.add_handler(CallbackQueryHandler(button_callback, block=True, pattern='^admin_topup_user:'))
    
    # CRITICAL: Add universal fallback handler for ALL other callbacks
    # This ensures NO button is left unhandled - catches everything not matched above
    # Must be registered AFTER specific handlers but BEFORE generation_handler
    # This handler will catch any callback_data that doesn't match patterns above
    application.add_handler(CallbackQueryHandler(button_callback, block=True))
    
    # 🔴 ГЛОБАЛЬНЫЙ ERROR HANDLER
    # Дубликат error_handler удален - используется обработчик выше (строка 24313)
    
    application.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.Document.ALL,
            active_session_router,
        ),
        group=-2,
    )
    application.add_handler(generation_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_router), group=1)
    application.add_handler(MessageHandler(filters.PHOTO, global_photo_router), group=1)
    application.add_handler(
        MessageHandler(
            filters.AUDIO | filters.VOICE | (filters.Document.MimeType("audio/*")),
            global_audio_router,
        ),
        group=1,
    )
    application.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND)
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.Document.ALL,
            unhandled_update_fallback,
            block=False,
        ),
        group=100,
    )
    application.add_handler(CommandHandler("models", list_models))
    
    # HTTP server already started at the beginning of main()
    # Run the bot
    logger.info("Bot starting...")
    
    # ==================== BOT MODE SELECTION ====================
    # КРИТИЧНО: Строгое разделение polling и webhook через BOT_MODE
    bot_mode = get_bot_mode()
    logger.info(f"📡 Bot mode: {bot_mode}")
    
    # Если webhook режим - НЕ запускаем polling
    if bot_mode == "webhook":
        webhook_url = WEBHOOK_URL or os.getenv("WEBHOOK_URL")
        if not webhook_url:
            logger.error("❌ WEBHOOK_URL not set for webhook mode!")
            logger.error("   Set WEBHOOK_URL environment variable or use BOT_MODE=polling")
            return
        
        logger.info(f"🌐 Starting webhook mode: {webhook_url}")
        
        # Устанавливаем webhook
        try:
            from telegram import Bot
            temp_bot = Bot(token=BOT_TOKEN)
            if not await ensure_webhook_mode(temp_bot, webhook_url):
                logger.error("❌ Failed to set webhook")
                return
            
            logger.info("✅ Webhook mode ready - waiting for updates via webhook")
            logger.info("   Bot will receive updates at: {webhook_url}")
            
            # В webhook режиме просто ждём (webhook handler должен быть настроен отдельно)
            # Для Render Web Service это нормально - они будут отправлять POST запросы
            while True:
                await asyncio.sleep(60)  # Health check loop
        except Conflict as e:
            handle_conflict_gracefully(e, "webhook")
            return
        except Exception as e:
            logger.error(f"❌ Error in webhook mode: {e}")
            return
        finally:
            await cleanup_storage()
            await cleanup_http_client()
    
    # Polling режим - продолжаем как обычно
    logger.info("📡 Starting polling mode")
    
    # CRITICAL: Wait longer to let any previous instance finish completely
    # На Render может быть несколько инстансов, запускающихся одновременно
    logger.info("⏳ Waiting 10 seconds to avoid conflicts with previous instance...")
    await asyncio.sleep(10)
    
    # Дополнительная проверка: убеждаемся, что нет активного polling
    logger.info("🔍 Final conflict check before polling...")
    try:
        from telegram import Bot
        check_bot = Bot(token=BOT_TOKEN)
        # Пробуем получить webhook info - если есть активный polling, это может вызвать конфликт
        webhook_info = await check_bot.get_webhook_info()
        if webhook_info.url:
            logger.warning(f"⚠️ Webhook still active: {webhook_info.url}, removing...")
            await check_bot.delete_webhook(drop_pending_updates=True)
            await asyncio.sleep(2)
        
        # Пробуем getUpdates с очень коротким timeout для проверки конфликта
        try:
            await check_bot.get_updates(offset=-1, limit=1, timeout=1)
        except Exception as test_e:
            if "Conflict" in str(test_e) or "terminated by other getUpdates" in str(test_e):
                logger.error("❌❌❌ CONFLICT DETECTED: Another instance is polling!")
                logger.error("   Exiting gracefully to prevent 409 Conflict...")
                handle_conflict_gracefully(test_e, "polling")
                return
    except Exception as e:
        if "Conflict" in str(e) or "terminated by other getUpdates" in str(e):
            logger.error("❌❌❌ CONFLICT DETECTED during pre-check!")
            handle_conflict_gracefully(e, "polling")
            return
        logger.warning(f"⚠️ Pre-check warning (non-critical): {e}")
    
    # КРИТИЧНО: Удалить ВСЕ webhook и проверить конфликты перед запуском polling
    async def preflight_telegram():
        """
        Preflight проверка: удаляет webhook и проверяет отсутствие конфликтов.
        Это гарантирует, что polling будет единственным источником апдейтов.
        ТОЛЬКО для polling режима!
        """
        try:
            # Используем временный bot для проверки (без инициализации application)
            from telegram import Bot
            temp_bot = Bot(token=BOT_TOKEN)
            
            async with temp_bot:
                # Шаг 1: Получаем информацию о webhook
                logger.info("🔍 Checking webhook status...")
                webhook_info = await temp_bot.get_webhook_info()
                
                if webhook_info.url:
                    logger.warning(f"⚠️ Webhook обнаружен: {webhook_info.url}")
                    logger.info("🗑️ Удаляю webhook с drop_pending_updates=True...")
                    
                    # Удаляем webhook с очисткой очереди
                    result = await temp_bot.delete_webhook(drop_pending_updates=True)
                    logger.info(f"✅ Webhook удалён: {result}")
                    
                    # Проверяем, что webhook действительно удалён
                    await asyncio.sleep(1)  # Небольшая задержка для Telegram API
                    webhook_info_after = await temp_bot.get_webhook_info()
                    
                    if webhook_info_after.url:
                        logger.error(f"❌ Webhook всё ещё установлен: {webhook_info_after.url}")
                        logger.error("🔄 Повторная попытка удаления...")
                        await temp_bot.delete_webhook(drop_pending_updates=True)
                        await asyncio.sleep(1)
                        webhook_info_final = await temp_bot.get_webhook_info()
                        if webhook_info_final.url:
                            logger.error("❌❌❌ Не удалось удалить webhook после 2 попыток!")
                            raise RuntimeError(f"Webhook still active: {webhook_info_final.url}")
                        else:
                            logger.info("✅ Webhook удалён после повторной попытки")
                    else:
                        logger.info("✅ Webhook полностью удалён, готов к polling")
                else:
                    logger.info("✅ Webhook не установлен, готов к polling")
                
                # Шаг 2: Используем bot_mode helper для гарантии polling режима
                if not await ensure_polling_mode(temp_bot):
                    raise RuntimeError("Failed to ensure polling mode")
                
                logger.info("✅ Preflight check passed: no conflicts detected, ready for polling")
        except Conflict as e:
            handle_conflict_gracefully(e, "polling")
            raise
        except Exception as e:
            error_msg = str(e)
            if "Conflict" in error_msg or "terminated by other getUpdates" in error_msg:
                from telegram.error import Conflict as TelegramConflict
                handle_conflict_gracefully(TelegramConflict(str(e)), "polling")
                raise
            else:
                logger.warning(f"⚠️ Предупреждение при preflight check: {e}")
                # Не критичная ошибка, продолжаем
    
    # ==================== ЕДИНАЯ ТОЧКА ВХОДА ДЛЯ СТАРТА POLLING ====================
    # Жёсткая защита от повторных запусков (409 Conflict)
    async def safe_start_polling(application: Application, *, drop_updates: bool = True):
        """
        Единственный безопасный способ запуска polling.
        Гарантирует, что polling запустится только один раз.
        КРИТИЧНО: Удаляет webhook ПЕРЕД запуском polling.
        """
        global _POLLING_STARTED
        
        async with _POLLING_LOCK:
            if _POLLING_STARTED:
                logger.warning("⚠️ Polling already started; skip second start")
                return
            _POLLING_STARTED = True
        
        # КРИТИЧНО: Проверяем, что single instance lock все еще активен перед запуском polling
        from app.locking.single_instance import is_lock_held
        if not is_lock_held():
            logger.error("❌❌❌ Single instance lock не удерживается! Невозможно запустить polling.")
            logger.error("   This should not happen - lock should be acquired at startup")
            raise RuntimeError("Single instance lock not held - cannot start polling")
        
        logger.info("✅ Single instance lock verified - proceeding with polling start")
        
        # КРИТИЧНО: Polling mode must not have webhook
        # Используем temp Bot для удаления webhook ПЕРЕД инициализацией application
        logger.info("🗑️ Removing webhook before polling start...")
        try:
            from telegram import Bot
            async with Bot(token=BOT_TOKEN) as temp_bot:
                await temp_bot.delete_webhook(drop_pending_updates=drop_updates)
                webhook_info = await temp_bot.get_webhook_info()
                if webhook_info.url:
                    logger.warning(f"⚠️ Webhook still present after delete: {webhook_info.url}")
                else:
                    logger.info("✅ Webhook removed successfully")
        except Conflict as e:
            handle_conflict_gracefully(e, "polling")
            raise
        except Exception as e:
            logger.warning(f"⚠️ Error removing webhook: {e}")
            # Не критично - продолжим
        
        # Инициализируем и запускаем polling
        logger.info("🚀 Initializing application...")
        await application.initialize()
        await application.start()
        
        # Регистрируем команды в меню Telegram
        logger.info("📋 Setting up bot commands menu...")
        try:
            # Базовые команды для всех пользователей
            user_commands = [
                BotCommand("start", "Главное меню"),
                BotCommand("help", "Помощь"),
                BotCommand("balance", "Проверить баланс"),
                BotCommand("cancel", "Отменить текущее действие"),
            ]
            
            # Команды для администраторов
            admin_commands = user_commands + [
                BotCommand("admin", "Панель администратора"),
                BotCommand("payments", "Список платежей"),
                BotCommand("selftest", "Самодиагностика бота"),
            ]
            
            # Устанавливаем команды для обычных пользователей
            await application.bot.set_my_commands(user_commands)
            logger.info(f"✅ Registered {len(user_commands)} user commands")
            
            # Устанавливаем команды для администраторов
            from telegram import BotCommandScopeAllChatAdministrators
            await application.bot.set_my_commands(
                admin_commands, 
                scope=BotCommandScopeAllChatAdministrators()
            )
            logger.info(f"✅ Registered {len(admin_commands)} admin commands")
        except Exception as e:
            logger.warning(f"⚠️ Failed to set bot commands: {e}")
            # Не критично - продолжим работу
        
        logger.info("📡 Starting polling...")
        
        # Запускаем polling с обработкой Conflict
        try:
            await application.updater.start_polling(drop_pending_updates=drop_updates)
            logger.info("✅ Polling started successfully!")
        except Conflict as e:
            logger.error(f"❌❌❌ Conflict during polling start: {e}")
            logger.error("   Another bot instance is already polling")
            try:
                await application.stop()
                await application.shutdown()
            except:
                pass
            try:
                from app.locking.single_instance import release_single_instance_lock
                release_single_instance_lock()
            except:
                pass
            handle_conflict_gracefully(e, "polling")
            import os
            os._exit(0)  # Immediate exit
        except Exception as e:
            error_msg = str(e)
            if "Conflict" in error_msg or "terminated by other getUpdates" in error_msg or "409" in error_msg:
                logger.error(f"❌❌❌ Conflict detected during polling start: {error_msg}")
                try:
                    await application.stop()
                    await application.shutdown()
                except:
                    pass
                try:
                    from app.locking.single_instance import release_single_instance_lock
                    release_single_instance_lock()
                except:
                    pass
                from telegram.error import Conflict as TelegramConflict
                handle_conflict_gracefully(TelegramConflict(error_msg), "polling")
                import os
                os._exit(0)  # Immediate exit
            else:
                raise  # Re-raise non-Conflict errors
    
    # Выполняем preflight проверку
    logger.info("🚀 Starting preflight check (webhook removal + conflict detection)...")
    try:
        await preflight_telegram()
        logger.info("✅ Preflight check passed: ready to start bot")
    except RuntimeError as e:
        if "Another bot instance" in str(e) or "Conflict" in str(e):
            logger.error("❌ Cannot start: Another bot instance is running!")
            logger.error("Fix the conflict and restart the service.")
            return
        else:
            raise
    except Conflict as e:
        handle_conflict_gracefully(e, "polling")
        return
    except Exception as e:
        if "Conflict" in str(e) or "terminated by other getUpdates" in str(e):
            from telegram.error import Conflict as TelegramConflict
            handle_conflict_gracefully(TelegramConflict(str(e)), "polling")
            return
        else:
            logger.warning(f"⚠️ Preflight warning (continuing): {e}")
    
    # Запускаем polling через единую точку входа
    await safe_start_polling(application, drop_updates=True)
    
    # Ждём бесконечно (polling работает в фоне)
    # Advisory lock будет освобожден через atexit handler при завершении процесса
    try:
        await asyncio.Event().wait()  # Бесконечное ожидание
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down bot (KeyboardInterrupt)...")
    finally:
        # Останавливаем application
        try:
            await application.stop()
            await application.shutdown()
        except Exception as e:
            logger.error(f"Error stopping application: {e}")

        await cleanup_storage()
        await cleanup_http_client()
        
        # Освобождаем single instance lock перед выходом (дополнительно к atexit)
        try:
            from app.locking.single_instance import release_single_instance_lock
            release_single_instance_lock()
            logger.info("✅ Single instance lock released in finally block")
        except Exception as e:
            logger.error(f"Error releasing lock in finally: {e}")


# ==================== HEALTH HTTP SERVER FOR RENDER ====================
# Простой HTTP сервер для health check (чтобы Render не жаловался на отсутствие порта)
class HealthHandler(BaseHTTPRequestHandler):
    """Обработчик для health check endpoints"""
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Отключаем логирование HTTP запросов (чтобы не засорять логи)
        return  # silence

def start_health_server():
    """Запускает простой HTTP сервер для health check"""
    try:
        port = int(os.getenv("PORT", "10000"))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"✅ Health server started on 0.0.0.0:{port}")
        logger.info(f"   Health check endpoints: /, /health, /healthz")
        server.serve_forever()
    except OSError as e:
        if "Address already in use" in str(e):
            logger.warning(f"⚠️ Port {port} already in use, health server may already be running")
        else:
            logger.error(f"❌ Failed to start health server: {e}")
    except Exception as e:
        logger.error(f"❌ Failed to start health server: {e}")
        # Не критично, продолжаем работу бота

if __name__ == '__main__':
    # ENV-управляемый режим: включаем health server только если нужно (для Web Service)
    ENABLE_HEALTH_SERVER = os.getenv("ENABLE_HEALTH_SERVER", "1") == "1"
    
    if ENABLE_HEALTH_SERVER:
        # КРИТИЧНО: Запускаем health сервер ПЕРЕД ботом, чтобы Render видел открытый порт
        port = int(os.getenv("PORT", "10000"))
        logger.info(f"🚀 Starting health server on port {port}...")
        
        # Запускаем health сервер в отдельном потоке (daemon - умрёт с основным процессом)
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()
        
        # Даём серверу время запуститься (Render проверяет порт сразу после старта)
        time.sleep(1)
        logger.info(f"✅ Health server listening on 0.0.0.0:{port}")
    else:
        logger.info("ℹ️ Health server disabled (ENABLE_HEALTH_SERVER=0) - running as Worker")
    
    # Единая точка входа через asyncio.run
    # НЕ запускаем бота при импортах - только при прямом вызове
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (KeyboardInterrupt)")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error in main(): {e}", exc_info=True)
        logger.error("❌ Bot failed to start. Check logs above for details.")
        sys.exit(1)
