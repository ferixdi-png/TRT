#!/usr/bin/env python3
"""
Диагностический скрипт для проверки данных в PostgreSQL.
Запуск: python scripts/check_db_data.py
"""
import asyncio
import os
import json
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set!")
        print("Set it in environment or .env file")
        return
    
    try:
        import asyncpg
    except ImportError:
        print("ERROR: asyncpg not installed. Run: pip install asyncpg")
        return
    
    print(f"Connecting to database...")
    print(f"DATABASE_URL: {database_url[:50]}...")
    
    try:
        conn = await asyncpg.connect(database_url)
        print("Connected!\n")
        
        # 1. Check all partner_ids
        print("=" * 60)
        print("1. ALL PARTNER_IDS IN DATABASE:")
        print("=" * 60)
        rows = await conn.fetch("""
            SELECT DISTINCT partner_id, COUNT(*) as file_count 
            FROM storage_json 
            GROUP BY partner_id 
            ORDER BY file_count DESC
        """)
        for row in rows:
            print(f"  partner_id={row['partner_id']!r} files={row['file_count']}")
        
        if not rows:
            print("  (NO DATA IN storage_json TABLE!)")
        
        # 2. Check critical files for each partner
        print("\n" + "=" * 60)
        print("2. CRITICAL FILES STATUS:")
        print("=" * 60)
        critical_files = ['payments.json', 'user_balances.json', 'user_registry.json', 'generations_history.json']
        
        rows = await conn.fetch("""
            SELECT partner_id, filename, 
                   jsonb_typeof(payload) as payload_type,
                   CASE 
                       WHEN jsonb_typeof(payload) = 'object' THEN jsonb_object_keys(payload)::text
                       ELSE 'N/A'
                   END as keys_count,
                   updated_at
            FROM storage_json 
            WHERE filename = ANY($1)
            ORDER BY partner_id, filename
        """, critical_files)
        
        for row in rows:
            print(f"  partner_id={row['partner_id']!r} file={row['filename']}")
            print(f"    type={row['payload_type']} updated_at={row['updated_at']}")
        
        # 3. Detailed check for payments.json
        print("\n" + "=" * 60)
        print("3. PAYMENTS.JSON DETAILS:")
        print("=" * 60)
        rows = await conn.fetch("""
            SELECT partner_id, 
                   CASE WHEN payload IS NULL THEN 0
                        WHEN jsonb_typeof(payload) = 'object' THEN (SELECT COUNT(*) FROM jsonb_object_keys(payload))
                        ELSE -1
                   END as keys_count,
                   pg_column_size(payload) as payload_size_bytes,
                   updated_at
            FROM storage_json 
            WHERE filename = 'payments.json'
        """)
        
        for row in rows:
            print(f"  partner_id={row['partner_id']!r}")
            print(f"    keys_count={row['keys_count']} size={row['payload_size_bytes']} bytes")
            print(f"    updated_at={row['updated_at']}")
        
        if not rows:
            print("  (NO payments.json FOUND!)")
        
        # 4. Detailed check for user_balances.json
        print("\n" + "=" * 60)
        print("4. USER_BALANCES.JSON DETAILS:")
        print("=" * 60)
        rows = await conn.fetch("""
            SELECT partner_id, 
                   CASE WHEN payload IS NULL THEN 0
                        WHEN jsonb_typeof(payload) = 'object' THEN (SELECT COUNT(*) FROM jsonb_object_keys(payload))
                        ELSE -1
                   END as keys_count,
                   pg_column_size(payload) as payload_size_bytes,
                   updated_at
            FROM storage_json 
            WHERE filename = 'user_balances.json'
        """)
        
        for row in rows:
            print(f"  partner_id={row['partner_id']!r}")
            print(f"    keys_count={row['keys_count']} size={row['payload_size_bytes']} bytes")
            print(f"    updated_at={row['updated_at']}")
            
        if not rows:
            print("  (NO user_balances.json FOUND!)")
        
        # 5. Check migrations_meta
        print("\n" + "=" * 60)
        print("5. MIGRATIONS STATUS:")
        print("=" * 60)
        rows = await conn.fetch("SELECT * FROM migrations_meta ORDER BY completed_at")
        for row in rows:
            print(f"  key={row['key']!r} completed_at={row['completed_at']}")
        
        if not rows:
            print("  (NO MIGRATIONS COMPLETED)")
        
        # 6. Sample data from payments if exists
        print("\n" + "=" * 60)
        print("6. SAMPLE PAYMENTS DATA (first 3):")
        print("=" * 60)
        rows = await conn.fetch("""
            SELECT partner_id, 
                   (SELECT jsonb_agg(value) FROM (
                       SELECT value FROM jsonb_each(payload) LIMIT 3
                   ) t) as sample_data
            FROM storage_json 
            WHERE filename = 'payments.json'
            AND jsonb_typeof(payload) = 'object'
        """)
        
        for row in rows:
            print(f"  partner_id={row['partner_id']!r}")
            if row['sample_data']:
                print(f"    sample: {json.dumps(row['sample_data'], indent=2, default=str)[:500]}")
            else:
                print("    (EMPTY OR NULL)")
        
        await conn.close()
        print("\n" + "=" * 60)
        print("DIAGNOSIS COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
