"""Deploy awareness markers."""
from __future__ import annotations

import time

_deploy_started_at: float | None = None


async def mark_deploy_start() -> None:
    global _deploy_started_at
    _deploy_started_at = time.time()


def is_deploy_in_progress() -> bool:
    if _deploy_started_at is None:
        return False
    return (time.time() - _deploy_started_at) < 300


def get_deploy_status_text() -> str:
    return "deploying" if is_deploy_in_progress() else "ready"
