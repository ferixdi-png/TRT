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
from typing import Any, Awaitable, Callable, Dict, Optional

from aiohttp import web
from telegram import Update

from app.bootstrap import create_application
from app.middleware.rate_limit import PerKeyRateLimiter, TTLCache
from app.observability.structured_logs import log_critical_event, log_structured_event
from app.observability.update_metrics import increment_metric as increment_update_metric
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
    ack_max_ms = int(os.getenv("WEBHOOK_ACK_MAX_MS", "200"))
    early_update_retry_after = int(os.getenv("WEBHOOK_EARLY_UPDATE_RETRY_AFTER", "2"))
    early_update_log_throttle_seconds = float(os.getenv("WEBHOOK_EARLY_UPDATE_LOG_THROTTLE_SECONDS", "30"))
    handler_stall_seconds = float(os.getenv("WEBHOOK_HANDLER_STALL_SECONDS", "6.0"))

    ip_rate_limiter = (
        PerKeyRateLimiter(ip_rate_limit_per_sec, ip_rate_limit_burst)
        if ip_rate_limit_per_sec > 0 and ip_rate_limit_burst > 0
        else None
    )
    request_deduper = TTLCache(request_dedup_ttl_seconds)
    webhook_semaphore = asyncio.Semaphore(concurrency_limit) if concurrency_limit > 0 else None
    process_in_background_raw = os.getenv("WEBHOOK_PROCESS_IN_BACKGROUND")
    test_mode = os.getenv("TEST_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    if process_in_background_raw is None:
        process_in_background = not test_mode
    else:
        process_in_background = process_in_background_raw.strip().lower() in {"1", "true", "yes", "on"}
    early_ack_raw = os.getenv("WEBHOOK_EARLY_ACK")
    if early_ack_raw is None:
        early_ack_enabled = not test_mode
    else:
        early_ack_enabled = early_ack_raw.strip().lower() in {"1", "true", "yes", "on"}
    ack_in_background = True

    def _resolve_update_type(update: Update) -> str:
        if update.callback_query:
            return "callback"
        if update.message:
            return "message"
        if update.edited_message:
            return "edited_message"
        if update.inline_query:
            return "inline_query"
        return "unknown"

    async def _watchdog_handler_stall(
        task: asyncio.Task,
        *,
        correlation_id: str,
        update_id: Optional[int],
        deadline_s: float,
    ) -> None:
        await asyncio.sleep(deadline_s)
        if task.done():
            return
        where = None
        try:
            frames = task.get_stack(limit=3)
            if frames:
                frame = frames[-1]
                where = f"{frame.f_code.co_filename}:{frame.f_lineno}:{frame.f_code.co_name}"
        except Exception:
            where = None
        log_critical_event(
            correlation_id=correlation_id,
            update_id=update_id,
            stage="HANDLER",
            latency_ms=None,
            retry_after=None,
            timeout_s=None,
            attempt=None,
            error_code="HANDLER_STALL",
            error_id="HANDLER_STALL",
            exception_class=None,
            where=where,
            fix_hint="Check slow handler dependencies/locks; move heavy work off hot path.",
            retryable=True,
            upstream=None,
            deadline_s=deadline_s,
            elapsed_ms=deadline_s * 1000,
        )

    def _schedule_task(coro: Awaitable[None], *, correlation_id: str) -> None:
        task = asyncio.create_task(coro)

        def _on_done(done_task: asyncio.Task) -> None:
            try:
                done_task.result()
            except asyncio.CancelledError:
                logger.info("WEBHOOK correlation_id=%s background_task_cancelled=true", correlation_id)
            except Exception:
                logger.exception("WEBHOOK correlation_id=%s background_task_failed=true", correlation_id)

        task.add_done_callback(_on_done)

    async def _process_update_async(
        update: Update,
        *,
        correlation_id: str,
        client_ip: str,
        semaphore_acquired: bool,
        route: str,
        request_id: Optional[str],
    ) -> None:
        process_started = time.monotonic()
        update_id = getattr(update, "update_id", None)
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        increment_update_metric("webhook_process_start")
        log_structured_event(
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=user_id,
            chat_id=chat_id,
            update_id=update_id,
            action="WEBHOOK_PROCESS_START",
            action_path="webhook:process_update",
            stage="WEBHOOK",
            outcome="start",
            update_type=_resolve_update_type(update),
            route=route,
        )
        process_task = asyncio.create_task(application.process_update(update))
        watchdog_task = asyncio.create_task(
            _watchdog_handler_stall(
                process_task,
                correlation_id=correlation_id,
                update_id=update_id,
                deadline_s=handler_stall_seconds,
            )
        )
        release_in_finally = True

        def _release_after_task(done_task: asyncio.Task) -> None:
            if webhook_semaphore is not None and semaphore_acquired:
                webhook_semaphore.release()
            try:
                done_task.result()
                log_structured_event(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update_id,
                    action="WEBHOOK_PROCESS_LATE_DONE",
                    action_path="webhook:process_update",
                    stage="WEBHOOK",
                    outcome="ok",
                    param={"duration_ms": int((time.monotonic() - process_started) * 1000)},
                    update_type=_resolve_update_type(update),
                    route=route,
                )
            except Exception as exc:
                log_structured_event(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    update_id=update_id,
                    action="WEBHOOK_PROCESS_LATE_DONE",
                    action_path="webhook:process_update",
                    stage="WEBHOOK",
                    outcome="failed",
                    error_id="WEBHOOK_PROCESS_FAILED",
                    param={"error": str(exc)[:200]},
                    update_type=_resolve_update_type(update),
                    route=route,
                )

        outcome = "ok"
        try:
            await asyncio.shield(process_task)
            duration_ms = int((time.monotonic() - process_started) * 1000)
            increment_update_metric("webhook_process_done")
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="WEBHOOK_PROCESS_DONE",
                action_path="webhook:process_update",
                stage="WEBHOOK",
                outcome="ok",
                duration_ms=duration_ms,
                handler_total_ms=duration_ms,
                update_type=_resolve_update_type(update),
                route=route,
            )
            logger.info("WEBHOOK correlation_id=%s forwarded_to_ptb=true", correlation_id)
        except Exception as exc:
            outcome = "failed"
            increment_update_metric("webhook_process_done")
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="WEBHOOK_PROCESS_DONE",
                action_path="webhook:process_update",
                stage="WEBHOOK",
                outcome="failed",
                error_id="WEBHOOK_PROCESS_FAILED",
                param={"error": str(exc)[:200]},
                update_type=_resolve_update_type(update),
                route=route,
            )
            logger.exception("WEBHOOK correlation_id=%s forward_failed=true error=%s", correlation_id, exc)
            if chat_id:
                try:
                    await application.bot.send_message(chat_id=chat_id, text="Ошибка обработки. Вернул в меню.")
                    increment_update_metric("send_message")
                except Exception:
                    logger.warning("WEBHOOK correlation_id=%s fallback_send_failed=true", correlation_id)
        finally:
            if release_in_finally and webhook_semaphore is not None and semaphore_acquired:
                webhook_semaphore.release()
            handler_total_ms = int((time.monotonic() - process_started) * 1000)
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                user_id=user_id,
                chat_id=chat_id,
                update_id=update_id,
                action="HANDLER_DONE",
                action_path="webhook:handler",
                stage="HANDLER",
                outcome=outcome,
                handler_total_ms=handler_total_ms,
                update_type=_resolve_update_type(update),
                route=route,
            )
            if not watchdog_task.done():
                watchdog_task.cancel()

    async def _process_update_with_semaphore(
        update: Update,
        *,
        correlation_id: str,
        client_ip: str,
        route: str,
        request_id: Optional[str],
    ) -> None:
        semaphore_acquired = False
        if webhook_semaphore is not None:
            try:
                await asyncio.wait_for(webhook_semaphore.acquire(), timeout=concurrency_timeout_seconds)
                semaphore_acquired = True
            except asyncio.TimeoutError:
                retry_after = max(1, int(math.ceil(concurrency_timeout_seconds)))
                log_structured_event(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    action="WEBHOOK_BACKPRESSURE",
                    action_path="webhook:concurrency_limit",
                    outcome="throttled",
                    error_id="WEBHOOK_CONCURRENCY_LIMIT",
                    abuse_id="concurrency_limit",
                    param={"client_ip": client_ip, "retry_after": retry_after},
                    route=route,
                )
                return
        await _process_update_async(
            update,
            correlation_id=correlation_id,
            client_ip=client_ip,
            semaphore_acquired=semaphore_acquired,
            route=route,
            request_id=request_id,
        )

    async def _handle_webhook_payload(
        payload: Dict[str, Any],
        *,
        correlation_id: str,
        client_ip: str,
        route: str,
        request_id: Optional[str],
    ) -> None:
        update_id = None
        try:
            if not isinstance(payload, dict):
                logger.warning(
                    "WEBHOOK correlation_id=%s payload_type_invalid type=%s",
                    correlation_id,
                    type(payload).__name__,
                )
                return
            update = Update.de_json(payload, application.bot)
            update_id = getattr(update, "update_id", None)
            if _is_duplicate(update_id):
                increment_update_metric("webhook_update_in")
                log_structured_event(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    user_id=update.effective_user.id if update.effective_user else None,
                    chat_id=update.effective_chat.id if update.effective_chat else None,
                    update_id=update_id,
                    action="WEBHOOK_UPDATE_IN",
                    action_path="webhook:update",
                    stage="WEBHOOK",
                    outcome="deduped",
                    update_type=_resolve_update_type(update),
                    route=route,
                )
                logger.info("WEBHOOK correlation_id=%s update_duplicate=true", correlation_id)
                return
            increment_update_metric("webhook_update_in")
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                user_id=update.effective_user.id if update.effective_user else None,
                chat_id=update.effective_chat.id if update.effective_chat else None,
                update_id=update_id,
                action="WEBHOOK_UPDATE_IN",
                action_path="webhook:update",
                stage="WEBHOOK",
                outcome="received",
                update_type=_resolve_update_type(update),
                route=route,
            )
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                user_id=update.effective_user.id if update.effective_user else None,
                chat_id=update.effective_chat.id if update.effective_chat else None,
                update_id=update_id,
                action="HANDLER_START",
                action_path="webhook:handler",
                stage="HANDLER",
                outcome="start",
                update_type=_resolve_update_type(update),
                route=route,
            )
            await _process_update_with_semaphore(
                update,
                correlation_id=correlation_id,
                client_ip=client_ip,
                route=route,
                request_id=request_id,
            )
        except Exception as exc:
            logger.exception("WEBHOOK correlation_id=%s handler_failed=true error=%s", correlation_id, exc)
            log_critical_event(
                correlation_id=correlation_id,
                update_id=update_id,
                stage="WEBHOOK",
                latency_ms=None,
                retry_after=None,
                timeout_s=process_timeout_seconds,
                attempt=None,
                error_code="WEBHOOK_HANDLER_EXCEPTION",
                error_id="WEBHOOK_HANDLER_EXCEPTION",
                exception_class=type(exc).__name__,
                where="webhook_handler",
                fix_hint="Inspect webhook handler error and payload parsing.",
                retryable=False,
                upstream="telegram",
                elapsed_ms=None,
            )

    async def _handler(request: web.Request) -> web.StreamResponse:
        global _early_update_count
        handler_start = time.monotonic()
        correlation_id = _resolve_correlation_id(request)
        client_ip = _resolve_client_ip(request)
        update_id: Optional[int] = None
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        ack_deadline_ms = ack_max_ms
        ack_sent_ms: Optional[int] = None

        def _ack_response(response: web.StreamResponse) -> web.StreamResponse:
            nonlocal ack_sent_ms
            ack_sent_ms = int((time.monotonic() - handler_start) * 1000)
            return response

        log_structured_event(
            correlation_id=correlation_id,
            request_id=request_id,
            action="ACK_SCHEDULED",
            action_path="webhook:ack",
            stage="WEBHOOK",
            outcome="scheduled",
            ack_ms=0,
            route=request.path,
            param={"ack_deadline_ms": ack_deadline_ms},
        )
        try:
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
                return _ack_response(
                    web.Response(status=204, headers={"Retry-After": str(early_update_retry_after)})
                )

            logger.info("WEBHOOK correlation_id=%s update_received=true", correlation_id)

            content_length = request.content_length
            if content_length is not None and content_length > max_payload_bytes:
                log_structured_event(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    action="WEBHOOK_ABUSE",
                    action_path="webhook:payload_too_large",
                    outcome="rejected",
                    error_id="WEBHOOK_PAYLOAD_TOO_LARGE",
                    abuse_id="payload_oversize",
                    param={"client_ip": client_ip, "content_length": content_length},
                    route=request.path,
                )
                return _ack_response(
                    web.json_response({"ok": False, "error": "payload_too_large"}, status=413)
                )

            if ip_rate_limiter is not None:
                allowed, retry_after = ip_rate_limiter.check(client_ip)
                if not allowed:
                    retry_after_seconds = max(1, int(math.ceil(retry_after)))
                    log_structured_event(
                        correlation_id=correlation_id,
                        request_id=request_id,
                        action="WEBHOOK_ABUSE",
                        action_path="webhook:rate_limit_ip",
                        outcome="throttled",
                        error_id="WEBHOOK_RATE_LIMIT",
                        abuse_id="rate_limit_ip",
                        param={"client_ip": client_ip, "retry_after": retry_after_seconds},
                        route=request.path,
                    )
                    return _ack_response(
                        web.json_response(
                            {"ok": False, "retry_after": retry_after_seconds},
                            status=429,
                            headers={"Retry-After": str(retry_after_seconds)},
                        )
                    )

            if request_id and request_deduper.seen(request_id):
                log_structured_event(
                    correlation_id=correlation_id,
                    request_id=request_id,
                    action="WEBHOOK_DEDUP",
                    action_path="webhook:request_id",
                    outcome="deduped",
                    abuse_id="duplicate_request_id",
                    param={"client_ip": client_ip},
                    route=request.path,
                )
                return _ack_response(web.json_response({"ok": True}, status=200))

            try:
                raw_body = await request.read()
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception:
                logger.warning("WEBHOOK correlation_id=%s payload_parse_failed=true", correlation_id)
                return _ack_response(web.json_response({"ok": False}, status=400))
            if isinstance(payload, dict):
                update_id = payload.get("update_id")

            if ack_in_background:
                logger.info("WEBHOOK correlation_id=%s forwarded_to_ptb=true", correlation_id)
                _schedule_task(
                    _handle_webhook_payload(
                        payload,
                        correlation_id=correlation_id,
                        client_ip=client_ip,
                        route=request.path,
                        request_id=request_id,
                    ),
                    correlation_id=correlation_id,
                )
            else:
                await _handle_webhook_payload(
                    payload,
                    correlation_id=correlation_id,
                    client_ip=client_ip,
                    route=request.path,
                    request_id=request_id,
                )
            return _ack_response(web.json_response({"ok": True}, status=200))
        except Exception as exc:
            logger.exception("WEBHOOK correlation_id=%s handler_failed=true error=%s", correlation_id, exc)
            log_critical_event(
                correlation_id=correlation_id,
                update_id=update_id,
                stage="WEBHOOK",
                latency_ms=None,
                retry_after=None,
                timeout_s=process_timeout_seconds,
                attempt=None,
                error_code="WEBHOOK_HANDLER_EXCEPTION",
                error_id="WEBHOOK_HANDLER_EXCEPTION",
                exception_class=type(exc).__name__,
                where="webhook_handler",
                fix_hint="Inspect webhook handler error and payload parsing.",
                retryable=False,
                upstream="telegram",
                elapsed_ms=(time.monotonic() - handler_start) * 1000,
            )
            return _ack_response(web.json_response({"ok": False, "error": "handler_failed"}, status=500))
        finally:
            duration_ms = ack_sent_ms if ack_sent_ms is not None else int((time.monotonic() - handler_start) * 1000)
            try:
                loop = asyncio.get_running_loop()
                event_loop_lag_ms = max(0.0, (time.monotonic() - loop.time()) * 1000)
            except RuntimeError:
                event_loop_lag_ms = None
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                update_id=update_id,
                action="WEBHOOK_ACK",
                action_path="webhook:handler",
                stage="WEBHOOK",
                outcome="ok",
                ack_ms=duration_ms,
                handler_total_ms=None,
                route=request.path,
            )
            log_structured_event(
                correlation_id=correlation_id,
                request_id=request_id,
                update_id=update_id,
                action="WEBHOOK_TIMING_PROFILE",
                action_path="webhook:timing",
                stage="WEBHOOK",
                outcome="ok",
                ack_ms=duration_ms,
                handler_total_ms=None,
                event_loop_lag_ms=event_loop_lag_ms,
                route=request.path,
            )
            if duration_ms > ack_max_ms:
                logger.warning("WEBHOOK_ACK_SLOW correlation_id=%s duration_ms=%s", correlation_id, duration_ms)

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
