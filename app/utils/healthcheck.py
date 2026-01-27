"""
Healthcheck endpoint для Render
Легкий aiohttp endpoint без потоков
"""

import asyncio
import inspect
import json
import logging
import os
import time
from aiohttp import web
from typing import Optional, Callable, Awaitable, Dict, Any, List

from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_health_server: Optional[web.Application] = None
_health_runner: Optional[web.AppRunner] = None
_start_time: Optional[float] = None
_health_server_running: bool = False
_webhook_route_registered: bool = False
_health_lock: Optional[asyncio.Lock] = None


def set_start_time():
    """Устанавливает время старта для расчета uptime"""
    global _start_time
    _start_time = time.time()


def get_health_status() -> Dict[str, Optional[object]]:
    return {
        "health_server_running": _health_server_running,
        "webhook_route_registered": _webhook_route_registered,
        "start_time": _start_time,
    }


async def health_handler(request):
    """Обработчик healthcheck запросов"""
    import os
    
    # Рассчитываем uptime
    uptime = 0
    if _start_time:
        uptime = int(time.time() - _start_time)
    
    # Определяем storage mode
    storage_mode = "unknown"
    try:
        from app.config import get_settings
        settings = get_settings()
        storage_mode = settings.get_storage_mode()
    except Exception as exc:
        logger.debug("healthcheck_storage_mode_failed error=%s", exc, exc_info=True)
    
    # Определяем KIE mode
    kie_mode = "stub" if os.getenv("KIE_STUB") else "real"
    if not os.getenv("KIE_API_KEY"):
        kie_mode = "disabled"
    
    # Формируем JSON ответ
    response_data = {
        "ok": True,
        "status": "ok",
        "uptime": uptime,
        "storage": storage_mode,
        "kie_mode": kie_mode,
        "webhook_route_registered": _webhook_route_registered,
    }
    try:
        from app.config import get_settings
        settings = get_settings()
        response_data["bot_mode"] = settings.bot_mode
        response_data["instance"] = settings.bot_instance_id or os.getenv("BOT_INSTANCE_ID", "")
    except Exception:
        response_data["bot_mode"] = os.getenv("BOT_MODE", "")
        response_data["instance"] = os.getenv("BOT_INSTANCE_ID", "")
    
    return web.Response(
        text=json.dumps(response_data),
        content_type="application/json",
        status=200
    )


async def webhook_health_echo(request):
    """Echo endpoint for webhook POST healthchecks."""
    payload = {
        "ok": True,
        "status": "ok",
        "path": "/webhook/health",
        "method": request.method,
    }
    return web.Response(
        text=json.dumps(payload),
        content_type="application/json",
        status=200,
    )


async def billing_preflight_handler(request):
    """Billing preflight diagnostic endpoint."""
    from app.diagnostics.billing_preflight import (
        build_billing_preflight_log_payload,
        run_billing_preflight,
    )
    from app.storage.factory import get_storage

    try:
        timeout_seconds = float(os.getenv("BILLING_PREFLIGHT_HTTP_TIMEOUT_SECONDS", "5.0"))
        storage = get_storage()
        db_pool = None
        if hasattr(storage, "_get_pool") and inspect.iscoroutinefunction(storage._get_pool):
            db_pool = await storage._get_pool()

        report = await asyncio.wait_for(
            run_billing_preflight(storage, db_pool, emit_logs=False),
            timeout=timeout_seconds,
        )
        payload = build_billing_preflight_log_payload(report)
        logger.info(
            "BILLING_PREFLIGHT_RUNTIME %s",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
        return web.Response(
            text=json.dumps(payload),
            content_type="application/json",
            status=200,
        )
    except asyncio.TimeoutError:
        payload = {
            "ok": False,
            "status": "timeout",
            "error": "billing_preflight_timeout",
        }
        logger.warning("[BILLING_PREFLIGHT] runtime_timeout timeout_s=%s", timeout_seconds)
        return web.Response(
            text=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
            status=503,
        )
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "error",
            "error": "billing_preflight_failed",
            "detail": str(exc)[:200],
        }
        logger.exception("[BILLING_PREFLIGHT] runtime_failed error=%s", exc)
        return web.Response(
            text=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
            status=503,
        )


