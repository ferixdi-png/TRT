"""
Healthcheck endpoint для Render
Легкий aiohttp endpoint без потоков
"""

import time
import logging
import json
from aiohttp import web
from telegram import Update
from typing import Optional

from app.utils.logging_config import get_logger
from app.utils.correlation import ensure_correlation_id, correlation_tag

logger = get_logger(__name__)

_health_server: Optional[web.Application] = None
_health_runner: Optional[web.AppRunner] = None
_start_time: Optional[float] = None


def set_start_time():
    """Устанавливает время старта для расчета uptime"""
    global _start_time
    _start_time = time.time()


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
        "status": "ok",
        "uptime": uptime,
        "storage": storage_mode,
        "kie_mode": kie_mode
    }
    
    return web.Response(
        text=json.dumps(response_data),
        content_type="application/json",
        status=200
    )


async def webhook_handler(request, application, secret_path: str, secret_token: str):
    """Обработчик webhook апдейтов от Telegram."""
    if request.match_info.get("secret") != secret_path:
        return web.Response(status=404, text="not found")

    if secret_token:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_token != secret_token:
            return web.Response(status=403, text="forbidden")

    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")

    try:
        ensure_correlation_id(str(payload.get("update_id", "")))
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
    except Exception as exc:
        logger.warning(f"[WEBHOOK] {correlation_tag()} Failed to process update: {exc}")
        return web.Response(status=500, text="error")

    return web.Response(status=200, text="ok")


async def start_health_server(
    port: int = 8000,
    application=None,
    webhook_secret_path: str | None = None,
    webhook_secret_token: str | None = None,
):
    """Запустить healthcheck сервер в том же event loop"""
    global _health_server, _health_runner
    
    if port == 0:
        logger.info("[HEALTH] PORT not set, skipping healthcheck server")
        return False
    
    try:
        set_start_time()  # Устанавливаем время старта
        
        app = web.Application()
        app.router.add_get('/health', health_handler)
        app.router.add_get('/', health_handler)  # Для совместимости
        if application and webhook_secret_path:
            app.router.add_post(
                '/webhook/{secret}',
                lambda request: webhook_handler(
                    request,
                    application=application,
                    secret_path=webhook_secret_path,
                    secret_token=webhook_secret_token or "",
                ),
            )
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        _health_server = app
        _health_runner = runner
        
        logger.info(f"[HEALTH] Healthcheck server started on port {port}")
        logger.info(f"[HEALTH] Endpoints: /health, /")
        if application and webhook_secret_path:
            logger.info("[HEALTH] Webhook endpoint enabled")
        
        return True
    except Exception as e:
        logger.warning(f"[HEALTH] Failed to start healthcheck server: {e}")
        logger.warning("[HEALTH] Continuing without healthcheck (Render may mark service as unhealthy)")
        return False


async def stop_health_server():
    """Остановить healthcheck сервер"""
    global _health_server, _health_runner
    
    if _health_runner:
        try:
            await _health_runner.cleanup()
            logger.info("[HEALTH] Healthcheck server stopped")
        except Exception as e:
            logger.warning(f"[HEALTH] Failed to stop healthcheck server: {e}")
        finally:
            _health_server = None
            _health_runner = None
