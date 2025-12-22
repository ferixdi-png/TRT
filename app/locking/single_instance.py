"""
Single instance locking using PostgreSQL advisory locks.
Prevents multiple bot instances from running simultaneously.
"""
import os
import sys
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    try:
        import psycopg
        HAS_PSYCOPG = True
    except ImportError:
        HAS_PSYCOPG = False

from app.utils.singleton_lock import (
    set_lock_acquired,
    is_lock_acquired,
    should_exit_on_lock_conflict,
    get_safe_mode
)


class SingletonLock:
    """PostgreSQL advisory lock for single instance enforcement."""
    
    LOCK_ID = 123456789  # Fixed advisory lock ID
    
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self._connection = None
        self._lock_held = False
        
    async def acquire(self, timeout: float = 5.0) -> bool:
        """
        Acquire PostgreSQL advisory lock.
        
        Args:
            timeout: Timeout for connection in seconds
            
        Returns:
            True if lock acquired, False if already held by another instance
        """
        if not self.dsn:
            logger.warning("DATABASE_URL not set, skipping singleton lock")
            # In passive mode, allow startup without lock
            set_lock_acquired(False)
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
                logger.warning("No async PostgreSQL driver available, skipping singleton lock")
                set_lock_acquired(False)
                return False
                
            # Try to acquire advisory lock (non-blocking)
            if HAS_ASYNCPG:
                lock_acquired = await self._connection.fetchval(
                    "SELECT pg_try_advisory_lock($1)",
                    self.LOCK_ID
                )
            else:  # psycopg
                async with self._connection.cursor() as cur:
                    await cur.execute(
                        "SELECT pg_try_advisory_lock(%s)",
                        (self.LOCK_ID,)
                    )
                    result = await cur.fetchone()
                    lock_acquired = result[0] if result else False
                    
            if lock_acquired:
                self._lock_held = True
                set_lock_acquired(True)
                logger.info(f"PostgreSQL advisory lock acquired (ID: {self.LOCK_ID})")
                return True
            else:
                self._lock_held = False
                set_lock_acquired(False)
                logger.warning(
                    f"PostgreSQL advisory lock already held (ID: {self.LOCK_ID}). "
                    f"Another instance is running."
                )
                
                # Check if we should exit or go to passive mode
                if should_exit_on_lock_conflict():
                    logger.info("SINGLETON_LOCK_STRICT=1: Exiting gracefully (exit code 0)")
                    await self.release()
                    sys.exit(0)
                else:
                    logger.info(
                        "[LOCK] Passive mode: telegram runner disabled, healthcheck only. "
                        f"Safe mode: {get_safe_mode()}"
                    )
                    return False
                    
        except asyncio.TimeoutError:
            logger.warning(f"Singleton lock acquisition timed out after {timeout}s")
            set_lock_acquired(False)
            return False
        except Exception as e:
            logger.error(f"Failed to acquire singleton lock: {e}")
            set_lock_acquired(False)
            return False
    
    async def release(self):
        """Release PostgreSQL advisory lock."""
        if not self._connection or not self._lock_held:
            return
            
        try:
            if HAS_ASYNCPG:
                await self._connection.execute(
                    "SELECT pg_advisory_unlock($1)",
                    self.LOCK_ID
                )
            else:  # psycopg
                async with self._connection.cursor() as cur:
                    await cur.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (self.LOCK_ID,)
                    )
                    
            self._lock_held = False
            set_lock_acquired(False)
            logger.info("PostgreSQL advisory lock released")
        except Exception as e:
            logger.error(f"Failed to release singleton lock: {e}")
        finally:
            if self._connection:
                await self._connection.close()
                self._connection = None
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
