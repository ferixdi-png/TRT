"""Telemetry helper stubs."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TelemetryMiddleware:
    async def __call__(self, handler, event, data):
        return await handler(event, data)


def log_callback_received(cid, callback_id, user_id, chat_id, data, bot_state=None):
    logger.info("[TELEMETRY] callback_received cid=%s callback_id=%s user_id=%s chat_id=%s data=%s bot_state=%s", cid, callback_id, user_id, chat_id, data, bot_state)


def log_callback_routed(cid, user_id, chat_id, handler, data, button_id=None):
    logger.info("[TELEMETRY] callback_routed cid=%s user_id=%s chat_id=%s handler=%s data=%s button_id=%s", cid, user_id, chat_id, handler, data, button_id)


def log_callback_accepted(cid, user_id, chat_id, data, button_id=None):
    logger.info("[TELEMETRY] callback_accepted cid=%s user_id=%s chat_id=%s data=%s button_id=%s", cid, user_id, chat_id, data, button_id)


def log_callback_rejected(cid, user_id, chat_id, data, reason):
    logger.info("[TELEMETRY] callback_rejected cid=%s user_id=%s chat_id=%s data=%s reason=%s", cid, user_id, chat_id, data, reason)


def log_ui_render(cid, user_id, chat_id, screen_id):
    logger.info("[TELEMETRY] ui_render cid=%s user_id=%s chat_id=%s screen=%s", cid, user_id, chat_id, screen_id)
