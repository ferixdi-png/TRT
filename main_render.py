#!/usr/bin/env python3
"""
Render webhook entrypoint (PTB-based).

Minimal implementation for webhook tests + smoke scripts:
- build_webhook_handler() returns aiohttp handler that forwards updates into PTB Application
- correlation_id is logged for every request
- errors return a safe user-facing response (no silence)
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Awaitable, Callable, Optional

from aiohttp import web
from telegram import Update

from app.bootstrap import create_application
from app.middleware.rate_limit import PerKeyRateLimiter, TTLCache
from app.observability.structured_logs import log_structured_event
from app.utils.healthcheck import start_health_server, stop_health_server
from app.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

_app_ready_event = asyncio.Event()
_app_init_lock = asyncio.Lock()
_app_init_task: Optional[asyncio.Task] = None
_handler_ready: bool = False
_seen_update_ids: set[int] = set()
_early_update_count: int = 0
_early_update_log_last_ts: Optional[float] = None


def _is_application_initialized(application) -> bool:
    initialized_attr = getattr(application, "initialized", None)
    if isinstance(initialized_attr, bool):
        return initialized_attr
    return bool(getattr(application, "_initialized", False))


def _should_log_early_update(now: float, throttle_seconds: float) -> bool:
    global _early_update_log_last_ts
    if _early_update_log_last_ts is None or (now - _early_update_log_last_ts) >= throttle_seconds:
        _early_update_log_last_ts = now
        return True
    return False


def _resolve_correlation_id(request: web.Request) -> str:
    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Trace-ID")
        or "corr-webhook-unknown"
    )


def _resolve_client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.headers.get("X-Real-IP") or request.remote or "unknown"


def _is_duplicate(update_id: Optional[int]) -> bool:
    if update_id is None:
        return False
    if update_id in _seen_update_ids:
        return True
    _seen_update_ids.add(update_id)
    if len(_seen_update_ids) > 5000:
        _seen_update_ids.clear()
    return False


def build_webhook_handler(
    application,
    settings,
) -> Callable[[web.Request], Awaitable[web.StreamResponse]]:
    """Build aiohttp webhook handler that forwards updates to PTB application."""
    global _handler_ready
    max_payload_bytes = int(os.getenv("WEBHOOK_MAX_PAYLOAD_BYTES", "1048576"))
    ip_rate_limit_per_sec = float(os.getenv("WEBHOOK_IP_RATE_LIMIT_PER_SEC", "4"))
    ip_rate_limit_burst = float(os.getenv("WEBHOOK_IP_RATE_LIMIT_BURST", "12"))
    request_dedup_ttl_seconds = float(os.getenv("WEBHOOK_REQUEST_DEDUP_TTL_SECONDS", "30"))
    process_timeout_seconds = float(os.getenv("WEBHOOK_PROCESS_TIMEOUT_SECONDS", "8"))
    concurrency_limit = int(os.getenv("WEBHOOK_CONCURRENCY_LIMIT", "24"))
    concurrency_timeout_seconds = float(os.getenv("WEBHOOK_CONCURRENCY_TIMEOUT_SECONDS", "1.5"))
    early_update_retry_after = int(os.getenv("WEBHOOK_EARLY_UPDATE_RETRY_AFTER", "2"))
    early_update_log_throttle_seconds = float(os.getenv("WEBHOOK_EARLY_UPDATE_LOG_THROTTLE_SECONDS", "30"))

    ip_rate_limiter = (
        PerKeyRateLimiter(ip_rate_limit_per_sec, ip_rate_limit_burst)
        if ip_rate_limit_per_sec > 0 and ip_rate_limit_burst > 0
        else None
    )
    request_deduper = TTLCache(request_dedup_ttl_seconds)
    webhook_semaphore = asyncio.Semaphore(concurrency_limit) if concurrency_limit > 0 else None

    async def _handler(request: web.Request) -> web.StreamResponse:
        global _early_update_count
        correlation_id = _resolve_correlation_id(request)
        client_ip = _resolve_client_ip(request)

        if not _app_ready_event.is_set() or not _is_application_initialized(application):
            _early_update_count += 1
            update_id = None
            try:
                payload = await request.json()
                if isinstance(payload, dict):
                    update_id = payload.get("update_id")
            except Exception:
                update_id = None
            if _should_log_early_update(time.monotonic(), early_update_log_throttle_seconds):
                logger.info(
                    "action=WEBHOOK_EARLY_UPDATE correlation_id=%s update_id=%s ready=false "
                    "outcome=defer early_update_count=%s retry_after=%s",
                    correlation_id,
                    update_id,
                    _early_update_count,
                    early_update_retry_after,
                )
            return web.Response(status=204, headers={"Retry-After": str(early_update_retry_after)})

        logger.info("WEBHOOK correlation_id=%s update_received=true", correlation_id)

        content_length = request.content_length
        if content_length is not None and content_length > max_payload_bytes:
            log_structured_event(
                correlation_id=correlation_id,
                action="WEBHOOK_ABUSE",
                action_path="webhook:payload_too_large",
                outcome="rejected",
                error_id="WEBHOOK_PAYLOAD_TOO_LARGE",
                abuse_id="payload_oversize",
                param={"client_ip": client_ip, "content_length": content_length},
            )
            return web.json_response({"ok": False, "error": "payload_too_large"}, status=413)

        if ip_rate_limiter is not None:
            allowed, retry_after = ip_rate_limiter.check(client_ip)
            if not allowed:
                retry_after_seconds = max(1, int(math.ceil(retry_after)))
                log_structured_event(
                    correlation_id=correlation_id,
                    action="WEBHOOK_ABUSE",
                    action_path="webhook:rate_limit_ip",
                    outcome="throttled",
                    error_id="WEBHOOK_RATE_LIMIT",
                    abuse_id="rate_limit_ip",
                    param={"client_ip": client_ip, "retry_after": retry_after_seconds},
                )
                return web.json_response(
                    {"ok": False, "retry_after": retry_after_seconds},
                    status=429,
                    headers={"Retry-After": str(retry_after_seconds)},
                )

        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        if request_id and request_deduper.seen(request_id):
            log_structured_event(
                correlation_id=correlation_id,
                action="WEBHOOK_DEDUP",
                action_path="webhook:request_id",
                outcome="deduped",
                abuse_id="duplicate_request_id",
                param={"client_ip": client_ip},
            )
            return web.json_response({"ok": True}, status=200)

        try:
            payload = await request.json()
        except Exception:
            logger.warning("WEBHOOK correlation_id=%s payload_parse_failed=true", correlation_id)
            return web.json_response({"ok": False}, status=400)

        update_id = payload.get("update_id") if isinstance(payload, dict) else None
        if _is_duplicate(update_id):
            logger.info("WEBHOOK correlation_id=%s update_duplicate=true", correlation_id)
            return web.json_response({"ok": True}, status=200)

        update = Update.de_json(payload, application.bot)

        semaphore_acquired = False
        if webhook_semaphore is not None:
            try:
                await asyncio.wait_for(webhook_semaphore.acquire(), timeout=concurrency_timeout_seconds)
                semaphore_acquired = True
            except asyncio.TimeoutError:
                retry_after = max(1, int(math.ceil(concurrency_timeout_seconds)))
                log_structured_event(
                    correlation_id=correlation_id,
                    action="WEBHOOK_BACKPRESSURE",
                    action_path="webhook:concurrency_limit",
                    outcome="throttled",
                    error_id="WEBHOOK_CONCURRENCY_LIMIT",
                    abuse_id="concurrency_limit",
                    param={"client_ip": client_ip, "retry_after": retry_after},
                )
                return web.json_response(
                    {"ok": False, "retry_after": retry_after},
                    status=503,
                    headers={"Retry-After": str(retry_after)},
                )

        try:
            await asyncio.wait_for(application.process_update(update), timeout=process_timeout_seconds)
            logger.info("WEBHOOK correlation_id=%s forwarded_to_ptb=true", correlation_id)
            return web.json_response({"ok": True}, status=200)
        except asyncio.TimeoutError:
            retry_after = max(1, int(math.ceil(process_timeout_seconds)))
            log_structured_event(
                correlation_id=correlation_id,
                action="WEBHOOK_TIMEOUT",
                action_path="webhook:process_update",
                outcome="timeout",
                error_id="WEBHOOK_PROCESS_TIMEOUT",
                param={"client_ip": client_ip, "retry_after": retry_after},
            )
            return web.json_response(
                {"ok": False, "retry_after": retry_after},
                status=503,
                headers={"Retry-After": str(retry_after)},
            )
        except Exception as exc:
            logger.exception("WEBHOOK correlation_id=%s forward_failed=true error=%s", correlation_id, exc)
            chat_id = getattr(update.effective_chat, "id", None)
            if chat_id:
                try:
                    await application.bot.send_message(chat_id=chat_id, text="Ошибка обработки. Вернул в меню.")
                except Exception:
                    logger.warning("WEBHOOK correlation_id=%s fallback_send_failed=true", correlation_id)
            return web.json_response({"ok": True}, status=200)
        finally:
            if webhook_semaphore is not None and semaphore_acquired:
                webhook_semaphore.release()

    _handler_ready = True
    return _handler


async def _initialize_application(settings):
    init_started = time.monotonic()
    application = await create_application(settings)
    if os.getenv("TEST_MODE", "").strip() == "1":
        logger.info("TEST_MODE enabled; skipping Telegram API initialization.")
        setattr(application, "_initialized", True)
    else:
        await application.initialize()
    init_ms = int((time.monotonic() - init_started) * 1000)
    _app_ready_event.set()
    logger.info("action=WEBHOOK_APP_READY ready=true init_ms=%s", init_ms)
    return application


async def _get_initialized_application(settings):
    global _app_init_task
    async with _app_init_lock:
        if _app_init_task is None:
            _app_init_task = asyncio.create_task(_initialize_application(settings))
    return await _app_init_task


async def main() -> None:
    """Start webhook-mode PTB application and healthcheck server."""
    setup_logging()
    settings = None
    try:
        from app.config import Settings

        settings = Settings()
    except Exception:
        settings = None

    application = await _get_initialized_application(settings)
    if _early_update_count:
        logger.warning("WEBHOOK early_updates=%s gate=ready", _early_update_count)

    port = int(os.getenv("PORT", "10000"))
    webhook_handler = build_webhook_handler(application, settings)
    await start_health_server(port=port, webhook_handler=webhook_handler, self_check=True)

    try:
        await asyncio.Event().wait()
    finally:
        await stop_health_server()


if __name__ == "__main__":
    asyncio.run(main())
