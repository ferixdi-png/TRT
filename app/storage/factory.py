"""
Storage factory - выбор storage (GitHub with test fallback).
В продакшене используется GitHub Contents API, в тестах возможен JSON fallback.
"""

import logging
import os
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.github_storage import GitHubStorage

logger = logging.getLogger(__name__)

# Глобальный экземпляр storage (singleton)
_storage_instance: Optional[BaseStorage] = None
_storage_mode_logged = False


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
    global _storage_mode_logged
    
    if _storage_instance is not None:
        return _storage_instance
    
    # Определяем режим
    if storage_mode is None:
        storage_mode = os.getenv('STORAGE_MODE', '').lower()
    storage_mode = storage_mode.lower()

    github_only = os.getenv("GITHUB_ONLY_STORAGE", "true").lower() in ("1", "true", "yes")
    if not github_only:
        logger.warning("[STORAGE] enforcing_github_only=true reason=GITHUB_ONLY_STORAGE_default")

    test_mode = os.getenv("TEST_MODE", "0") == "1"
    dry_run = os.getenv("DRY_RUN", "0") == "1"

    if storage_mode in {"json", "local", "file"}:
        storage_path = data_dir or os.getenv("STORAGE_DATA_DIR", "./data")
        logger.warning(
            "[STORAGE] mode_override=true requested=%s using=github reason=github_only path=%s",
            storage_mode,
            storage_path,
        )

    if storage_mode not in {"", "github", "github_json"}:
        logger.warning(
            "[STORAGE] mode_override=true requested=%s using=github reason=github_only",
            storage_mode,
        )

    if not _storage_mode_logged:
        logger.info("STORAGE_MODE=GITHUB_JSON (DB_DISABLED=true)")
        _storage_mode_logged = True

    try:
        _storage_instance = GitHubStorage()
    except ValueError:
        if test_mode or dry_run:
            logger.error("[STORAGE] github_init_failed mode=github_json env_missing=true")
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