async def telegram_diag_handler(request):
    """Telegram diagnostics: webhook info, webhook set (same URL), sendMessage to ADMIN_ID."""
    from telegram import Bot
    from telegram.request import HTTPXRequest

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        payload = {"ok": False, "status": "error", "error": "missing_bot_token"}
        return web.Response(text=json.dumps(payload), content_type="application/json", status=503)

    timeout_seconds = float(os.getenv("TELEGRAM_DIAG_TIMEOUT_SECONDS", "6.0"))
    connect_timeout = float(os.getenv("TELEGRAM_HTTP_CONNECT_TIMEOUT_SECONDS", "5.0"))
    read_timeout = float(os.getenv("TELEGRAM_HTTP_READ_TIMEOUT_SECONDS", "15.0"))
    write_timeout = float(os.getenv("TELEGRAM_HTTP_WRITE_TIMEOUT_SECONDS", "15.0"))
    pool_timeout = float(os.getenv("TELEGRAM_HTTP_POOL_TIMEOUT_SECONDS", "5.0"))
    request = HTTPXRequest(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
        pool_timeout=pool_timeout,
    )

    webhook_url = ""
    try:
        from app.config import get_settings

        settings = get_settings()
        webhook_url = settings.webhook_url
    except Exception:
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()

    admin_id_raw = os.getenv("ADMIN_ID", "").strip()
    try:
        admin_id = int(admin_id_raw.split(",")[0]) if admin_id_raw else 0
    except ValueError:
        admin_id = 0

    result = {
        "ok": True,
        "status": "ok",
        "webhook_info": None,
        "webhook_set": None,
        "send_message": None,
    }

    async with Bot(token=token, request=request) as bot:
        try:
            start = time.monotonic()
            info = await asyncio.wait_for(bot.get_webhook_info(), timeout=timeout_seconds)
            result["webhook_info"] = {
                "ok": True,
                "lat_ms": int((time.monotonic() - start) * 1000),
                "url": getattr(info, "url", ""),
                "pending_update_count": getattr(info, "pending_update_count", None),
            }
        except Exception as exc:
            result["ok"] = False
            result["webhook_info"] = {"ok": False, "error": str(exc)[:200]}

        if webhook_url:
            try:
                start = time.monotonic()
                await asyncio.wait_for(
                    bot.set_webhook(url=webhook_url, drop_pending_updates=False),
                    timeout=timeout_seconds,
                )
                result["webhook_set"] = {
                    "ok": True,
                    "lat_ms": int((time.monotonic() - start) * 1000),
                    "url": webhook_url,
                }
            except Exception as exc:
                result["ok"] = False
                result["webhook_set"] = {"ok": False, "error": str(exc)[:200], "url": webhook_url}
        else:
            result["webhook_set"] = {"ok": False, "skipped": True, "reason": "missing_webhook_url"}

        if admin_id:
            try:
                start = time.monotonic()
                await asyncio.wait_for(
                    bot.send_message(chat_id=admin_id, text="✅ Telegram diag ping"),
                    timeout=timeout_seconds,
                )
                result["send_message"] = {
                    "ok": True,
                    "lat_ms": int((time.monotonic() - start) * 1000),
                    "admin_id": admin_id,
                }
            except Exception as exc:
                result["ok"] = False
                result["send_message"] = {"ok": False, "error": str(exc)[:200], "admin_id": admin_id}
        else:
            result["send_message"] = {"ok": False, "skipped": True, "reason": "missing_admin_id"}

    return web.Response(
        text=json.dumps(result, ensure_ascii=False),
        content_type="application/json",
        status=200 if result["ok"] else 503,
    )


