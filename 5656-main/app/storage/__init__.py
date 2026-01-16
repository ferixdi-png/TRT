"""
Storage module - unified interface for data persistence.

Exports get_storage() factory function that returns appropriate storage
implementation based on environment configuration.
"""

from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_storage_instance: Optional[object] = None


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
    
    # Check NO_DATABASE_MODE first
    no_db_mode = os.getenv('NO_DATABASE_MODE', '').lower() in ('1', 'true', 'yes')
    database_url = os.getenv('DATABASE_URL', '').strip()
    
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
        try:
            from app.storage.pg_storage import PostgresStorage
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
__all__ = ['get_storage']

