"""Anti-abuse middleware stub."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AntiAbuseMiddleware:
    async def __call__(self, handler, event, data):
        return await handler(event, data)
