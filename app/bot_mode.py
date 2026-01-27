#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Mode Manager - единая семантика BOT_MODE.
Поддерживает polling/webhook/web/smoke и гарантирует явную ошибку для неизвестных значений.
"""

import os
from urllib.parse import urlsplit, urlunsplit
import asyncio
import logging
import time
from typing import Dict, Literal, Optional
from telegram import Bot
from telegram.error import Conflict, RetryAfter, TimedOut
import httpx

logger = logging.getLogger(__name__)

BotMode = Literal["polling", "webhook", "web", "smoke"]
_VALID_MODES = {"polling", "webhook", "web", "smoke"}
_WEBHOOK_SET_LOCK = asyncio.Lock()
_WEBHOOK_SET_RATE_LIMIT_TOTAL = 0
_WEBHOOK_SET_LAST_REASON: Optional[str] = None
_WEBHOOK_SET_LAST_ERROR_TYPE: Optional[str] = None
_WEBHOOK_SET_LAST_ERROR: Optional[str] = None
def _set_webhook_set_result(reason: str, *, error_type: Optional[str] = None, error: Optional[str] = None) -> None:
    global _WEBHOOK_SET_LAST_REASON, _WEBHOOK_SET_LAST_ERROR_TYPE, _WEBHOOK_SET_LAST_ERROR
    _WEBHOOK_SET_LAST_REASON = reason
    _WEBHOOK_SET_LAST_ERROR_TYPE = error_type
    _WEBHOOK_SET_LAST_ERROR = error


def get_webhook_set_last_failure_reason() -> Optional[str]:
    reason = _WEBHOOK_SET_LAST_REASON
    if reason in {None, "ok", "already_set"}:
        return None
    return reason


def get_webhook_set_last_result() -> Dict[str, Optional[str]]:
    return {
        "reason": _WEBHOOK_SET_LAST_REASON,
        "error_type": _WEBHOOK_SET_LAST_ERROR_TYPE,
        "error": _WEBHOOK_SET_LAST_ERROR,
    }


def _read_float_env(name: str, default: float, *, min_value: float = 0.1, max_value: float = 30.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value.strip())
    except ValueError:
        logger.warning("Invalid %s value '%s', defaulting to %s", name, raw_value, default)
        return default
    return max(min_value, min(max_value, value))


def _read_int_env(name: str, default: int, *, min_value: int = 1, max_value: int = 10) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value.strip())
    except ValueError:
        logger.warning("Invalid %s value '%s', defaulting to %s", name, raw_value, default)
        return default
    return max(min_value, min(max_value, value))

def _normalize_webhook_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    path = parts.path or ""
    while "//" in path:
        path = path.replace("//", "/")
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def get_webhook_url_from_env() -> str:
    """Resolve webhook URL from WEBHOOK_URL or WEBHOOK_BASE_URL."""
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()
    if not webhook_url and webhook_base_url:
        normalized_base = _normalize_webhook_url(webhook_base_url.rstrip("/"))
        return normalized_base.rstrip("/") + "/webhook"
    return _normalize_webhook_url(webhook_url)


def get_bot_mode() -> BotMode:
    """
    Получает режим работы бота из ENV
    Default: polling для локальной разработки, webhook для Render Web Service
    """
    mode = os.getenv("BOT_MODE", "").lower().strip()
    
    # Автоопределение для Render
    if not mode:
        # Если есть PORT и WEBHOOK_URL - вероятно webhook режим
        if os.getenv("PORT") and get_webhook_url_from_env():
            mode = "webhook"
        else:
            mode = "polling"
    
    if mode not in _VALID_MODES:
        logger.error("Invalid BOT_MODE=%s. Allowed: %s", mode, ", ".join(sorted(_VALID_MODES)))
        raise ValueError(f"Invalid BOT_MODE: {mode}")
    
    logger.info(f"📡 Bot mode: {mode}")
    return mode


async def ensure_polling_mode(bot: Bot) -> bool:
    """
    Гарантирует что бот в polling режиме
    Удаляет webhook перед запуском polling
    
    Returns:
        True если готов к polling, False если ошибка
    """
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.warning(f"⚠️ Webhook detected: {webhook_info.url}, removing...")
            result = await bot.delete_webhook(drop_pending_updates=True)
            logger.info(f"✅ Webhook deleted: {result}")
            
            # Проверяем что webhook действительно удалён
            webhook_info_after = await bot.get_webhook_info()
            if webhook_info_after.url:
                logger.error(f"❌ Webhook still active: {webhook_info_after.url}")
                return False
            
            logger.info("✅ Webhook confirmed deleted, ready for polling")
        else:
            logger.info("✅ No webhook set, ready for polling")
        
        return True
    except Conflict as e:
        logger.error(f"❌ Conflict detected while ensuring polling mode: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Error ensuring polling mode: {e}")
        return False


async def ensure_webhook_mode(
    bot: Bot,
    webhook_url: str,
    *,
    connect_timeout: Optional[float] = None,
    read_timeout: Optional[float] = None,
    write_timeout: Optional[float] = None,
    pool_timeout: Optional[float] = None,
    cycle_timeout_s: Optional[float] = None,
    pending_update_threshold: Optional[int] = None,
) -> bool:
    """
    Гарантирует что бот в webhook режиме
    Устанавливает webhook и проверяет что polling не запущен
    
    Returns:
        True если готов к webhook, False если ошибка
    """
    if not webhook_url:
        logger.error("❌ WEBHOOK_URL not set for webhook mode")
        logger.error("   Set WEBHOOK_URL or WEBHOOK_BASE_URL")
        return False
    
    timeout_connect = connect_timeout or _read_float_env("WEBHOOK_SET_CONNECT_TIMEOUT_SECONDS", 1.0)
    timeout_read = read_timeout or _read_float_env("WEBHOOK_SET_READ_TIMEOUT_SECONDS", 1.5)
    timeout_write = write_timeout or _read_float_env("WEBHOOK_SET_WRITE_TIMEOUT_SECONDS", 1.5)
    timeout_pool = pool_timeout or _read_float_env("WEBHOOK_SET_POOL_TIMEOUT_SECONDS", 1.0)
    cycle_timeout = cycle_timeout_s or _read_float_env(
        "WEBHOOK_SET_CYCLE_TIMEOUT_SECONDS",
        2.8,
        min_value=1.0,
        max_value=5.0,
    )
    pending_threshold = pending_update_threshold or _read_int_env(
        "WEBHOOK_SET_PENDING_UPDATE_THRESHOLD",
        5,
        min_value=0,
        max_value=100,
    )

    async with _WEBHOOK_SET_LOCK:
        start = time.monotonic()
        deadline = start + cycle_timeout

        def _remaining_timeout() -> float:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("webhook_set_cycle_timeout")
            return remaining

        async def _call_with_deadline(coro, *, stage: str):
            try:
                return await asyncio.wait_for(coro, timeout=_remaining_timeout())
            except asyncio.TimeoutError as exc:
                raise TimeoutError(f"{stage}_timeout") from exc

        try:
            webhook_info = await _call_with_deadline(
                bot.get_webhook_info(
                    connect_timeout=min(timeout_connect, _remaining_timeout()),
                    read_timeout=min(timeout_read, _remaining_timeout()),
                ),
                stage="webhook_probe",
            )
            pending_count = getattr(webhook_info, "pending_update_count", None)
            pending_ok = pending_count is None or pending_count <= pending_threshold
            if webhook_info.url == webhook_url and pending_ok:
                logger.info("✅ Webhook already set: %s", webhook_info.url)
                _set_webhook_set_result("already_set")
                return True
        except TimeoutError as exc:
            logger.warning("WEBHOOK_INFO_CHECK_TIMEOUT error=%s", exc)
            _set_webhook_set_result("timeout", error_type="Timeout", error=str(exc))
            return False
        except Exception as exc:
            logger.warning("WEBHOOK_INFO_CHECK_FAILED error=%s", exc)
            _set_webhook_set_result("info_failed", error_type=type(exc).__name__, error=str(exc))
        try:
            result = await _call_with_deadline(
                bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True,
                    connect_timeout=min(timeout_connect, _remaining_timeout()),
                    read_timeout=min(timeout_read, _remaining_timeout()),
                    write_timeout=min(timeout_write, _remaining_timeout()),
                    pool_timeout=min(timeout_pool, _remaining_timeout()),
                ),
                stage="webhook_set",
            )
            logger.info("✅ Webhook set: %s", result)
            _set_webhook_set_result("ok")
            return True
        except RetryAfter as exc:
            global _WEBHOOK_SET_RATE_LIMIT_TOTAL
            _WEBHOOK_SET_RATE_LIMIT_TOTAL += 1
            retry_after = max(0.1, float(exc.retry_after or 0.5))
            logger.warning("WEBHOOK_SET_RATE_LIMIT retry_after_s=%s", retry_after)
            logger.info(
                "METRIC_GAUGE name=webhook_set_rate_limit_total value=%s retry_after_s=%s",
                _WEBHOOK_SET_RATE_LIMIT_TOTAL,
                retry_after,
            )
            _set_webhook_set_result("rate_limit", error_type="RetryAfter", error=str(exc))
            return False
        except Conflict as exc:
            logger.error("❌ Conflict detected while setting webhook: %s", exc)
            _set_webhook_set_result("conflict", error_type="Conflict", error=str(exc))
            raise
        except (TimedOut, httpx.ConnectTimeout, httpx.ReadTimeout, TimeoutError) as exc:
            logger.warning("WEBHOOK_SET_TIMEOUT error=%s", exc)
            _set_webhook_set_result("timeout", error_type="Timeout", error=str(exc))
            return False
        except asyncio.CancelledError as exc:
            logger.warning("WEBHOOK_SET_CANCELLED error=%s", exc)
            _set_webhook_set_result("cancelled", error_type="CancelledError", error=str(exc))
            raise
        except Exception as exc:
            logger.error("❌ Error setting webhook: %s", exc)
            _set_webhook_set_result("error", error_type=type(exc).__name__, error=str(exc))
            return False


def handle_conflict_gracefully(error: Conflict, mode: BotMode) -> None:
    """
    Graceful обработка Conflict ошибки
    Логирует и завершает процесс без агрессивных retry
    
    КРИТИЧНО: Использует os._exit(0) для немедленного завершения,
    чтобы предотвратить повторные конфликты и остановить polling loop немедленно.
    """
    logger.error(f"❌❌❌ Conflict detected in {mode} mode: {error}")
    logger.error("   Another instance is already running")
    logger.error("   Exiting gracefully to allow orchestrator restart")
    
    # НЕ делаем retry, НЕ перезапускаем - просто выходим
    # os._exit(0) завершает процесс немедленно, обходя cleanup handlers
    # Это предотвращает повторные конфликты и останавливает polling loop
    import os
    os._exit(0)
