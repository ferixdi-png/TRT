"""
Storage factory - выбор storage (GitHub with test fallback).
В продакшене используется GitHub Contents API, в тестах возможен JSON fallback.
"""

import logging
import os
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.github_storage import GitHubStorage
from app.storage.json_storage import JsonStorage

logger = logging.getLogger(__name__)

# Глобальный экземпляр storage (singleton)
_storage_instance: Optional[BaseStorage] = None


def create_storage(
    storage_mode: Optional[str] = None,
    database_url: Optional[str] = None,
    data_dir: Optional[str] = None
) -> BaseStorage:
    """
    Создает storage instance
    
    Args:
        storage_mode: 'github' (default) или 'auto' (для github)
        database_url: игнорируется (БД отключены)
        data_dir: игнорируется (БД отключены)
    
    Returns:
        BaseStorage instance
    """
    global _storage_instance
    
    if _storage_instance is not None:
        return _storage_instance
    
    # Определяем режим
    if storage_mode is None:
        storage_mode = os.getenv('STORAGE_MODE', 'auto').lower()
    storage_mode = storage_mode.lower()

    test_mode = os.getenv("TEST_MODE", "0") == "1"
    dry_run = os.getenv("DRY_RUN", "0") == "1"

    if storage_mode in {"json", "local", "file"}:
        storage_path = data_dir or os.getenv("STORAGE_DATA_DIR", "./data")
        logger.warning("[STORAGE] mode_override=true requested=%s using=json path=%s", storage_mode, storage_path)
        _storage_instance = JsonStorage(storage_path)
        return _storage_instance

    if storage_mode != "github":
        logger.warning(
            "[STORAGE] mode_override=true requested=%s using=github reason=db_disabled",
            storage_mode,
        )

    try:
        _storage_instance = GitHubStorage()
    except ValueError as exc:
        if test_mode or dry_run:
            storage_path = data_dir or os.getenv("STORAGE_DATA_DIR", "./data")
            logger.warning(
                "[STORAGE] github_init_failed fallback=json reason=%s path=%s",
                exc,
                storage_path,
            )
            _storage_instance = JsonStorage(storage_path)
        else:
            raise
    return _storage_instance


def get_storage() -> BaseStorage:
    """
    Получить текущий storage instance (singleton)
    
    Returns:
        BaseStorage instance
    """
    global _storage_instance
    
    if _storage_instance is None:
        _storage_instance = create_storage()
    
    return _storage_instance


def reset_storage() -> None:
    """Сбросить storage instance (для тестов)"""
    global _storage_instance
    _storage_instance = None
