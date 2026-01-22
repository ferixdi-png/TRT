"""Exception middleware for aiogram."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ExceptionMiddleware:
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except Exception as exc:
            logger.exception("[EXCEPTION_MW] Unhandled exception: %s", exc)
            raise
