"""
Storage module - unified interface for data persistence.

Exports get_storage() factory function that returns appropriate storage
implementation based on environment configuration.

P0: Async-safe initialization - no asyncio.run() in runtime, no sync_check_pg from async context.
"""

from typing import Optional
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_storage_instance: Optional[object] = None


async def init_pg_storage(database_url: str):
    """
    P0: Async initialization of PostgreSQL storage.
    
    This function should be used when already in async context (runtime).
    It uses async_test_connection() instead of sync test_connection().
    
    Args:
        database_url: PostgreSQL connection string
        
    Returns:
        PostgresStorage instance if connection successful, None otherwise
        
    Raises:
        ImportError: if asyncpg is not available
        RuntimeError: if connection test fails
    """
    try:
        from app.storage.pg_storage import PostgresStorage
        
        # Create storage instance (__init__ is sync, doesn't test connection)
        storage = PostgresStorage(database_url)
        
        # P0: Test connection using async method (no asyncio.run() in runtime)
        try:
            connection_ok = await storage.async_test_connection()
            if not connection_ok:
                logger.warning("[STORAGE] PostgreSQL connection test failed - will fallback to FileStorage on first use")
                return None
        except Exception as e:
            logger.warning(f"[STORAGE] PostgreSQL async connection test error: {e} - will fallback to FileStorage on first use")
            return None
        
        logger.info("[STORAGE] ✅ PostgresStorage initialized and connection verified (async)")
        return storage
    except ImportError as e:
        logger.error(f"[STORAGE] Failed to import PostgresStorage: {e}")
        raise
    except Exception as e:
        logger.error(f"[STORAGE] Failed to initialize PostgresStorage: {e}")
        raise RuntimeError(f"Cannot initialize PostgreSQL storage: {e}") from e


def get_storage():
    """
    Get storage instance (singleton pattern).
    
    Returns:
        - PostgresStorage if DATABASE_URL is set and NO_DATABASE_MODE is not enabled
        - FileStorage if NO_DATABASE_MODE is enabled or DATABASE_URL is not set
    
    CRITICAL: This function must work in both database and file storage modes.
    """
    global _storage_instance
    
    if _storage_instance is not None:
        return _storage_instance
    
    storage_mode = os.getenv("STORAGE_MODE", "").strip().lower()
    no_db_mode = os.getenv('NO_DATABASE_MODE', '').lower() in ('1', 'true', 'yes')
    database_url = os.getenv('DATABASE_URL', '').strip()

    if storage_mode == "github":
        try:
            from app.storage.github_storage import GitHubStorage

            _storage_instance = GitHubStorage()
            logger.info("[STORAGE] Using GitHubStorage (STORAGE_MODE=github)")
            return _storage_instance
        except Exception as e:
            logger.error(f"[STORAGE] Failed to initialize GitHubStorage: {e}")
            raise
    
    if no_db_mode or not database_url:
        # In NO_DATABASE_MODE, main_render.py initializes FileStorage separately
        # We return a placeholder that will be replaced by the actual FileStorage instance
        # This allows get_storage() to be called before FileStorage is initialized
        logger.info("[STORAGE] NO_DATABASE_MODE - FileStorage will be initialized by main_render.py")
        # Create a minimal storage stub that will be replaced
        # For now, try to import and create if available
        try:
            from app.storage.file_storage import FileStorage
            _storage_instance = FileStorage()
            logger.info("[STORAGE] Using FileStorage (NO_DATABASE_MODE or no DATABASE_URL)")
            return _storage_instance
        except (ImportError, AttributeError) as e:
            # FileStorage module doesn't exist - this is expected in some configurations
            # main_render.py will handle FileStorage initialization via init_file_storage()
            logger.debug(f"[STORAGE] FileStorage not available yet (will be initialized by main_render.py): {e}")
            # Return a minimal stub that indicates FileStorage mode
            # The actual storage will be set by main_render.py after init_file_storage()
            class FileStorageStub:
                """Temporary stub until FileStorage is initialized"""
                pass
            _storage_instance = FileStorageStub()
            return _storage_instance
        except Exception as e:
            logger.warning(f"[STORAGE] Failed to initialize FileStorage: {e}, will retry later")
            # Return stub to allow code to continue
            class FileStorageStub:
                pass
            _storage_instance = FileStorageStub()
            return _storage_instance
    else:
        # Use PostgresStorage
        # P0: Check if we're in async context - if yes, warn but don't use asyncio.run()
        try:
            # Try to detect if we're in async context
            loop = asyncio.get_running_loop()
            # If we get here, we're in async context
            # P0: Don't call sync functions that might use asyncio.run() or test_connection()
            # Return storage instance without connection test (will be tested on first async use via _get_pool())
            logger.warning(
                "[STORAGE] get_storage() called from async context. "
                "Consider using init_pg_storage() for proper async initialization. "
                "Creating PostgresStorage without connection test (will test on first use via _get_pool())."
            )
            from app.storage.pg_storage import PostgresStorage
            # CRITICAL: PostgresStorage.__init__ is sync, but it doesn't test connection
            # Connection testing happens async via _get_pool() on first use
            _storage_instance = PostgresStorage(database_url)
            logger.info("[STORAGE] Using PostgresStorage (DATABASE_URL provided, connection test deferred to first async use)")
            return _storage_instance
        except RuntimeError:
            # No running event loop - safe to use sync initialization
            pass
        
        # Now try to initialize PostgresStorage (either from sync context or after RuntimeError)
        try:
            from app.storage.pg_storage import PostgresStorage
            # CRITICAL: PostgresStorage.__init__ is sync, but it doesn't test connection
            # Connection testing happens async via _get_pool() on first use
            _storage_instance = PostgresStorage(database_url)
            logger.info("[STORAGE] Using PostgresStorage (DATABASE_URL provided)")
            return _storage_instance
        except ImportError as e:
            logger.error(f"[STORAGE] Failed to import PostgresStorage: {e}")
            # Fallback to FileStorage if PostgresStorage is not available
            logger.warning("[STORAGE] Falling back to FileStorage due to PostgresStorage import error")
            try:
                from app.storage.file_storage import FileStorage
                _storage_instance = FileStorage()
                logger.info("[STORAGE] Using FileStorage (fallback)")
                return _storage_instance
            except Exception as fallback_error:
                logger.error(f"[STORAGE] Fallback to FileStorage also failed: {fallback_error}")
                raise RuntimeError(f"Cannot initialize storage: {e}") from e
        except Exception as e:
            logger.error(f"[STORAGE] Failed to initialize PostgresStorage: {e}")
            # Fallback to FileStorage
            logger.warning("[STORAGE] Falling back to FileStorage due to PostgresStorage initialization error")
            try:
                from app.storage.file_storage import FileStorage
                _storage_instance = FileStorage()
                logger.info("[STORAGE] Using FileStorage (fallback)")
                return _storage_instance
            except Exception as fallback_error:
                logger.error(f"[STORAGE] Fallback to FileStorage also failed: {fallback_error}")
                raise RuntimeError(f"Cannot initialize storage: {e}") from e


# Export for backward compatibility
__all__ = ['get_storage', 'init_pg_storage']
