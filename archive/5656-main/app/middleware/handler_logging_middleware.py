"""Handler logging middleware."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class HandlerLoggingMiddleware:
    async def __call__(self, handler, event, data):
        logger.debug("[HANDLER_LOGGING] event=%s", type(event).__name__)
        return await handler(event, data)
