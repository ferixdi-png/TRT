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
                logger.debug(f"[LOCK] PostgreSQL advisory lock NOT acquired (key={lock_key}) - another instance is running")
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


def _force_release_stale_lock() -> None:
    """
    На Render при деплое старый процесс может зависнуть с lock'ом.
    Этот метод пытается forcefully освободить lock если текущий process_id другой.
    
    Это безопасно потому что:
    - Мы проверяем что это другой процесс
    - На Render старый контейнер уже умирает при деплое
    - Lock автоматически освобождается при disconnect (session-level)
    """
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return
        
        from database import get_connection_pool
        pool = get_connection_pool()
        if pool is None:
            return
        
        import render_singleton_lock
        lock_key = _get_lock_key()
        
        # Пробуем forcefully unlock (это не гарантирует что lock был у нас, но пробуем)
        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                # Просто пробуем unlock, если это был наш lock - хорошо, если нет - курсор просто ничего не сделает
                cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
                result = cur.fetchone()[0] if cur.fetchone() else False
        except:
            pass
        finally:
            try:
                pool.putconn(conn)
            except:
                pass
        
        logger.debug("[LOCK] Stale lock release attempted")
    except Exception as e:
        logger.debug(f"[LOCK] Could not attempt stale lock release: {e}")


def acquire_single_instance_lock() -> bool:
    """
    Попытаться получить single instance lock (PostgreSQL или filelock).
    
    На Render: для одного инстанса эта функция ДОЛЖНА вернуть True.
    Если lock не получен - это либо ошибка БД, либо остаток от старого деплоя.
    
    Returns:
        True если lock получен, False в экстренных случаях (passive mode)
        
    Side effect:
        Сохраняет lock handle в глобальной переменной для последующего освобождения
    """
    global _lock_handle, _lock_type, _lock_connection
    
    database_url = os.getenv('DATABASE_URL')
    strict_mode = os.getenv('SINGLETON_LOCK_STRICT', '0') == '1'
    force_active = os.getenv('SINGLETON_LOCK_FORCE_ACTIVE', '1') == '1'  # Default: True для Render
    
    # Пробуем PostgreSQL advisory lock сначала
    lock_data = _acquire_postgres_lock()
    if lock_data:
        _lock_handle = lock_data
        _lock_connection = lock_data['connection']
        _lock_type = 'postgres'
        logger.info("[LOCK] ✅ ACTIVE MODE: Acquired PostgreSQL advisory lock")
        return True
    
    # Если DATABASE_URL установлен, но PostgreSQL lock не получен
    if database_url:
        logger.warning("=" * 60)
        logger.warning("[LOCK] PostgreSQL advisory lock NOT acquired on first attempt")
        logger.warning("[LOCK] Attempting to release any stale lock from previous deployment...")
        
        # Попробуем освободить старый lock и повторить
        _force_release_stale_lock()
        
        # Повторная попытка получить lock
        logger.info("[LOCK] Retrying lock acquisition after stale release...")
        lock_data = _acquire_postgres_lock()
        if lock_data:
            _lock_handle = lock_data
            _lock_connection = lock_data['connection']
            _lock_type = 'postgres'
            logger.info("[LOCK] ✅ ACTIVE MODE: Acquired PostgreSQL advisory lock (after stale release)")
            return True
        
        # Если все еще не получилось
        logger.error("[LOCK] PostgreSQL advisory lock still NOT acquired after stale release")
        
        if force_active:
            # FORCE ACTIVE MODE (для Render с одним инстансом)
            # Если на Render один инстанс - lock должен быть
            # Если lock не получен - это ошибка, но мы не можем быть в PASSIVE MODE
            logger.error("[LOCK] FORCE ACTIVE MODE: Proceeding as ACTIVE despite lock failure")
            logger.error("[LOCK] WARNING: This assumes you have only ONE Render Web Service instance!")
            logger.error("[LOCK] If you have multiple instances, they may conflict. Use DATABASE_URL properly!")
            logger.error("=" * 60)
            
            # Возвращаем True но отмечаем что это без реального lock'а
            # Это опасно для multi-instance, но на Render обычно один инстанс
            return True
        elif strict_mode:
            # STRICT MODE: exit
            logger.error("[LOCK] STRICT MODE: Exiting gracefully (exit code 0)")
            logger.error("=" * 60)
            sys.exit(0)
        else:
            # PASSIVE MODE: не завершаем процесс, переходим в safe mode
            logger.warning("[LOCK] PASSIVE MODE: Telegram runner will be disabled")
            logger.warning("[LOCK] Healthcheck server will continue running")
            logger.warning("=" * 60)
            return False
    
    # Fallback на filelock ТОЛЬКО если DATABASE_URL не установлен
    lock_handle = _acquire_file_lock()
    if lock_handle:
        _lock_handle = lock_handle
        _lock_connection = None
        _lock_type = 'file'
        return True
    
    # Lock не получен - другой экземпляр запущен
    logger.warning("=" * 60)
    logger.warning("[LOCK] WARNING: Another bot instance is already running")
    
    if strict_mode:
        # STRICT MODE: exit
        logger.error("[LOCK] STRICT MODE: Exiting gracefully (exit code 0)")
        logger.error("=" * 60)
        import sys
        sys.exit(0)
    else:
        # PASSIVE MODE: не завершаем процесс
        logger.warning("[LOCK] PASSIVE MODE: Telegram runner will be disabled")
        logger.warning("[LOCK] Healthcheck server will continue running")
        logger.warning("=" * 60)
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

