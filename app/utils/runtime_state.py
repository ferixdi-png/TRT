"""
Runtime state shared across handlers for diagnostics.
"""
from dataclasses import dataclass
import os
import socket
import uuid


@dataclass
class RuntimeState:
    instance_id: str
    lock_acquired: bool | None = None
    storage_mode: str = "auto"
    bot_mode: str = "polling"
    last_start_time: str | None = None
    db_schema_ready: bool = False  # CRITICAL: tracks if migrations applied
    callback_job_not_found_count: int = 0  # Metric: orphan callbacks
    telegram_send_fail_count: int = 0  # Metric: delivery failures


def _build_instance_id() -> str:
    host = socket.gethostname()
    suffix = uuid.uuid4().hex[:8]
    return f"{host}-{suffix}"


runtime_state = RuntimeState(
    instance_id=_build_instance_id(),
    storage_mode=os.getenv("STORAGE_MODE", "auto"),
    bot_mode=os.getenv("BOT_MODE", "polling"),
)
