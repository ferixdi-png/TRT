"""Job service stub."""
from __future__ import annotations


class JobServiceV2:
    def __init__(self, _pool):
        self._pool = _pool

    async def cleanup_stale_jobs(self, stale_minutes: int = 30) -> int:
        return 0
