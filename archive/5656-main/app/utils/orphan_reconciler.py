"""Orphan callback reconciliation stub."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class OrphanCallbackReconciler:
    def __init__(self, storage, bot, check_interval: int = 10, max_age_minutes: int = 30):
        self.storage = storage
        self.bot = bot
        self.check_interval = check_interval
        self.max_age_minutes = max_age_minutes
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[RECONCILER] Loop error: %s", exc)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
