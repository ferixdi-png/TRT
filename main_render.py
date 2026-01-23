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
import os
import time
from typing import Awaitable, Callable, Optional

from aiohttp import web
from telegram import Update

from app.bootstrap import create_application
from app.utils.healthcheck import start_health_server, stop_health_server
from app.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

_app_ready_event = asyncio.Event()
_app_init_lock = asyncio.Lock()
_app_init_task: Optional[asyncio.Task] = None
_handler_ready: bool = False
_seen_update_ids: set[int] = set()
_early_update_count: int = 0


def _resolve_correlation_id(request: web.Request) -> str:
    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or request.headers.get("X-Trace-ID")
        or "corr-webhook-unknown"
    )


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

    async def _handler(request: web.Request) -> web.StreamResponse:
        global _early_update_count
        correlation_id = _resolve_correlation_id(request)

        if not _app_ready_event.is_set():
            _early_update_count += 1
            update_id = None
            try:
                payload = await request.json()
                if isinstance(payload, dict):
                    update_id = payload.get("update_id")
            except Exception as exc:
                logger.warning(
                    "action=WEBHOOK_EARLY_UPDATE correlation_id=%s ready=false outcome=reject_503 "
                    "dropped=true parse_error=%s",
                    correlation_id,
                    exc,
                )
            retry_after = 2
            logger.warning(
                "action=WEBHOOK_EARLY_UPDATE correlation_id=%s update_id=%s ready=false "
                "outcome=reject_503 dropped=true early_update_count=%s retry_after=%s",
                correlation_id,
                update_id,
                _early_update_count,
                retry_after,
            )
            return web.json_response(
                {"ok": False, "retry_after": retry_after},
                status=503,
                headers={"Retry-After": str(retry_after)},
            )

        logger.info("WEBHOOK correlation_id=%s update_received=true", correlation_id)

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

        try:
            await application.process_update(update)
            logger.info("WEBHOOK correlation_id=%s forwarded_to_ptb=true", correlation_id)
            return web.json_response({"ok": True}, status=200)
        except Exception as exc:
            logger.exception("WEBHOOK correlation_id=%s forward_failed=true error=%s", correlation_id, exc)
            chat_id = getattr(update.effective_chat, "id", None)
            if chat_id:
                try:
                    await application.bot.send_message(chat_id=chat_id, text="Ошибка обработки. Вернул в меню.")
                except Exception:
                    logger.warning("WEBHOOK correlation_id=%s fallback_send_failed=true", correlation_id)
            return web.json_response({"ok": True}, status=200)

    _handler_ready = True
    return _handler


async def _initialize_application(settings):
    init_started = time.monotonic()
    application = await create_application(settings)
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
