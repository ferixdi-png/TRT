"""Structured logging helpers."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_operation(operation: str, status: str, **kwargs) -> None:
    payload = {"operation": operation, "status": status, **kwargs}
    logger.info("[OPERATION] %s", payload)
