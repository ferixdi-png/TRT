"""Runtime state shared across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import uuid


@dataclass
class RuntimeState:
    bot_mode: str = "unknown"
    storage_mode: str = "unknown"
    lock_acquired: bool = False
    instance_id: str = field(default_factory=lambda: os.getenv("BOT_INSTANCE_ID", str(uuid.uuid4())))
    last_start_time: str | None = None
    db_schema_ready: bool = False
    fsm_cleanup_last_run: str | None = None
    stale_job_cleanup_last_run: str | None = None
    stuck_payment_cleanup_last_run: str | None = None
    callback_job_not_found_count: int = 0
    db_pool: object | None = None
    last_error: str | None = None


runtime_state = RuntimeState()
