"""
Render singleton lock (disabled).
Legacy module retained for imports only.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_DISABLED_MESSAGE = "DB_DISABLED: github-only mode"


def make_lock_key(_token: str, _namespace: str = "telegram_polling") -> int:
    logger.info("%s action=make_lock_key", DB_DISABLED_MESSAGE)
    return 0


def acquire_lock_session(_pool, _lock_key: int) -> Optional[object]:
    logger.info("%s action=acquire_lock_session", DB_DISABLED_MESSAGE)
    return None


def release_lock_session(_pool, _conn, _lock_key: int) -> None:
    logger.info("%s action=release_lock_session", DB_DISABLED_MESSAGE)
