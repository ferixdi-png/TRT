"""
Healthcheck endpoint для Render
Легкий aiohttp endpoint без потоков
"""

import time
import os
import logging
import json
import asyncio
from aiohttp import web
from typing import Optional, Callable, Awaitable, Dict

from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_health_server: Optional[web.Application] = None
_health_runner: Optional[web.AppRunner] = None
_start_time: Optional[float] = None
_health_server_running: bool = False
_webhook_route_registered: bool = False


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
    except:
        pass
    
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
        if hasattr(storage, "_get_pool") and asyncio.iscoroutinefunction(storage._get_pool):
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


async def start_health_server(
    port: int = 8000,
    webhook_handler: Optional[Callable[[web.Request], Awaitable[web.StreamResponse]]] = None,
    self_check: bool = False,
    **kwargs,
):
    """Запустить healthcheck сервер в том же event loop"""
    global _health_server, _health_runner, _health_server_running, _webhook_route_registered
    
    if port == 0:
        logger.info("[HEALTH] PORT not set, skipping healthcheck server")
        return False

    if _health_runner is not None:
        logger.info("[HEALTH] server_already_running=true port=%s", port)
        return True
    
    try:
        set_start_time()  # Устанавливаем время старта
        
        app = web.Application()
        app.router.add_get('/health', health_handler)
        app.router.add_get('/', health_handler)  # Для совместимости
        app.router.add_get('/__diag/billing_preflight', billing_preflight_handler)
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
        except Exception as e:
            logger.warning(f"[HEALTH] Failed to stop healthcheck server: {e}")
        finally:
            _health_server = None
            _health_runner = None
            _health_server_running = False
            _webhook_route_registered = False
