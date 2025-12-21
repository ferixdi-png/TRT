"""
DEPRECATED: Этот модуль существует только для обратной совместимости.
Используйте app.locking.single_instance вместо этого.

Thin wrapper вокруг app.locking.single_instance для обратной совместимости.
"""

import sys
from app.locking.single_instance import (
    acquire_single_instance_lock,
    release_single_instance_lock as _release_single_instance_lock,
    is_lock_held,
)
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def acquire_singleton_lock() -> bool:
    """
    DEPRECATED: Используйте app.locking.single_instance.acquire_single_instance_lock()
    
    Попытаться получить singleton lock (PostgreSQL или filelock)
    
    Returns:
        True если lock получен, False если нет
    
    Side effect:
        Если lock не получен, вызывает sys.exit(0) (не бесконечные рестарты)
    """
    if acquire_single_instance_lock():
        return True
    
    # Lock не получен - другой экземпляр запущен
    logger.error("=" * 60)
    logger.error("[LOCK] FAILED: Another bot instance is already running")
    logger.error("[LOCK] Exiting gracefully (exit code 0) to prevent restart loop")
    logger.error("=" * 60)
    sys.exit(0)  # exit(0) чтобы Render не считал это ошибкой


def release_singleton_lock():
    """
    DEPRECATED: Используйте app.locking.single_instance.release_single_instance_lock()
    
    Освободить singleton lock
    """
    _release_single_instance_lock()

