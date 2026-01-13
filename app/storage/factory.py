"""
Storage factory - автоматический выбор storage (JSON или PostgreSQL)
AUTO режим: если DATABASE_URL доступен и коннектится -> pg, иначе json
"""

import logging
import os
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.json_storage import JsonStorage
from app.storage.pg_storage import PostgresStorage

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
        storage_mode: 'postgres', 'json', или 'auto' (default)
        database_url: URL базы данных (если None, берется из env)
        data_dir: Директория для JSON (если None, берется из env или './data')
    
    Returns:
        BaseStorage instance
    """
    global _storage_instance
    
    if _storage_instance is not None:
        return _storage_instance
    
    # Определяем режим
    if storage_mode is None:
        storage_mode = os.getenv('STORAGE_MODE', 'auto').lower()
    
    # AUTO режим: пробуем PostgreSQL, если не получается - JSON
    if storage_mode == 'auto':
        database_url = database_url or os.getenv('DATABASE_URL')
        
        if database_url:
            try:
                # Пробуем создать PostgreSQL storage
                pg_storage = PostgresStorage(database_url)
                # CRITICAL: Never call sync test_connection() - always use async version
                # Pool initialization will happen on first actual query
                logger.info("[OK] PostgreSQL storage initialized (pool will initialize on first query)")
                _storage_instance = pg_storage
                return _storage_instance
            except Exception as e:
                logger.warning(f"[WARN] PostgreSQL initialization failed: {e}, falling back to JSON")
        
        # Fallback на JSON
        data_dir = data_dir or os.getenv('DATA_DIR', './data')
        logger.info(f"[OK] Using JSON storage (AUTO mode, data_dir={data_dir})")
        _storage_instance = JsonStorage(data_dir)
        return _storage_instance
    
    # Явный режим
    if storage_mode == 'postgres':
        database_url = database_url or os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL storage")
        _storage_instance = PostgresStorage(database_url)
        logger.info("[OK] Using PostgreSQL storage (explicit mode)")
        return _storage_instance
    
    elif storage_mode == 'json':
        data_dir = data_dir or os.getenv('DATA_DIR', './data')
        _storage_instance = JsonStorage(data_dir)
        logger.info(f"[OK] Using JSON storage (explicit mode, data_dir={data_dir})")
        return _storage_instance
    
    else:
        raise ValueError(f"Invalid storage_mode: {storage_mode}. Use 'postgres', 'json', or 'auto'")


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


