"""Telegram protection middleware stub."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TelegramProtectionMiddleware:
    async def __call__(self, handler, event, data):
        return await handler(event, data)