async def ready_diag_handler(request):
    """Production-ready diagnostics: webhook info, DB ping, lock status, recent CRIT events."""
    from telegram import Bot
    from telegram.request import HTTPXRequest
    from app.storage.factory import get_storage
    from app.utils.singleton_lock import get_lock_degraded_reason, get_lock_mode, is_lock_degraded
    from app.observability.structured_logs import get_recent_critical_event_ids

    timeout_seconds = float(os.getenv("READY_DIAG_TIMEOUT_SECONDS", "6.0"))
    connect_timeout = float(os.getenv("TELEGRAM_HTTP_CONNECT_TIMEOUT_SECONDS", "5.0"))
    read_timeout = float(os.getenv("TELEGRAM_HTTP_READ_TIMEOUT_SECONDS", "15.0"))
    write_timeout = float(os.getenv("TELEGRAM_HTTP_WRITE_TIMEOUT_SECONDS", "15.0"))
    pool_timeout = float(os.getenv("TELEGRAM_HTTP_POOL_TIMEOUT_SECONDS", "5.0"))
    request_cfg = HTTPXRequest(
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
        pool_timeout=pool_timeout,
    )

    webhook_url = ""
    try:
        from app.config import get_settings

        settings = get_settings()
        webhook_url = settings.webhook_url
    except Exception:
        webhook_url = os.getenv("WEBHOOK_URL", "").strip()

    result: Dict[str, Any] = {
        "ok": True,
        "status": "READY",
        "webhook": {},
        "db": {},
        "lock": {},
        "crit_event_ids": get_recent_critical_event_ids(),
        "how_to_fix": [],
    }

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        async with Bot(token=token, request=request_cfg) as bot:
            try:
                start = time.monotonic()
                info = await asyncio.wait_for(bot.get_webhook_info(), timeout=timeout_seconds)
                latency_ms = int((time.monotonic() - start) * 1000)
                current_url = getattr(info, "url", "") or ""
                result["webhook"] = {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "current_url": current_url,
                    "expected_url": webhook_url,
                    "pending_update_count": getattr(info, "pending_update_count", None),
                    "match": bool(webhook_url and current_url == webhook_url),
                }
                if webhook_url and current_url != webhook_url:
                    result["ok"] = False
                    result["status"] = "DEGRADED"
                    result["how_to_fix"].append("Set Telegram webhook URL to match WEBHOOK_URL.")
            except Exception as exc:
                result["ok"] = False
                result["status"] = "DEGRADED"
                result["webhook"] = {"ok": False, "error": str(exc)[:200]}
                result["how_to_fix"].append("Check Telegram API connectivity and webhook configuration.")
    else:
        result["ok"] = False
        result["status"] = "DEGRADED"
        result["webhook"] = {"ok": False, "error": "missing_bot_token"}
        result["how_to_fix"].append("Set TELEGRAM_BOT_TOKEN for webhook diagnostics.")

    storage = None
    try:
        storage = get_storage()
    except Exception as exc:
        result["ok"] = False
        result["status"] = "DEGRADED"
        result["db"] = {"ok": False, "error": str(exc)[:200]}
        result["how_to_fix"].append("Ensure storage backend is configured and reachable.")

    if storage is not None:
        db_meta: Dict[str, Any] = {}
        try:
            start = time.monotonic()
            if hasattr(storage, "ping") and inspect.iscoroutinefunction(storage.ping):
                ping_ok = await asyncio.wait_for(storage.ping(), timeout=timeout_seconds)
            else:
                ping_ok = True
            latency_ms = int((time.monotonic() - start) * 1000)
            pool_in_use = None
            pool_size = None
            if hasattr(storage, "_get_pool") and inspect.iscoroutinefunction(storage._get_pool):
                pool = await storage._get_pool()
                try:
                    pool_size = pool.get_max_size() if hasattr(pool, "get_max_size") else None
                    if hasattr(pool, "get_size") and hasattr(pool, "get_idle_size"):
                        pool_in_use = pool.get_size() - pool.get_idle_size()
                except Exception:
                    pool_in_use = None
                    pool_size = None
            db_meta = {
                "ok": bool(ping_ok),
                "latency_ms": latency_ms,
                "pool_in_use": pool_in_use,
                "pool_size": pool_size,
            }
            if not ping_ok:
                result["ok"] = False
                result["status"] = "DEGRADED"
                result["how_to_fix"].append("Check DATABASE_URL connectivity and pool saturation.")
        except Exception as exc:
            result["ok"] = False
            result["status"] = "DEGRADED"
            db_meta = {"ok": False, "error": str(exc)[:200]}
            result["how_to_fix"].append("Inspect database connectivity and credentials.")
        result["db"] = db_meta

    lock_mode = get_lock_mode()
    degraded_reason = get_lock_degraded_reason()
    lock_degraded = is_lock_degraded()
    result["lock"] = {
        "ok": not lock_degraded,
        "mode": lock_mode,
        "degraded": lock_degraded,
        "degraded_reason": degraded_reason,
    }
    if lock_degraded:
        result["ok"] = False
        result["status"] = "DEGRADED"
        result["how_to_fix"].append("Restore Redis lock backend or ensure Postgres advisory lock is reachable.")

    return web.Response(
        text=json.dumps(result, ensure_ascii=False),
        content_type="application/json",
        status=200 if result["ok"] else 503,
    )


