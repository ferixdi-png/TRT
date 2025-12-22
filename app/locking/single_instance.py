"""
Single instance lock - предотвращение 409 Conflict через единый механизм блокировки

Алгоритм:
- Если есть DATABASE_URL: использует PostgreSQL advisory lock через удержание соединения (session-level)
- Если DATABASE_URL нет: file lock в DATA_DIR (или /tmp как fallback)

ВАЖНО: Соединение держится открытым весь runtime для сохранения session-level lock.
"""

import os
import sys
import logging
import hashlib
from pathlib import Path
from typing import Optional, Literal

from app.utils.logging_config import get_logger
from app.config import get_settings

logger = get_logger(__name__)

# Глобальное состояние lock
_lock_handle: Optional[object] = None
_lock_type: Optional[Literal['postgres', 'file']] = None
_lock_connection: Optional[object] = None  # PostgreSQL connection (для session-level lock)


def _get_lock_key() -> int:
    """Получить ключ для advisory lock (на основе BOT_TOKEN)"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    # Используем render_singleton_lock логику для совместимости
    namespace = "telegram_polling"
    combined = f"{namespace}:{bot_token}".encode('utf-8')
    
    # Используем SHA256 и берем первые 8 байт (64 бита) для bigint
    hash_bytes = hashlib.sha256(combined).digest()[:8]
    
    # Конвертируем в unsigned int64, затем приводим к signed bigint
    unsigned_key = int.from_bytes(hash_bytes, byteorder='big', signed=False)
    
    # Приводим к signed bigint
    MAX_BIGINT = 9223372036854775807
    lock_key = unsigned_key % (MAX_BIGINT + 1)
    
    return lock_key


def _acquire_postgres_lock() -> Optional[object]:
    """
    Пытается получить PostgreSQL advisory lock через session-level connection.
    
    Returns:
        dict с 'connection' и 'lock_key' если lock получен, None если нет
    """
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return None
        
        # Пытаемся получить connection pool из database.py (psycopg2)
        try:
            from database import get_connection_pool
            pool = get_connection_pool()
        except Exception as e:
            logger.debug(f"[LOCK] Cannot get connection pool from database.py: {e}")
            return None
        
        if pool is None:
            return None
        
        # Используем render_singleton_lock для получения lock
        try:
            import render_singleton_lock
            lock_key = _get_lock_key()
            conn = render_singleton_lock.acquire_lock_session(pool, lock_key)
            
            if conn:
                logger.info(f"[LOCK] PostgreSQL advisory lock acquired (key={lock_key})")
                return {'connection': conn, 'pool': pool, 'lock_key': lock_key}
            else:
                logger.warning(f"[LOCK] PostgreSQL advisory lock NOT acquired (key={lock_key}) - another instance is running")
                return None
        except ImportError:
            logger.debug("[LOCK] render_singleton_lock not available")
            return None
        except Exception as e:
            logger.warning(f"[LOCK] Failed to acquire PostgreSQL lock: {e}")
            return None
    
    except Exception as e:
        logger.debug(f"[LOCK] PostgreSQL lock acquisition failed: {e}")
        return None


def _acquire_file_lock() -> Optional[object]:
    """
    Пытается получить file lock.
    
    Returns:
        FileLock object если lock получен, None если нет
    """
    try:
        from filelock import FileLock, Timeout
        
        # Определяем путь к lock файлу
        settings = get_settings()
        data_dir = Path(settings.data_dir) if settings.data_dir else Path('/tmp')
        
        # Создаем директорию если не существует
        data_dir.mkdir(parents=True, exist_ok=True)
        lock_file = data_dir / 'bot_single_instance.lock'
        
        # Пробуем получить lock (non-blocking)
        lock = FileLock(lock_file, timeout=0.1)
        
        try:
            lock.acquire(timeout=0.1)
            logger.info(f"[LOCK] File lock acquired: {lock_file}")
            return lock
        except Timeout:
            logger.warning(f"[LOCK] File lock NOT acquired: {lock_file} - another instance is running")
            return None
    
    except ImportError:
        logger.debug("[LOCK] filelock not available, skipping file lock")
        return None
    except Exception as e:
        logger.warning(f"[LOCK] Failed to acquire file lock: {e}")
        return None


def acquire_single_instance_lock() -> bool:
    """
    Попытаться получить single instance lock (PostgreSQL или filelock).
    
    КРИТИЧНО: Если DATABASE_URL установлен, PostgreSQL lock ОБЯЗАТЕЛЕН.
    Если PostgreSQL lock не получен (другой инстанс его держит), процесс должен завершиться,
    даже если file lock получен. Это предотвращает одновременную работу двух инстансов.
    
    Returns:
        True если lock получен, False если нет
        
    Side effect:
        Сохраняет lock handle в глобальной переменной для последующего освобождения
    """
    global _lock_handle, _lock_type, _lock_connection
    
    database_url = os.getenv('DATABASE_URL')
    
    # Пробуем PostgreSQL advisory lock сначала
    lock_data = _acquire_postgres_lock()
    if lock_data:
        _lock_handle = lock_data
        _lock_connection = lock_data['connection']
        _lock_type = 'postgres'
        return True
    
    # КРИТИЧНО: Если DATABASE_URL установлен, но PostgreSQL lock не получен - это конфликт!
    # Другой инстанс уже держит PostgreSQL lock, и мы НЕ должны запускаться с file lock.
    if database_url:
        logger.error("=" * 60)
        logger.error("[LOCK] CRITICAL: DATABASE_URL is set, but PostgreSQL lock NOT acquired")
        logger.error("[LOCK] Another bot instance is already running with PostgreSQL lock")
        logger.error("[LOCK] This instance will exit to prevent 409 Conflict")
        logger.error("[LOCK] Exiting gracefully (exit code 0) to prevent restart loop")
        logger.error("=" * 60)
        return False
    
    # Fallback на filelock ТОЛЬКО если DATABASE_URL не установлен
    lock_handle = _acquire_file_lock()
    if lock_handle:
        _lock_handle = lock_handle
        _lock_connection = None
        _lock_type = 'file'
        return True
    
    # Lock не получен - другой экземпляр запущен
    logger.error("=" * 60)
    logger.error("[LOCK] FAILED: Another bot instance is already running")
    logger.error("[LOCK] Exiting gracefully (exit code 0) to prevent restart loop")
    logger.error("=" * 60)
    return False


def release_single_instance_lock():
    """Освободить single instance lock"""
    global _lock_handle, _lock_type, _lock_connection
    
    if _lock_handle is None:
        return
    
    try:
        if _lock_type == 'postgres':
            # Освобождаем PostgreSQL advisory lock
            lock_data = _lock_handle
            if isinstance(lock_data, dict):
                conn = lock_data.get('connection')
                pool = lock_data.get('pool')
                lock_key = lock_data.get('lock_key')
                
                if conn and pool and lock_key is not None:
                    try:
                        import render_singleton_lock
                        render_singleton_lock.release_lock_session(pool, conn, lock_key)
                        logger.info("[LOCK] PostgreSQL advisory lock released")
                    except Exception as e:
                        logger.warning(f"[LOCK] Failed to release PostgreSQL lock: {e}")
        
        elif _lock_type == 'file':
            # Освобождаем filelock
            _lock_handle.release()
            logger.info("[LOCK] File lock released")
    
    except Exception as e:
        logger.warning(f"[LOCK] Failed to release lock: {e}")
    finally:
        _lock_handle = None
        _lock_connection = None
        _lock_type = None


def is_lock_held() -> bool:
    """Проверить, удерживается ли lock"""
    return _lock_handle is not None and _lock_type is not None

