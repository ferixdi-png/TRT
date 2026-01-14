#!/usr/bin/env python3
"""
Database Readonly Check - безопасная проверка БД для health checks.

Использует DATABASE_URL_READONLY только для SELECT запросов.
Никаких миграций/DDL.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_db_config() -> Optional[str]:
    """
    Load DATABASE_URL_READONLY from Desktop/TRT_RENDER.env or env.
    
    Returns:
        Database URL or None
    """
    # Try env first
    db_url = os.getenv("DATABASE_URL_READONLY")
    if db_url:
        return db_url
    
    # Try Desktop config
    if os.name == 'nt':  # Windows
        desktop_path = Path(os.getenv('USERPROFILE', '')) / 'Desktop'
    else:  # macOS/Linux
        desktop_path = Path.home() / 'Desktop'
    
    env_file = desktop_path / 'TRT_RENDER.env'
    
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('DATABASE_URL_READONLY='):
                    return line.split('=', 1)[1].strip()
    
    return None


def check_database_connection(db_url: str) -> Dict[str, any]:
    """
    Check database connection and basic health.
    
    Returns:
        Dict with status, tables, and basic info
    """
    result = {
        "status": "unknown",
        "connected": False,
        "tables_checked": False,
        "error": None,
    }
    
    try:
        import asyncpg
        import asyncio
    except ImportError:
        result["error"] = "asyncpg not available"
        return result
    
    async def check():
        try:
            # Connect with short timeout
            conn = await asyncio.wait_for(
                asyncpg.connect(db_url, timeout=5),
                timeout=10
            )
            
            try:
                # Test 1: SELECT 1
                row = await conn.fetchrow("SELECT 1 as test")
                if row and row['test'] == 1:
                    result["connected"] = True
                    result["status"] = "ok"
                
                # Test 2: Check if migrations table exists (indicates schema is initialized)
                try:
                    migrations = await conn.fetchval(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                    )
                    result["tables_checked"] = True
                    result["has_migrations"] = migrations > 0 if migrations else False
                except Exception as e:
                    result["migrations_check_error"] = str(e)
                
                # Test 3: Check key tables (if they exist)
                key_tables = ["users", "wallets", "jobs", "app_events"]
                existing_tables = []
                for table in key_tables:
                    try:
                        count = await conn.fetchval(
                            f"SELECT COUNT(*) FROM information_schema.tables "
                            f"WHERE table_schema = 'public' AND table_name = '{table}'"
                        )
                        if count and count > 0:
                            existing_tables.append(table)
                    except Exception:
                        pass
                
                result["existing_tables"] = existing_tables
                
            finally:
                await conn.close()
                
        except asyncio.TimeoutError:
            result["error"] = "Connection timeout"
            result["status"] = "timeout"
        except Exception as e:
            result["error"] = str(e)
            result["status"] = "error"
    
    try:
        asyncio.run(check())
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
    
    return result


def print_report(result: Dict):
    """Print diagnostic report."""
    print("\n" + "=" * 60)
    print("  DATABASE READONLY CHECK")
    print("=" * 60)
    
    if result["connected"]:
        print("  ✅ Database connection: OK")
    else:
        print(f"  ❌ Database connection: FAILED")
        if result["error"]:
            print(f"     Error: {result['error']}")
    
    if result.get("tables_checked"):
        if result.get("has_migrations"):
            print("  ✅ Migrations table: Found")
        else:
            print("  ⚠️  Migrations table: Not found (schema may not be initialized)")
    
    if result.get("existing_tables"):
        print(f"  ✅ Key tables found: {', '.join(result['existing_tables'])}")
    
    print("=" * 60)
    
    return 0 if result["connected"] else 1


def main():
    """Main function."""
    print("=" * 60)
    print("  DATABASE READONLY CHECK")
    print("=" * 60)
    
    # Load config
    db_url = load_db_config()
    if not db_url:
        print("\n❌ DATABASE_URL_READONLY not found")
        print("   Set it in Desktop/TRT_RENDER.env or environment")
        return 1
    
    # Redact password in URL
    if '@' in db_url and ':' in db_url.split('@')[0]:
        parts = db_url.split('@')
        if len(parts) == 2:
            user_pass = parts[0]
            rest = parts[1]
            if ':' in user_pass:
                user, _ = user_pass.rsplit(':', 1)
                redacted = f"{user}:****@{rest}"
            else:
                redacted = f"****@{rest}"
        else:
            redacted = "****"
    else:
        redacted = "****"
    
    print(f"\n  Database URL: {redacted}")
    
    # Check connection
    print("  🔍 Checking connection...")
    result = check_database_connection(db_url)
    
    # Print report
    exit_code = print_report(result)
    
    return exit_code


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