async def start_health_server(
    port: int = 8000,
    webhook_handler: Optional[Callable[[web.Request], Awaitable[web.StreamResponse]]] = None,
    self_check: bool = False,
    **kwargs,
):
    """Запустить healthcheck сервер в том же event loop"""
    global _health_server, _health_runner, _health_server_running, _webhook_route_registered, _health_lock

    if _health_runner is not None and _health_server_running:
        return True

    if _health_lock is None:
        _health_lock = asyncio.Lock()

    if port == 0:
        logger.info("[HEALTH] PORT not set, skipping healthcheck server")
        return False

    async with _health_lock:
        if _health_runner is not None and _health_server_running:
            return True

        try:
            set_start_time()  # Устанавливаем время старта

            app = web.Application()
            app.router.add_get('/health', health_handler)
            app.router.add_get('/healthz', health_handler)
            app.router.add_get('/', health_handler)  # Для совместимости
            app.router.add_get('/__diag/billing_preflight', billing_preflight_handler)
            app.router.add_get('/diag/telegram', telegram_diag_handler)
            app.router.add_get('/diag/ready', ready_diag_handler)
            app.router.add_post('/webhook/health', webhook_health_echo)
            if webhook_handler is not None:
                try:
                    app.router.add_post('/webhook', webhook_handler)
                    _webhook_route_registered = True
                    logger.info("[WEBHOOK] route_registered=true path=/webhook")
                except Exception as exc:
                    _webhook_route_registered = False
                    logger.warning(
                        "[WEBHOOK] route_registered=false path=/webhook reason=registration_error error=%s",
                        exc,
                    )
            else:
                _webhook_route_registered = False
                logger.warning("[WEBHOOK] route_registered=false path=/webhook reason=handler_missing")

            runner = web.AppRunner(app)
            await runner.setup()

            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()

            logger.info("[HEALTH] port_bound=true host=0.0.0.0 port=%s", port)
            if self_check:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", port),
                        timeout=0.5,
                    )
                    writer.close()
                    if hasattr(writer, "wait_closed"):
                        await writer.wait_closed()
                    logger.info("[HEALTH] self_check_ok=true host=127.0.0.1 port=%s", port)
                except Exception as exc:
                    logger.warning(
                        "[HEALTH] self_check_ok=false host=127.0.0.1 port=%s error=%s",
                        port,
                        exc,
                    )

            _health_server = app
            _health_runner = runner
            _health_server_running = True

            logger.info(f"[HEALTH] Healthcheck server started on port {port}")
            logger.info(f"[HEALTH] Endpoints: /health, /")

            return True
        except Exception as e:
            _health_server_running = False
            logger.warning(f"[HEALTH] Failed to start healthcheck server: {e}")
            logger.warning("[HEALTH] Continuing without healthcheck (Render may mark service as unhealthy)")
            return False


async def stop_health_server():
    """Остановить healthcheck сервер"""
    global _health_server, _health_runner, _health_server_running, _webhook_route_registered
    
    if _health_runner:
        try:
            await _health_runner.cleanup()
            logger.info("[HEALTH] Healthcheck server stopped")
        except RuntimeError as exc:
            if "Event loop is closed" in str(exc):
                logger.warning("[HEALTH] Event loop closed while stopping healthcheck server")
            else:
                logger.warning("[HEALTH] Failed to stop healthcheck server: %s", exc)
        except Exception as e:
            logger.warning(f"[HEALTH] Failed to stop healthcheck server: {e}")
        finally:
            _health_server = None
            _health_runner = None
            _health_server_running = False
            _webhook_route_registered = False
