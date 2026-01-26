"""Fault injection helpers for deterministic slowdown tests."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _is_fault_injection_enabled() -> bool:
    return os.getenv("TEST_MODE", "").strip() in {"1", "true", "yes"} or os.getenv("DRY_RUN", "").strip() in {
        "1",
        "true",
        "yes",
    }


def _get_sleep_ms(env_var: str) -> Optional[int]:
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning("FAULT_INJECT_PARSE_FAILED env=%s value=%s", env_var, raw)
        return None
    if value <= 0:
        return None
    return value


async def maybe_inject_sleep(env_var: str, *, label: str) -> None:
    if not _is_fault_injection_enabled():
        return
    sleep_ms = _get_sleep_ms(env_var)
    if sleep_ms is None:
        return
    logger.info("FAULT_INJECT_SLEEP label=%s env=%s sleep_ms=%s", label, env_var, sleep_ms)
    await asyncio.sleep(sleep_ms / 1000)