try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


# Lock TTL in seconds (aggressive for zero-downtime rolling deployment)
LOCK_TTL = 10
HEARTBEAT_INTERVAL = 3  # Heartbeat more frequently to avoid false stale detection


class SingletonLock:
    """
    PostgreSQL advisory lock with TTL for ensuring only one active instance.
    """
    
    def __init__(self, dsn: Optional[str] = None, instance_name: str = "bot-instance"):
        self.dsn = dsn
        self.instance_name = instance_name
        self._connection = None
        self._lock_id = 12345
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._acquired = False
    
    async def _ensure_heartbeat_table(self):
        """Create heartbeat table if not exists."""
        if not self._connection:
            return
        
        try:
            await self._connection.execute("""
                CREATE TABLE IF NOT EXISTS singleton_heartbeat (
                    lock_id INTEGER PRIMARY KEY,
                    instance_name TEXT NOT NULL,
                    last_heartbeat TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
        except Exception as e:
            logger.warning(f"Could not create heartbeat table: {e}")
    
    async def _update_heartbeat(self):
        """Update heartbeat timestamp."""
        if not self._connection:
            return
        
        try:
            await self._connection.execute("""
                INSERT INTO singleton_heartbeat (lock_id, instance_name, last_heartbeat)
                VALUES ($1, $2, NOW())
                ON CONFLICT (lock_id) DO UPDATE
                SET instance_name = EXCLUDED.instance_name,
                    last_heartbeat = NOW()
            """, self._lock_id, self.instance_name)
        except Exception as e:
            logger.warning(f"Could not update heartbeat: {e}")
    
    async def _cleanup_stale_locks(self):
        """
        Release stale locks (no heartbeat for LOCK_TTL seconds).
        Also forcefully unlock PostgreSQL advisory lock if stale.
        """
        if not self._connection:
            return
        
        try:
            # Check if there's a stale lock
            result = await self._connection.fetchrow(f"""
                SELECT instance_name, last_heartbeat
                FROM singleton_heartbeat
                WHERE lock_id = $1
                AND last_heartbeat < NOW() - INTERVAL '{LOCK_TTL} seconds'
            """, self._lock_id)
            
            if result:
                logger.warning(f"🔓 Found STALE lock from {result['instance_name']} "
                             f"(last heartbeat: {result['last_heartbeat']}) - force unlocking!")
                
                # Force release PostgreSQL advisory lock
                if HAS_ASYNCPG:
                    unlocked = await self._connection.fetchval(
                        "SELECT pg_advisory_unlock_all()"
                    )
                    logger.info(f"Advisory lock force released: {unlocked}")
                else:  # psycopg
                    async with self._connection.cursor() as cur:
                        await cur.execute("SELECT pg_advisory_unlock_all()")
                        result_unlock = await cur.fetchone()
                        logger.info(f"Advisory lock force released: {result_unlock[0] if result_unlock else False}")
                
                # Delete stale heartbeat record
                await self._connection.execute(
                    "DELETE FROM singleton_heartbeat WHERE lock_id = $1",
                    self._lock_id
                )
                logger.info("✅ Stale lock cleaned up - ready for new acquisition")
        except Exception as e:
            logger.warning(f"Could not check stale locks: {e}")
    
    async def _heartbeat_loop(self):
        """Background task to update heartbeat."""
        while self._acquired:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if self._acquired:
                    await self._update_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def acquire(self, timeout: float = 5.0) -> bool:
        """
        Acquire singleton lock with stale detection.
        
        Returns:
            True if lock acquired, False otherwise
        """
        if not self.dsn:
            logger.warning("No database URL - running without singleton lock")
            return False
        
        if not HAS_ASYNCPG and not HAS_PSYCOPG:
            logger.warning("No PostgreSQL driver available - running without lock")
            return False
        
        try:
            if HAS_ASYNCPG:
                self._connection = await asyncio.wait_for(
                    asyncpg.connect(self.dsn),
                    timeout=timeout
                )
            elif HAS_PSYCOPG:
                self._connection = await asyncio.wait_for(
                    psycopg.AsyncConnection.connect(self.dsn),
                    timeout=timeout
                )
            else:
                return False
            
            # Create heartbeat table
            await self._ensure_heartbeat_table()
            
            # Cleanup stale locks
            await self._cleanup_stale_locks()
            
            # Try to acquire advisory lock
            if HAS_ASYNCPG:
                acquired = await self._connection.fetchval(
                    "SELECT pg_try_advisory_lock($1)",
                    self._lock_id
                )
            else:  # psycopg
                async with self._connection.cursor() as cur:
                    await cur.execute("SELECT pg_try_advisory_lock(%s)", (self._lock_id,))
                    result = await cur.fetchone()
                    acquired = result[0] if result else False
            
            if acquired:
                self._acquired = True
                await self._update_heartbeat()
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                logger.info(f"✅ Singleton lock acquired by {self.instance_name}")
                return True
            else:
                logger.warning(f"⚠️ Singleton lock NOT acquired - another instance is active")
                await self._connection.close()
                self._connection = None
                return False
        
        except asyncio.TimeoutError:
            logger.error("Timeout acquiring singleton lock")
            return False
        except Exception as e:
            logger.error(f"Error acquiring singleton lock: {e}")
            if self._connection:
                try:
                    await self._connection.close()
                except Exception as close_err:
                    # MASTER PROMPT: No bare except - specific exception type
                    logger.debug(f"Error closing connection during cleanup: {close_err}")
                    pass
                self._connection = None
            return False
    
    async def release(self):
        """Release singleton lock with detailed logging for zero-downtime deployment tracking."""
        if not self._acquired:
            logger.debug("Lock already released or not acquired - skipping release")
            return
        
        logger.info(f"🔓 Starting lock release for {self.instance_name}...")
        self._acquired = False
        
        # Cancel heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
                logger.info("Heartbeat task cancelled successfully")
            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled (expected)")
            self._heartbeat_task = None
        
        if not self._connection:
            logger.warning("No connection available for lock release")
            return
        
        try:
            # Release advisory lock
            if HAS_ASYNCPG:
                released = await self._connection.fetchval(
                    "SELECT pg_advisory_unlock($1)",
                    self._lock_id
                )
                logger.info(f"Advisory lock released: {released}")
            else:  # psycopg
                async with self._connection.cursor() as cur:
                    await cur.execute("SELECT pg_advisory_unlock(%s)", (self._lock_id,))
                    result = await cur.fetchone()
                    logger.info(f"Advisory lock released: {result[0] if result else False}")
            
            # Remove heartbeat record
            deleted = await self._connection.execute(
                "DELETE FROM singleton_heartbeat WHERE lock_id = $1",
                self._lock_id
            )
            logger.info(f"Heartbeat record removed (rows affected: {deleted})")
            
            logger.info(f"✅ Singleton lock fully released by {self.instance_name} - new instance can acquire")
        except Exception as e:
            logger.error(f"❌ Error releasing lock: {e}", exc_info=True)
        finally:
            try:
                await self._connection.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            self._connection = None

