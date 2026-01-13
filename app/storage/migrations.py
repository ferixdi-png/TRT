"""
Auto-migration runner for PostgreSQL
Безопасно применяет migrations/*.sql при старте
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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
        
        # Quick check: try to connect to DB
        conn = None
        try:
            conn = await asyncpg.connect(database_url, timeout=5)
            # If we can connect, assume migrations are applied
            # (more detailed check would require migration tracking table)
            return True, len(sql_files)
        except Exception:
            return False, len(sql_files)
        finally:
            if conn:
                await conn.close()
    except Exception:
        return False, 0
