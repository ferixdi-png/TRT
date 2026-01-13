"""
Auto-migration runner for PostgreSQL
Безопасно применяет migrations/*.sql при старте
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


async def get_applied_migrations(database_url: str) -> Optional[List[str]]:
    """
    Retrieve list of migrations that have been applied.
    Uses migration_history table if available (migration 012+).
    
    Returns:
        List of migration names if tracking table exists, None otherwise
    """
    try:
        import asyncpg
    except ImportError:
        return None
    
    try:
        conn = await asyncpg.connect(database_url, timeout=5)
        
        # Check if migration_history table exists
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='migration_history')"
        )
        
        if not exists:
            # migration 012 not yet applied, no history available
            await conn.close()
            return None
        
        # Fetch applied migrations
        applied = await conn.fetch(
            "SELECT migration_name FROM migration_history WHERE status = 'success' ORDER BY applied_at"
        )
        
        await conn.close()
        return [row['migration_name'] for row in applied]
    
    except Exception as e:
        logger.debug(f"[MIGRATIONS] Could not check migration history: {e}")
        return None



async def apply_migrations_safe(database_url: str) -> bool:
    """
    Безопасно применить миграции из migrations/*.sql
    
    Returns:
        True если миграции применены успешно или не нужны
        False если произошла ошибка
    """
    try:
        import asyncpg
    except ImportError:
        logger.warning("[MIGRATIONS] asyncpg not available, skipping auto-migrations")
        return False
    
    try:
        # SSOT: Единственный источник миграций - /migrations/ в корне проекта
        project_root = Path(__file__).parent.parent.parent
        migrations_dir = project_root / "migrations"
        
        if not migrations_dir.exists():
            logger.error(f"[MIGRATIONS] CRITICAL: SSOT directory not found: {migrations_dir}")
            return False
        
        # Находим все SQL файлы
        sql_files = sorted(migrations_dir.glob("*.sql"))
        if not sql_files:
            logger.info("[MIGRATIONS] No .sql files found, nothing to apply")
            return True
        
        logger.info(f"[MIGRATIONS] Found {len(sql_files)} migration file(s)")
        
        # Подключаемся к БД
        conn: Optional[asyncpg.Connection] = None
        try:
            conn = await asyncpg.connect(database_url, timeout=10)
            
            for sql_file in sql_files:
                try:
                    # Читаем и выполняем миграцию
                    sql_content = sql_file.read_text(encoding='utf-8')
                    
                    # Используем CREATE TABLE IF NOT EXISTS - идемпотентно
                    await conn.execute(sql_content)
                    logger.info(f"[MIGRATIONS] ✅ Applied {sql_file.name}")
                    
                    # Track in migration_history if table exists (migration 012+)
                    try:
                        await conn.execute(
                            "INSERT INTO migration_history (migration_name, status) VALUES ($1, 'success') "
                            "ON CONFLICT (migration_name) DO UPDATE SET status = 'success', applied_at = NOW()",
                            sql_file.name,
                        )
                    except Exception:
                        # migration_history table may not exist yet, that's OK
                        pass
                    
                except Exception as e:
                    # Если ошибка "already exists" - это OK (идемпотентность)
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate" in error_msg:
                        logger.debug(f"[MIGRATIONS] {sql_file.name} already applied (OK)")
                    else:
                        logger.error(f"[MIGRATIONS] ❌ Failed to apply {sql_file.name}: {e}")
                        raise
            
            logger.info("[MIGRATIONS] ✅ All migrations applied successfully")
            return True
            
        finally:
            if conn is not None:
                await conn.close()
    
    except Exception as e:
        logger.exception(f"[MIGRATIONS] Critical error during auto-migration: {e}")
        return False


async def check_migrations_status() -> tuple[bool, int]:
    """
    Check if migrations have been applied successfully.
    Uses migration_history table if available (migration 012+).
    
    Returns:
        Tuple[bool, int]: (all_applied, count_of_migrations)
    """
    try:
        import os
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            return False, 0
        
        try:
            import asyncpg
        except ImportError:
            return False, 0
        
        project_root = Path(__file__).parent.parent.parent
        migrations_dir = project_root / "migrations"
        
        if not migrations_dir.exists():
            return False, 0
        
        sql_files = sorted(migrations_dir.glob("*.sql"))
        if not sql_files:
            return True, 0  # No migrations = OK
        
        # Quick check: try to connect to DB and check migration status
        conn = None
        try:
            conn = await asyncpg.connect(database_url, timeout=5)
            
            # Check if migration_history table exists (migration 012+)
            history_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='migration_history')"
            )
            
            if history_exists:
                # Use migration history for accurate tracking
                applied_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM migration_history WHERE status = 'success'"
                )
                expected_count = len(sql_files)
                all_applied = applied_count >= expected_count
                logger.debug(f"[MIGRATIONS] Migration history check: {applied_count}/{expected_count} applied")
                return all_applied, expected_count
            else:
                # Fallback: assume migrations are applied if DB is accessible
                # (migration 012 not yet applied, no tracking available)
                logger.debug("[MIGRATIONS] Migration history not available (migration 012 not yet applied)")
                return True, len(sql_files)
                
        except Exception as e:
            logger.debug(f"[MIGRATIONS] Migration status check failed: {e}")
            return False, len(sql_files)
        finally:
            if conn:
                await conn.close()
    except Exception:
        return False, 0

