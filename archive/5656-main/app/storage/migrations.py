"""Database migration stubs."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def apply_migrations_safe(*_args, **_kwargs) -> bool:
    logger.info("[MIGRATIONS] Skipped (no database configured)")
    return True
