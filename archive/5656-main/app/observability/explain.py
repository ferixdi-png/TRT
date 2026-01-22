"""Deployment topology logging."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_deploy_topology(
    *,
    instance_id: str,
    pid: int,
    boot_time: str,
    commit_sha: str,
    is_active: bool,
    lock_key: int | None,
    lock_holder_pid: int | None,
    render_service_name: str | None,
) -> None:
    logger.info(
        "[DEPLOY_TOPOLOGY] instance_id=%s pid=%s boot_time=%s commit_sha=%s active=%s lock_key=%s lock_holder_pid=%s service=%s",
        instance_id,
        pid,
        boot_time,
        commit_sha,
        is_active,
        lock_key,
        lock_holder_pid,
        render_service_name,
    )
