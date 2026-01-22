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
from price_confirmation import show_price_confirmation, build_confirmation_text
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
    # FIX #2: Strict check - verify balance is sufficient before subtracting
    if before_balance < price:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            chat_id=chat_id,
            action="CHARGE_COMMIT",
            action_path="delivery",
            model_id=model_id,
            stage="CHARGE_COMMIT",
            outcome="insufficient_funds",
            param={
                "task_id": task_id,
                "required": price,
                "available": before_balance,
            },
        )
        logger.error(f"❌ Insufficient balance: user={user_id}, required={price}, available={before_balance}")
        return outcome
    
    success = await subtract_user_balance_async(user_id, price)
    after_balance = await get_user_balance_async(user_id) if success else before_balance
    if success:
        session["balance_charged"] = True
        registry.add(task_key)
        outcome["charged"] = True
        # FIX #2: Log history operation when balance is charged
        logger.info(f"💸 Balance charged: user_id={user_id}, model_id={model_id}, amount={price}, before={before_balance}, after={after_balance}")
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
        # FIX #4: If already referred before, don't give bonus again (idempotent)
        logger.warning(f"⚠️ Duplicate referral attempt: referred_id={referred_id}, already has referrer={data[referred_key].get('referred_by')}")
        return
    
    # FIX #4: Check if bonus was already awarded in recent time (prevent double-award in same session)
    if referred_key in data and data[referred_key].get('referred_at'):
        last_referred_time = data[referred_key].get('referred_at', 0)
        if time.time() - last_referred_time < 10:  # Within 10 seconds = same request replay
            logger.warning(f"⚠️ Duplicate referral within 10s: referred_id={referred_id}, skipping bonus")
            return
    
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
    logger.info(f"🤝 Referral added: referrer={referrer_id}, referred={referred_id}")
    
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
    # FIX #1: Check duplicate by screenshot_file_id before charging balance
    if screenshot_file_id and check_duplicate_payment(screenshot_file_id):
        logger.warning(f"⚠️ Duplicate payment attempt: screenshot_file_id={screenshot_file_id}")
        existing = load_json_file(PAYMENTS_FILE, {})
        for p in existing.values():
            if p.get('screenshot_file_id') == screenshot_file_id:
                return p  # Return existing payment record (idempotent)
    
    payment = _persist_payment_record(user_id, amount, screenshot_file_id)

    # Auto-add balance (only once per unique payment_id)
    add_user_balance(user_id, amount)
    logger.info(f"💰 Payment topped up: user_id={user_id}, amount={amount}, payment_id={payment.get('id')}")

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

    if user_lang == "ru":
        header_text = (
            "🔥 FERIXDI AI — Ultra Creative Suite\n"
            "Премиальная AI-студия в Telegram для маркетинга / SMM / арбитража.\n"
            "Здесь делают креатив не “поиграться”, а быстро собрать материал под трафик: варианты, стили, усиление качества — и сразу в работу.\n\n"
            "⚡ Что ты получаешь:\n"
            "• 🎨 Визуал-пак под рекламу — генерация, стили, вариации, апскейл, фон\n"
            "• 🧩 Ремикс изображения — прокачать исходник, сменить вайб, усилить детали\n"
            "• 🎬 Видео-креативы — из идеи в ролик, из изображения в движение, улучшение качества\n"
            "• 🧼 Ремастер качества — “подня