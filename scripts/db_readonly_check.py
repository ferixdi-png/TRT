#!/usr/bin/env python3
"""
Database Readonly Check - безопасная проверка БД для health checks.

Использует DATABASE_URL_READONLY только для SELECT запросов.
Никаких миграций/DDL.
"""

import sys
import os
import asyncio
from pathlib import Path
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def redact_secret(value: str, show_chars: int = 4) -> str:
    """Redact secret, showing only last N chars."""
    if not value or len(value) <= show_chars:
        return "****"
    return "*" * (len(value) - show_chars) + value[-show_chars:]


def load_db_config() -> Dict[str, str]:
    """
    Load DATABASE_URL_READONLY from Desktop/TRT_RENDER.env or env.
    
    Returns:
        Dict with DATABASE_URL_READONLY or empty dict
    """
    config = {}
    
    # Try env first
    db_url = os.getenv("DATABASE_URL_READONLY")
    if db_url:
        config["DATABASE_URL_READONLY"] = db_url
        return config
    
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
                    config["DATABASE_URL_READONLY"] = line.split('=', 1)[1].strip()
                    return config
    
    return config


async def check_database_connection(db_url: str) -> Dict[str, Any]:
    """
    Performs a read-only check of database connectivity.
    
    Returns:
        Dict with connection status and latency
    """
    import asyncpg
    import time
    
    try:
        start_time = time.time()
        conn = await asyncio.wait_for(asyncpg.connect(db_url, timeout=3), timeout=5)
        await conn.fetchval('SELECT 1')
        latency = time.time() - start_time
        await conn.close()
        
        return {
            "status": "ok",
            "latency_ms": round(latency * 1000, 2)
        }
    except asyncio.TimeoutError:
        return {"status": "timeout", "latency_ms": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def get_connection_stats(db_url: str) -> Dict[str, Any]:
    """
    Get database connection statistics (read-only).
    
    Returns:
        Dict with connection counts and stats
    """
    import asyncpg
    
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url, timeout=3), timeout=5)
        
        stats = {}
        
        # Get active connections count
        try:
            active_conns = await conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            )
            stats["active_connections"] = active_conns
        except Exception:
            stats["active_connections"] = None
        
        # Get max connections
        try:
            max_conns = await conn.fetchval("SHOW max_connections")
            if max_conns:
                stats["max_connections"] = int(max_conns)
            else:
                stats["max_connections"] = None
        except Exception:
            stats["max_connections"] = None
        
        # Get database name
        try:
            db_name = await conn.fetchval("SELECT current_database()")
            stats["database_name"] = db_name
        except Exception:
            stats["database_name"] = None
        
        await conn.close()
        return stats
    except Exception as e:
        return {"error": str(e)}


async def get_table_list(db_url: str) -> List[Dict[str, Any]]:
    """
    Get list of tables in the database (read-only).
    
    Returns:
        List of dicts with table info: name, row_count (if accessible)
    """
    import asyncpg
    
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url, timeout=3), timeout=5)
        
        # Get tables from public schema
        tables = await conn.fetch("""
            SELECT 
                tablename as name,
                schemaname as schema
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        
        table_list = []
        for row in tables:
            table_info = {
                "name": row["name"],
                "schema": row["schema"]
            }
            
            # Try to get row count (may fail if no permissions)
            try:
                row_count = await conn.fetchval(
                    f'SELECT COUNT(*) FROM "{row["name"]}"'
                )
                table_info["row_count"] = row_count
            except Exception:
                table_info["row_count"] = None
            
            table_list.append(table_info)
        
        await conn.close()
        return table_list
    except Exception as e:
        return [{"error": str(e)}]


async def check_recent_errors(db_url: str, hours: int = 24) -> List[Dict[str, Any]]:
    """
    Check for recent errors in app_events table (if exists).
    
    Returns:
        List of error events
    """
    import asyncpg
    
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url, timeout=3), timeout=5)
        
        # Check if app_events table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_tables 
                WHERE schemaname = 'public' AND tablename = 'app_events'
            )
        """)
        
        if not table_exists:
            await conn.close()
            return []
        
        # Get recent errors
        errors = await conn.fetch("""
            SELECT 
                id,
                ts,
                level,
                event,
                cid,
                user_id,
                err_stack
            FROM app_events
            WHERE level IN ('ERROR', 'CRITICAL')
            AND ts > NOW() - INTERVAL '%s hours'
            ORDER BY ts DESC
            LIMIT 10
        """, hours)
        
        error_list = []
        for row in errors:
            error_list.append({
                "id": row["id"],
                "timestamp": str(row["ts"]) if row["ts"] else None,
                "level": row["level"],
                "event": row["event"],
                "cid": row["cid"],
                "user_id": row["user_id"],
                "has_stack": bool(row["err_stack"])
            })
        
        await conn.close()
        return error_list
    except Exception as e:
        return [{"error": str(e)}]


