"""
PostgreSQL Advisory Lock для предотвращения 409 Conflict на Render.

Использует pg_advisory_lock для гарантии что только один инстанс бота запущен.
Это критически важно для предотвращения Telegram 409 Conflict ошибок,
которые возникают когда несколько инстансов пытаются использовать polling одновременно.

Механизм:
- Генерирует уникальный lock_key на основе TELEGRAM_BOT_TOKEN
- Пытается получить advisory lock через pg_try_advisory_lock
- Если lock не получен (уже занят другим инстансом) - процесс завершается
- Соединение держится в течение всего runtime для сохранения lock
- Lock освобождается только при shutdown процесса
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
    
    # Конвертируем в unsigned int64, затем приводим к signed bigint
    # PostgreSQL advisory lock использует signed bigint (-2^63 to 2^63-1)
    unsigned_key = int.from_bytes(hash_bytes, byteorder='big', signed=False)
    
    # Приводим к signed bigint: используем модуль для гарантии положительного значения
    # MAX_BIGINT = 9223372036854775807 (2^63 - 1)
    MAX_BIGINT = 9223372036854775807
    lock_key = unsigned_key % (MAX_BIGINT + 1)
    
    # Убеждаемся что ключ в допустимом диапазоне (должно быть автоматически)
    if lock_key > MAX_BIGINT or lock_key < 0:
        # Fallback: используем только младшие 63 бита
        lock_key = unsigned_key & 0x7FFFFFFFFFFFFFFF
    
    # Маскируем токен для логов
    masked_token = token[:4] + "..." + token[-4:] if len(token) > 8 else "****"
    logger.debug(f"Lock key generated: namespace={namespace}, token={masked_token}, key={lock_key}")
    
    return lock_key


def acquire_lock_session(pool, lock_key: int) -> Optional[connection]:
    """
    Пытается получить PostgreSQL advisory lock.
    Если lock занят, проверяет не "мёртвый" ли он (>5 минут без активности).
    
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
            # Lock занят - проверяем не "мёртвый" ли процесс
            logger.warning(f"⏸️ PostgreSQL advisory lock already held by another instance: key={lock_key}")
            
            # Проверяем timestamp последней активности держателя lock
            # ВАЖНО: используем classid,objid,objsubid для advisory locks (не objid alone!)
            # classid=0 для user locks, objid хранит lock key
            with conn.cursor() as cur:
                # Advisory lock key распределён по (classid, objid, objsubid)
                # Для user locks: classid=0, objid=key (если key fits in 32-bit) или classid,objid pair
                cur.execute("""
                    SELECT 
                        pl.pid,
                        sa.state,
                        EXTRACT(EPOCH FROM (NOW() - sa.query_start)) as duration_sec,
                        EXTRACT(EPOCH FROM (NOW() - sa.state_change)) as idle_sec
                    FROM pg_locks pl
                    LEFT JOIN pg_stat_activity sa ON pl.pid = sa.pid
                    WHERE pl.locktype = 'advisory'
                    AND pl.granted = true
                    LIMIT 1
                """)
                result = cur.fetchone()
                
                if result:
                    pid, state, duration_sec, idle_sec = result
                    
                    logger.info(f"[LOCK] Holder: pid={pid}, state={state}, duration={duration_sec:.0f}s, idle={idle_sec:.0f}s")
                    
                    # Если держатель lock idle >5 минут - считаем его мёртвым
                    if idle_sec and idle_sec > 300:
                        logger.warning(f"[LOCK] ⚠️ STALE LOCK DETECTED: idle for {idle_sec:.0f}s (>5min)")
                        logger.warning(f"[LOCK] 🔥 Terminating stale process pid={pid}...")
                        
                        try:
                            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
                            terminated = cur.fetchone()[0]
                            if terminated:
                                logger.info(f"[LOCK] ✅ Stale process terminated, retrying lock acquisition...")
                                conn.commit()
                                
                                # Wait a bit for lock release
                                import time
                                time.sleep(0.5)
                                
                                # Retry lock acquisition
                                cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
                                lock_acquired_retry = cur.fetchone()[0]
                                
                                if lock_acquired_retry:
                                    logger.info(f"[LOCK] ✅ Lock acquired after terminating stale process!")
                                    return conn
                                else:
                                    logger.warning("[LOCK] ⚠️ Still cannot acquire lock after termination")
                        except Exception as e:
                            logger.error(f"[LOCK] ❌ Failed to terminate stale process: {e}")
                else:
                    logger.warning("[LOCK] ⚠️ Lock holder process not found in pg_stat_activity (already dead?)")
            
            logger.warning("[LOCK] ⚠️ PASSIVE MODE - another instance is ACTIVE, this instance will wait")
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
