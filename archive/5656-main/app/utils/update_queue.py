"""Minimal update queue manager."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QueueManager:
    max_size: int = 100
    num_workers: int = 2
    _dp: object | None = None
    _bot: object | None = None
    _active_state: object | None = None
    _total_received: int = 0
    _total_processed: int = 0
    _total_dropped: int = 0

    def configure(self, dp, bot, active_state) -> None:
        self._dp = dp
        self._bot = bot
        self._active_state = active_state

    def get_metrics(self) -> dict:
        return {
            "queue_depth_current": 0,
            "queue_max": self.max_size,
            "total_received": self._total_received,
            "total_processed": self._total_processed,
            "total_dropped": self._total_dropped,
        }


_queue_manager = QueueManager()


def get_queue_manager() -> QueueManager:
    return _queue_manager
