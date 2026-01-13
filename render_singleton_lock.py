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


def split_bigint_to_pg_advisory_oids(lock_key: int) -> tuple[int, int]:
    """
    Разбивает 64-битный lock_key на пару 32-битных OID для pg_advisory_lock.
    
    PostgreSQL advisory locks используют пару (classid, objid), каждая из которых
    является 32-битным unsigned integer (OID type, 0..4294967295).
    
    Args:
        lock_key: 64-битный ключ (0 <= lock_key <= 2^63-1)
    
    Returns:
        tuple[int, int]: (hi, lo) где каждый 0 <= value <= 4294967295
    
    Example:
        >>> split_bigint_to_pg_advisory_oids(2797505866569588743)
        (651107867, 2242801671)
    """
    # Разбиваем на старшие и младшие 32 бита (unsigned)
    hi = (lock_key >> 32) & 0xFFFFFFFF  # Старшие 32 бита
    lo = lock_key & 0xFFFFFFFF          # Младшие 32 бита
    return hi, lo


def make_lock_key(token: str, namespace: str = "telegram_polling") -> int:
    """
    Создает стабильный bigint ключ из токена и namespace.
    ГАРАНТИЯ: результат ВСЕГДА в диапазоне signed int64 [0, 2^63-1]
    
    Args:
        token: TELEGRAM_BOT_TOKEN
        namespace: Имя namespace для lock (default: "telegram_polling")
    
    Returns:
        int64 ключ для pg_advisory_lock (0 <= key <= 9223372036854775807)
    """
    # Комбинируем namespace и token для уникальности
    combined = f"{namespace}:{token}".encode('utf-8')
    
    # Используем SHA256 и берем первые 8 байт (64 бита)
    hash_bytes = hashlib.sha256(combined).digest()[:8]
    
    # Конвертируем в unsigned int64
    unsigned_key = int.from_bytes(hash_bytes, byteorder='big', signed=False)
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Приводим к signed int64 через битовую маску
    # Берем только младшие 63 бита (старший бит сбрасываем для знака)
    # Результат: 0 <= lock_key <= 0x7FFFFFFFFFFFFFFF (9223372036854775807)
    MAX_BIGINT = 0x7FFFFFFFFFFFFFFF  # 2^63 - 1 = 9223372036854775807
    lock_key = unsigned_key & MAX_BIGINT
    
    # Маскируем токен для логов
    masked_token = token[:4] + "..." + token[-4:] if len(token) > 8 else "****"
    logger.debug(f"Lock key generated: namespace={namespace}, token={masked_token}, key={lock_key}")
    
    return lock_key


def acquire_lock_session(pool, lock_key: int) -> Optional[connection]:
    """
    Пытается получить PostgreSQL advisory lock.
    Если lock занят, проверяет не "мёртвый" ли он (>5 минут без активности).
    
    КРИТИЧНО: Соединение должно быть в autocommit режиме чтобы избежать
    "idle in transaction" состояния при удержании lock.
    
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
        
        # КРИТИЧНО: Устанавливаем autocommit чтобы избежать "idle in transaction"
        # Advisory lock держится на уровне сессии, не транзакции
        conn.autocommit = True
        logger.debug(f"[LOCK] Connection autocommit enabled to prevent 'idle in transaction'")
        
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
            # КРИТИЧНО: Для 64-битных advisory locks PostgreSQL использует пару (classid, objid)
            # где каждая часть - 32-битный OID (0..2^32-1)
            hi, lo = split_bigint_to_pg_advisory_oids(lock_key)
            
            try:
                with conn.cursor() as cur:
                    # Находим holder нашего конкретного lock по classid/objid паре
                    cur.execute("""
                        SELECT 
                            pl.pid,
                            sa.state,
                            EXTRACT(EPOCH FROM (NOW() - sa.query_start)) as duration_sec,
                            EXTRACT(EPOCH FROM (NOW() - sa.state_change)) as idle_sec
                        FROM pg_locks pl
                        LEFT JOIN pg_stat_activity sa ON pl.pid = sa.pid
                        WHERE pl.locktype = 'advisory'
                        AND pl.database = (SELECT oid FROM pg_database WHERE datname = current_database())
                        AND pl.classid = %s
                        AND pl.objid = %s
                        AND pl.granted = true
                        LIMIT 1
                    """, (hi, lo))
                    result = cur.fetchone()
            except Exception as e:
                # FAIL-SAFE: Ошибка диагностики НЕ должна ломать acquire цикл
                logger.warning(f"[LOCK] ⚠️ Cannot check lock holder (key={lock_key}): {e}")
                pool.putconn(conn)
                return None
                
                if result:
                    pid, state, duration_sec, idle_sec = result
                    
                    logger.info(f"[LOCK] Holder: pid={pid}, state={state}, duration={duration_sec:.0f}s, idle={idle_sec:.0f}s")
                    
                    # КРИТИЧНО: "idle in transaction" убиваем через 30 секунд (открытая транзакция блокирует БД)
                    # Обычный "idle" убиваем через 5 минут
                    stale_threshold = 30 if state == "idle in transaction" else 300
                    
                    # Если держатель lock превысил порог - считаем его мёртвым
                    if idle_sec and idle_sec > stale_threshold:
                        threshold_label = f"{stale_threshold}s ({state})"
                        logger.warning(f"[LOCK] ⚠️ STALE LOCK DETECTED: idle for {idle_sec:.0f}s (>{threshold_label})")
                        logger.warning(f"[LOCK] 🔥 Terminating stale process pid={pid}...")
                        
                        try:
                            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
                            terminated = cur.fetchone()[0]
                            if terminated:
                                logger.info(f"[LOCK] ✅ Stale process terminated, retrying lock acquisition...")
                                # No need for conn.commit() - autocommit is enabled
                                
                                # Wait for lock release - measured ~500-2000ms in production logs
                                # Using 3s to GUARANTEE lock is fully released (critical for webhook setup)
                                import time
                                time.sleep(3.0)
                                
                                # Retry lock acquisition
                                cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
                                lock_acquired_retry = cur.fetchone()[0]
                                
                                if lock_acquired_retry:
                                    logger.info(f"[LOCK] ✅ Lock acquired after terminating stale process!")
                                    return conn
                                else:
                                    logger.warning("[LOCK] ⚠️ Still cannot acquire lock after termination")
                        except Exception as term_err:
                            logger.warning(f"[LOCK] ⚠️ Cannot terminate stale process (pid={pid}): {term_err}")
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
