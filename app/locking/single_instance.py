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
import asyncio
from pathlib import Path
from typing import Optional, Literal

from app.utils.logging_config import get_logger
from app.config import get_settings

logger = get_logger(__name__)

# Lock configuration
LOCK_MODE_WAIT_PASSIVE = "wait_then_passive"  # Safe: wait, then passive if no lock
LOCK_MODE_WAIT_FORCE = "wait_then_force"      # Risky: force active even without lock
LOCK_DEFAULT_MODE = LOCK_MODE_WAIT_PASSIVE

# Retry configuration  
LOCK_WAIT_SECONDS = int(os.getenv('LOCK_WAIT_SECONDS', '60'))
LOCK_RETRY_BACKOFF_BASE = 0.5  # seconds
LOCK_RETRY_BACKOFF_MAX = 5.0   # seconds
LOCK_RETRY_INTERVAL_BG = 10    # seconds (background retry when in passive)

# Глобальное состояние lock
_lock_handle: Optional[object] = None
_lock_type: Optional[Literal['postgres', 'file']] = None
_lock_connection: Optional[object] = None  # PostgreSQL connection (для session-level lock)
_lock_mode: str = os.getenv('LOCK_MODE', LOCK_DEFAULT_MODE)
_is_active: bool = False  # True if lock acquired, False if passive
_bg_retry_task: Optional[asyncio.Task] = None  # Background task for lock retry


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


# REMOVED: _force_release_stale_lock() was conceptually wrong
# Advisory locks are session-scoped and cannot be released from a different session
# On Render deploy overlap, we WAIT for old instance to release the lock naturally


def acquire_single_instance_lock() -> bool:
    """
    Попытаться получить single instance lock с retry и wait/passive логикой.
    
    Алгоритм:
    1. Пытается получить lock в течение LOCK_WAIT_SECONDS с exponential backoff
    2. Если lock получен -> ACTIVE mode (return True)
    3. Если не получен:
       - LOCK_MODE=wait_then_passive -> PASSIVE mode (return False)
       - LOCK_MODE=wait_then_force -> FORCE ACTIVE (return True, risky!)
    
    Returns:
        True если ACTIVE mode (lock acquired or forced)
        False если PASSIVE mode (webhook returns 200 but no side effects)
    """
    global _lock_handle, _lock_type, _lock_connection, _is_active
    
    database_url = os.getenv('DATABASE_URL')
    lock_mode = os.getenv('LOCK_MODE', LOCK_DEFAULT_MODE)
    
    # Пробуем PostgreSQL advisory lock с retry
    if database_url:
        logger.info("[LOCK] Attempting to acquire PostgreSQL advisory lock...")
        logger.info(f"[LOCK] Mode: {lock_mode}, Wait: {LOCK_WAIT_SECONDS}s")
        
        import time
        start_time = time.time()
        attempt = 0
        
        while time.time() - start_time < LOCK_WAIT_SECONDS:
            lock_data = _acquire_postgres_lock()
            if lock_data:
                _lock_handle = lock_data
                _lock_connection = lock_data['connection']
                _lock_type = 'postgres'
                _is_active = True
                logger.info(f"[LOCK] ✅ ACTIVE MODE: PostgreSQL advisory lock acquired (attempt {attempt + 1})")
                return True
            
            # Exponential backoff
            attempt += 1
            backoff = min(LOCK_RETRY_BACKOFF_BASE * (2 ** attempt), LOCK_RETRY_BACKOFF_MAX)
            remaining = LOCK_WAIT_SECONDS - (time.time() - start_time)
            
            if remaining <= 0:
                break
                
            wait_time = min(backoff, remaining)
            logger.debug(f"[LOCK] Attempt {attempt} failed, retrying in {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        # Lock not acquired after wait period
        logger.warning("=" * 60)
        logger.warning(f"[LOCK] PostgreSQL advisory lock NOT acquired after {LOCK_WAIT_SECONDS}s")
        logger.warning("[LOCK] This is normal during Render deploy overlap")
        
        if lock_mode == LOCK_MODE_WAIT_FORCE:
            logger.error("[LOCK] ⚠️  FORCE ACTIVE MODE (risky!)")
            logger.error("[LOCK] Proceeding as ACTIVE despite missing lock")
            logger.error("[LOCK] WARNING: May cause conflicts if multiple instances running!")
            logger.error("=" * 60)
            _is_active = True
            return True
        else:
            logger.info("[LOCK] ⏸️  PASSIVE MODE: Webhook will return 200 but no processing")
            logger.info("[LOCK] Background retry task will attempt to acquire lock periodically")
            logger.info("=" * 60)
            _is_active = False
            return False
    
    # Fallback to filelock if no DATABASE_URL
    lock_handle = _acquire_file_lock()
    if lock_handle:
        _lock_handle = lock_handle
        _lock_connection = None
        _lock_type = 'file'
        _is_active = True
        logger.info("[LOCK] ✅ ACTIVE MODE: File lock acquired")
        return True
    
    # No lock mechanism available
    logger.warning("[LOCK] ⚠️  No lock mechanism available, proceeding as ACTIVE")
    _is_active = True
    return True


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


def is_active_mode() -> bool:
    """
    Проверить, в ACTIVE ли режиме бот (lock получен или forced).
    PASSIVE mode: webhook returns 200 but no side effects.
    """
    return _is_active


async def start_background_lock_retry():
    """
    Запустить фоновую задачу для retry lock acquisition в PASSIVE режиме.
    Когда lock становится доступным, переключаемся в ACTIVE mode автоматически.
    """
    global _bg_retry_task
    
    if _is_active:
        logger.debug("[LOCK] Already in ACTIVE mode, no background retry needed")
        return
    
    if _bg_retry_task is not None:
        logger.debug("[LOCK] Background retry task already running")
        return
    
    async def _retry_loop():
        global _lock_handle, _lock_type, _lock_connection, _is_active
        
        logger.info("[LOCK] Starting background lock retry task...")
        attempt = 0
        while not _is_active:
            await asyncio.sleep(LOCK_RETRY_INTERVAL_BG)
            
            if _is_active:
                logger.info("[LOCK] Lock acquired by another path, stopping retry")
                break
            
            attempt += 1
            logger.info(f"[LOCK] Background retry attempt {attempt}...")
            
            # Try to acquire lock (synchronous call)
            try:
                lock_data = _acquire_postgres_lock()
                if lock_data:
                    _lock_handle = lock_data
                    _lock_connection = lock_data['connection']
                    _lock_type = 'postgres'
                    _is_active = True
                    logger.info("=" * 60)
                    logger.info(f"[LOCK] ✅ PASSIVE → ACTIVE: Lock acquired on retry {attempt}!")
                    logger.info("[LOCK] Bot now processing updates normally")
                    logger.info("=" * 60)
                    break
            except Exception as e:
                logger.warning(f"[LOCK] Background retry {attempt} failed: {e}")
    
    _bg_retry_task = asyncio.create_task(_retry_loop())
    logger.info("[LOCK] Background lock retry task started")


def stop_background_lock_retry():
    """Остановить фоновую задачу retry lock acquisition"""
    global _bg_retry_task
    
    if _bg_retry_task is not None:
        _bg_retry_task.cancel()
        _bg_retry_task = None
        logger.info("[LOCK] Background lock retry task stopped")

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
        
        Args:
            timeout: Timeout in seconds for connection AND lock acquisition attempt
        
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
            # Use timeout for connection
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
            
            # Try to acquire advisory lock (immediate, non-blocking)
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
            logger.error(f"Timeout ({timeout}s) acquiring singleton lock")
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

