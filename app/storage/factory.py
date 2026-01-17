"""
Storage factory - выбор storage (GitHub).
Единственный источник хранения: GitHub Contents API.
"""

import logging
import os
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.github_storage import GitHubStorage

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
    
    if storage_mode != "github":
        logger.warning(
            "[STORAGE] mode_override=true requested=%s using=github reason=db_disabled",
            storage_mode,
        )

    _storage_instance = GitHubStorage()
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

