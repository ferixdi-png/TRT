#!/usr/bin/env python3
"""
Migration runner - выполняет SQL миграции из migrations/
"""

import sys
import os
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


async def run_migration(sql_file: Path, database_url: str):
    """Выполнить SQL миграцию"""
    try:
        import asyncpg
        
        # Читаем SQL файл
        sql_content = sql_file.read_text(encoding='utf-8')
        
        # Подключаемся к БД
        conn = await asyncpg.connect(database_url)
        try:
            # Выполняем миграцию
            await conn.execute(sql_content)
            print(f"[OK] Migration {sql_file.name} applied successfully")
        finally:
            await conn.close()
    except ImportError:
        print(f"[ERROR] asyncpg not available, cannot run migration {sql_file.name}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to apply migration {sql_file.name}: {e}")
        raise


async def main():
    """Главная функция"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("[ERROR] DATABASE_URL not set")
        sys.exit(1)
    
    migrations_dir = root_dir / "migrations"
    if not migrations_dir.exists():
        print(f"[ERROR] Migrations directory not found: {migrations_dir}")
        sys.exit(1)
    
    # Находим все SQL файлы
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("[WARN] No migration files found")
        return
    
    print(f"[INFO] Found {len(sql_files)} migration(s)")
    
    for sql_file in sql_files:
        print(f"[INFO] Applying migration: {sql_file.name}")
        await run_migration(sql_file, database_url)
    
    print("[OK] All migrations applied successfully")


if __name__ == "__main__":
    asyncio.run(main())


