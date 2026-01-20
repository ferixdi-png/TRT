"""
PostgreSQL storage (disabled).
Retained for legacy imports only.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_DISABLED_MESSAGE = "DB_DISABLED: github-only mode"


def async_check_pg(*_args, **_kwargs) -> bool:
    logger.info("%s action=async_check_pg", DB_DISABLED_MESSAGE)
    return False


def sync_check_pg(*_args, **_kwargs) -> bool:
    logger.info("%s action=sync_check_pg", DB_DISABLED_MESSAGE)
    return False


class PGStorage:
    """Disabled PostgreSQL storage backend."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn

    async def initialize(self) -> bool:
        logger.info("%s action=initialize", DB_DISABLED_MESSAGE)
        return False

    async def close(self) -> None:
        logger.info("%s action=close", DB_DISABLED_MESSAGE)

    def test_connection(self) -> bool:
        logger.info("%s action=test_connection", DB_DISABLED_MESSAGE)
        return False


PostgresStorage = PGStorage

__all__ = ["PGStorage", "PostgresStorage", "async_check_pg", "sync_check_pg"]
