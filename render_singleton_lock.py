"""
PostgreSQL Advisory Lock для предотвращения 409 Conflict на Render.
Использует pg_advisory_lock для гарантии что только один инстанс бота запущен.
"""

import os
import logging
import hashlib
from typing import Optional
import psycopg2
from psycopg2.extensions import connection

logger = logging.getLogger(__name__)


def make_lock_key(token: str, namespace: str = "telegram_polling") -> int:
    """
    Создает стабильный bigint ключ из токена и namespace.
    
    Args:
        token: TELEGRAM_BOT_TOKEN
        namespace: Имя namespace для lock (default: "telegram_polling")
    
    Returns:
        int64 ключ для pg_advisory_lock
    """
    # Комбинируем namespace и token для уникальности
    combined = f"{namespace}:{token}".encode('utf-8')
    
    # Используем SHA256 и берем первые 8 байт (64 бита) для bigint
    hash_bytes = hashlib.sha256(combined).digest()[:8]
    
    # Конвертируем в signed int64 (PostgreSQL bigint)
    lock_key = int.from_bytes(hash_bytes, byteorder='big', signed=True)
    
    # Маскируем токен для логов
    masked_token = token[:4] + "..." + token[-4:] if len(token) > 8 else "****"
    logger.debug(f"Lock key generated: namespace={namespace}, token={masked_token}, key={lock_key}")
    
    return lock_key


def acquire_lock_session(pool, lock_key: int) -> Optional[connection]:
    """
    Пытается получить PostgreSQL advisory lock.
    
    Args:
        pool: psycopg2.pool.SimpleConnectionPool
        lock_key: int64 ключ для lock
    
    Returns:
        connection если lock получен, None если другой инстанс уже держит lock
        ВАЖНО: соединение НЕ должно возвращаться в пул пока lock активен!
    """
    try:
        # Получаем соединение из пула
        conn = pool.getconn()
        
        # Пытаемся получить advisory lock (неблокирующий)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            lock_acquired = cur.fetchone()[0]
        
        if lock_acquired:
            logger.info(f"✅ PostgreSQL advisory lock acquired: key={lock_key}")
            # ВАЖНО: НЕ возвращаем соединение в пул!
            return conn
        else:
            # Lock уже занят другим инстансом
            logger.warning(f"⚠️ PostgreSQL advisory lock already held: key={lock_key}")
            # Возвращаем соединение в пул
            pool.putconn(conn)
            return None
            
    except Exception as e:
        logger.error(f"❌ Error acquiring advisory lock: {e}", exc_info=True)
        # Если была ошибка и соединение получено - возвращаем в пул
        if 'conn' in locals():
            try:
                pool.putconn(conn)
            except:
                pass
        return None


def release_lock_session(pool, conn: connection, lock_key: int) -> None:
    """
    Освобождает PostgreSQL advisory lock и возвращает соединение в пул.
    
    Args:
        pool: psycopg2.pool.SimpleConnectionPool
        conn: Соединение с активным lock
        lock_key: int64 ключ lock
    """
    try:
        if conn and not conn.closed:
            # Освобождаем advisory lock
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
                unlocked = cur.fetchone()[0]
            
            if unlocked:
                logger.info(f"✅ PostgreSQL advisory lock released: key={lock_key}")
            else:
                logger.warning(f"⚠️ Lock was not held (already released?): key={lock_key}")
            
            # Возвращаем соединение в пул
            pool.putconn(conn)
        else:
            logger.warning(f"⚠️ Connection already closed, cannot release lock: key={lock_key}")
    except Exception as e:
        logger.error(f"❌ Error releasing advisory lock: {e}", exc_info=True)
        # Пытаемся вернуть соединение в пул даже при ошибке
        if conn and not conn.closed:
            try:
                pool.putconn(conn)
            except:
                pass
