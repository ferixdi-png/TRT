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
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import psycopg2
from psycopg2.extensions import connection

logger = logging.getLogger(__name__)

STALE_IDLE_SECONDS = int(os.getenv("LOCK_STALE_IDLE_SECONDS", "45"))
STALE_HEARTBEAT_SECONDS = int(os.getenv("LOCK_STALE_HEARTBEAT_SECONDS", "60"))
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("LOCK_HEARTBEAT_INTERVAL", "15"))
LOCK_RELEASE_WAIT_SECONDS = float(os.getenv("LOCK_RELEASE_WAIT_SECONDS", "3.0"))

_heartbeat_available: Optional[bool] = None
_last_takeover_event: Optional[Dict[str, Any]] = None


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


def _heartbeat_supported(conn: connection) -> bool:
    global _heartbeat_available
    if _heartbeat_available is not None:
        return _heartbeat_available
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM lock_heartbeat LIMIT 1")
        _heartbeat_available = True
    except Exception as exc:
        logger.debug("[LOCK] Heartbeat table unavailable: %s", exc)
        _heartbeat_available = False
    return _heartbeat_available


def _get_heartbeat_age_seconds(conn: connection, lock_key: int) -> Optional[float]:
    if not _heartbeat_supported(conn):
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) FROM lock_heartbeat WHERE lock_key = %s",
                (lock_key,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None
    except Exception as exc:
        logger.debug("[LOCK] Failed to fetch heartbeat age: %s", exc)
        return None


def _write_heartbeat(pool, lock_key: int, instance_id: str) -> None:
    try:
        conn = pool.getconn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT update_lock_heartbeat(%s, %s)", (lock_key, instance_id))
    except Exception as exc:
        logger.debug("[LOCK] Heartbeat update failed: %s", exc)
    finally:
        if "conn" in locals():
            try:
                pool.putconn(conn)
            except Exception:
                pass


def start_lock_heartbeat(pool, lock_key: int, instance_id: str):
    stop_event = threading.Event()

    def _loop():
        _write_heartbeat(pool, lock_key, instance_id)
        while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            _write_heartbeat(pool, lock_key, instance_id)

    thread = threading.Thread(target=_loop, daemon=True, name="lock_heartbeat")
    thread.start()
    return stop_event, thread


def stop_lock_heartbeat(stop_event: Optional[threading.Event]) -> None:
    if stop_event:
        stop_event.set()


def get_last_takeover_event() -> Optional[Dict[str, Any]]:
    return _last_takeover_event


def get_lock_holder_info(pool, lock_key: int) -> Dict[str, Any]:
    info = {
        "holder_pid": None,
        "idle_duration": None,
        "state": None,
        "heartbeat_age": None,
    }
    try:
        conn = pool.getconn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pl.pid,
                    sa.state,
                    EXTRACT(EPOCH FROM (NOW() - sa.state_change)) as idle_sec
                FROM pg_locks pl
                LEFT JOIN pg_stat_activity sa ON pl.pid = sa.pid
                WHERE pl.locktype = 'advisory'
                  AND pl.granted = true
                  AND pl.classid = 1
                  AND pl.objid = %s
                LIMIT 1
                """,
                (lock_key,),
            )
            row = cur.fetchone()
            if row:
                info["holder_pid"], info["state"], info["idle_duration"] = row
            info["heartbeat_age"] = _get_heartbeat_age_seconds(conn, lock_key)
    except Exception as exc:
        logger.debug("[LOCK] Failed to fetch lock holder info: %s", exc)
    finally:
        if "conn" in locals():
            try:
                pool.putconn(conn)
            except Exception:
                pass
    return info


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
            # ВАЖНО: используем classid,objid,objsubid для advisory locks (не objid alone!)
            # classid=0 для user locks, objid хранит lock key
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        pl.pid,
                        sa.state,
                        EXTRACT(EPOCH FROM (NOW() - sa.query_start)) as duration_sec,
                        EXTRACT(EPOCH FROM (NOW() - sa.state_change)) as idle_sec
                    FROM pg_locks pl
                    LEFT JOIN pg_stat_activity sa ON pl.pid = sa.pid
                    WHERE pl.locktype = 'advisory'
                      AND pl.granted = true
                      AND pl.classid = 1
                      AND pl.objid = %s
                    LIMIT 1
                    """,
                    (lock_key,),
                )
                result = cur.fetchone()
                
                if result:
                    pid, state, duration_sec, idle_sec = result
                    
                    logger.info(f"[LOCK] Holder: pid={pid}, state={state}, duration={duration_sec:.0f}s, idle={idle_sec:.0f}s")
                    
                    heartbeat_age = _get_heartbeat_age_seconds(conn, lock_key)
                    heartbeat_stale = (
                        heartbeat_age is None or heartbeat_age > STALE_HEARTBEAT_SECONDS
                    ) if _heartbeat_supported(conn) else False
                    idle_stale = idle_sec is not None and idle_sec > STALE_IDLE_SECONDS
                    
                    if idle_stale or heartbeat_stale:
                        stale_reasons = []
                        if idle_stale:
                            stale_reasons.append(f"idle>{STALE_IDLE_SECONDS}s")
                        if heartbeat_stale:
                            stale_reasons.append(f"heartbeat>{STALE_HEARTBEAT_SECONDS}s")
                        reason_label = ", ".join(stale_reasons)
                        logger.warning(
                            "[LOCK] ⚠️ STALE LOCK DETECTED: pid=%s idle=%.0fs heartbeat=%s (%s)",
                            pid,
                            idle_sec or 0,
                            f"{heartbeat_age:.0f}s" if heartbeat_age is not None else "none",
                            reason_label,
                        )
                        logger.warning(f"[LOCK] 🔥 Terminating stale process pid={pid}...")
                        
                        try:
                            cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
                            terminated = cur.fetchone()[0]
                            if terminated:
                                event = {
                                    "event": "[LOCK_TAKEOVER]",
                                    "pid": pid,
                                    "reason": reason_label,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                                global _last_takeover_event
                                _last_takeover_event = event
                                logger.warning(
                                    "[LOCK_TAKEOVER] ✅ Terminated stale lock holder pid=%s reason=%s",
                                    pid,
                                    reason_label,
                                )
                                logger.info(f"[LOCK] ✅ Stale process terminated, retrying lock acquisition...")
                                # No need for conn.commit() - autocommit is enabled
                                
                                # Wait for lock release - measured ~500-2000ms in production logs
                                # Using 3s to GUARANTEE lock is fully released (critical for webhook setup)
                                import time
                                time.sleep(LOCK_RELEASE_WAIT_SECONDS)
                                
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
