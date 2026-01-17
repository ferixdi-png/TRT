"""Balance guarantee retry loop stub."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def start_periodic_retry_loop() -> None:
    while True:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("[BALANCE_GUARANTEE] Loop error: %s", exc)
