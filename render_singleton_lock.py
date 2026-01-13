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
import time
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

# Троттлинг логов для предотвращения спама
_last_lock_held_log: float = 0
_lock_acquisition_failures: int = 0
_backoff_seconds: float = 0.5

def _should_log_lock_held() -> bool:
    """Rate-limit для логов lock held (не чаще 1 раза в 30s)."""
    global _last_lock_held_log
    now = time.time()
    if now - _last_lock_held_log >= 30:
        _last_lock_held_log = now
        return True
    return False

def _get_backoff_delay() -> float:
    """Экспоненциальный backoff: 0.5s → 1s → 2s → 5s → 5s..."""
    global _lock_acquisition_failures, _backoff_seconds
    _lock_acquisition_failures += 1
    
    if _lock_acquisition_failures == 1:
        _backoff_seconds = 0.5
    elif _lock_acquisition_failures == 2:
        _backoff_seconds = 1.0
    elif _lock_acquisition_failures == 3:
        _backoff_seconds = 2.0
    else:
        _backoff_seconds = 5.0
    
    return _backoff_seconds

def _reset_backoff():
    """Сброс backoff после успешного получения lock."""
    global _lock_acquisition_failures, _backoff_seconds
    _lock_acquisition_failures = 0
    _backoff_seconds = 0.5


def split_bigint_to_pg_advisory_oids(lock_key: int) -> tuple[int, int]:
    """
    Разбивает 64-битный lock_key на пару 32-битных signed int для pg_advisory_lock.
    
    PostgreSQL pg_try_advisory_lock(int, int) принимает два SIGNED int32 параметра.
    Диапазон signed int32: -2147483648..2147483647
    
    Args:
        lock_key: 64-битный ключ (0 <= lock_key <= 2^63-1)
    
    Returns:
        tuple[int, int]: (k1, k2) где каждый -2^31 <= value <= 2^31-1
    
    Example:
        >>> split_bigint_to_pg_advisory_oids(2797505866569588743)
        (651107867, -2052522489)  # Второй параметр signed
    """
    # Разбиваем на старшие и младшие 32 бита
    hi = (lock_key >> 32) & 0xFFFFFFFF
    lo = lock_key & 0xFFFFFFFF
    
    # Конвертируем в signed int32 (PostgreSQL int type)
    # Если значение > 2^31-1, вычитаем 2^32 для получения отрицательного числа
    if hi > 0x7FFFFFFF:
        hi -= 0x100000000
    if lo > 0x7FFFFFFF:
        lo -= 0x100000000
    
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
        
        # Разбиваем lock_key на два int4
        k1, k2 = split_bigint_to_pg_advisory_oids(lock_key)
        
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
                  AND pl.classid = %s
                  AND pl.objid = %s
                LIMIT 1
                """,
                (k1, k2),
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
        
        # Разбиваем lock_key на два int4 для двухпараметрового advisory lock
        k1, k2 = split_bigint_to_pg_advisory_oids(lock_key)
        
        # Пытаемся получить advisory lock (неблокирующий, двухпараметровый)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s, %s)", (k1, k2))
            lock_acquired = cur.fetchone()[0]
        
        if lock_acquired:
            _reset_backoff()  # Сброс backoff при успехе
            logger.info(f"✅ PostgreSQL advisory lock acquired: key={lock_key}")
            # ВАЖНО: НЕ возвращаем соединение в пул!
            return conn
        else:
            # Lock занят - применяем троттлинг и backoff
            if _should_log_lock_held():
                logger.warning(f"⏸️ PostgreSQL advisory lock already held by another instance: key={lock_key}")
            
            backoff = _get_backoff_delay()
            time.sleep(backoff)  # Backoff перед следующей попыткой
            
            # Проверяем timestamp последней активности держателя lock
            # Используем двухпараметровый поиск по classid/objid (оба int4)
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
                      AND pl.classid = %s
                      AND pl.objid = %s
                    LIMIT 1
                    """,
                    (k1, k2),
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
                                cur.execute("SELECT pg_try_advisory_lock(%s, %s)", (k1, k2))
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
            # Разбиваем lock_key на два int4
            k1, k2 = split_bigint_to_pg_advisory_oids(lock_key)
            
            # Освобождаем advisory lock (двухпараметровый)
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s, %s)", (k1, k2))
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