async def check_migrations_table(db_url: str) -> bool:
    """
    Checks if the Alembic migrations table exists.
    """
    import asyncpg
    
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url, timeout=3), timeout=5)
        result = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'alembic_version')"
        )
        await conn.close()
        return result
    except Exception as e:
        return False


async def main_async():
    """Main async function for DB checks."""
    print("=" * 70)
    print("  DB READ-ONLY CHECK")
    print("=" * 70)

    config = load_db_config()
    if not config:
        print("\n❌ Config not loaded, exiting")
        return 1

    db_url = config.get("DATABASE_URL_READONLY")
    if not db_url:
        print("\n❌ DATABASE_URL_READONLY missing in TRT_RENDER.env")
        return 1

    # Redact DB URL for display (keep hostname visible)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        db_display = f"{parsed.scheme}://***USER***:***PASSWORD***@{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"
    except Exception:
        db_display = redact_secret(db_url)
    
    print(f"\n  🔗 Database: {db_display}")

    # Check 1: Basic connectivity
    print("\n  📥 Checking DB connectivity...")
    conn_result = await check_database_connection(db_url)
    if conn_result["status"] == "ok":
        print(f"     ✅ Connection OK (latency: {conn_result['latency_ms']}ms)")
    elif conn_result["status"] == "timeout":
        print(f"     ❌ Connection TIMEOUT")
        return 1
    else:
        print(f"     ❌ Connection FAILED: {conn_result.get('error', 'Unknown error')}")
        return 1

    # Check 2: Connection statistics
    print("\n  📊 Connection Statistics:")
    stats = await get_connection_stats(db_url)
    if "error" in stats:
        print(f"     ⚠️  Failed to get stats: {stats['error']}")
    else:
        if stats.get("database_name"):
            print(f"     Database: {stats['database_name']}")
        if stats.get("active_connections") is not None:
            print(f"     Active connections: {stats['active_connections']}")
        if stats.get("max_connections"):
            print(f"     Max connections: {stats['max_connections']}")
            if stats.get("active_connections") is not None:
                usage_pct = (stats['active_connections'] / stats['max_connections']) * 100
                print(f"     Usage: {usage_pct:.1f}%")

    # Check 3: Table list
    print("\n  📋 Tables:")
    tables = await get_table_list(db_url)
    if tables and "error" not in tables[0]:
        print(f"     Found {len(tables)} tables in public schema:")
        for table in tables[:20]:  # Show first 20 tables
            row_info = f" ({table['row_count']} rows)" if table.get("row_count") is not None else ""
            print(f"       - {table['name']}{row_info}")
        if len(tables) > 20:
            print(f"       ... and {len(tables) - 20} more tables")
    elif tables and "error" in tables[0]:
        print(f"     ⚠️  Failed to get table list: {tables[0]['error']}")
    else:
        print("     ℹ️  No tables found in public schema")

    # Check 4: Recent errors (if app_events table exists)
    print("\n  🔍 Recent Errors (last 24h):")
    errors = await check_recent_errors(db_url, hours=24)
    if errors and "error" in errors[0]:
        print(f"     ⚠️  Failed to check errors: {errors[0]['error']}")
    elif errors:
        print(f"     Found {len(errors)} error events:")
        for err in errors[:5]:  # Show top 5
            cid_info = f" cid={err['cid']}" if err.get("cid") else ""
            user_info = f" user={err['user_id']}" if err.get("user_id") else ""
            stack_info = " (has stack)" if err.get("has_stack") else ""
            print(f"       - {err.get('timestamp', 'N/A')}: {err.get('event', 'N/A')}{cid_info}{user_info}{stack_info}")
        if len(errors) > 5:
            print(f"       ... and {len(errors) - 5} more errors")
    else:
        print("     ✅ No errors found in last 24h")

    # Check 5: Migrations table (optional)
    print("\n  🔍 Migrations:")
    migrations_ok = await check_migrations_table(db_url)
    if migrations_ok:
        print("     ✅ Alembic migrations table found")
    else:
        print("     ⚠️  Alembic migrations table not found (migrations may not have run)")

    print("\n" + "=" * 70)
    print("  ✅ DB READ-ONLY CHECK COMPLETE")
    print("=" * 70)
    return 0


def main():
    """Main entry point for the script."""
    try:
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
