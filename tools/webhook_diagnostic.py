#!/usr/bin/env python3
"""
🚨 ITERATION 2: Webhook Diagnostic & Fix
Системная проверка почему бот не отвечает на сообщения
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def diagnose_webhook():
    """Диагностика webhook setup"""
    print("=" * 70)
    print("🔍 WEBHOOK DIAGNOSTIC")
    print("=" * 70)
    
    # Check 1: Environment variables
    print("\n1️⃣ ENVIRONMENT VARIABLES:")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    webhook_base = os.getenv("WEBHOOK_BASE_URL", "")
    webhook_secret = os.getenv("WEBHOOK_SECRET_PATH", "")
    
    if not token:
        print("   ❌ TELEGRAM_BOT_TOKEN not set")
        return False
    print(f"   ✅ TELEGRAM_BOT_TOKEN: {token[:10]}... ({len(token)} chars)")
    
    if not webhook_base:
        print("   ❌ WEBHOOK_BASE_URL not set")
        return False
    print(f"   ✅ WEBHOOK_BASE_URL: {webhook_base}")
    
    if not webhook_secret:
        print("   ⚠️  WEBHOOK_SECRET_PATH not set (using default)")
        webhook_secret = token.replace(":", "")
    print(f"   ✅ WEBHOOK_SECRET_PATH: {webhook_secret[:6]}...")
    
    # Check 2: Bot can be reached
    print("\n2️⃣ BOT CONNECTIVITY:")
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
        
        # Get bot info
        me = await bot.get_me()
        print(f"   ✅ Bot username: @{me.username}")
        print(f"   ✅ Bot ID: {me.id}")
        print(f"   ✅ Bot name: {me.first_name}")
        
        # Get webhook info
        webhook_info = await bot.get_webhook_info()
        print(f"\n3️⃣ CURRENT WEBHOOK:")
        if webhook_info.url:
            print(f"   📡 URL: {webhook_info.url}")
            print(f"   📊 Pending updates: {webhook_info.pending_update_count}")
            if webhook_info.last_error_message:
                print(f"   ❌ Last error: {webhook_info.last_error_message}")
                print(f"   ⏰ Error date: {webhook_info.last_error_date}")
            else:
                print(f"   ✅ No errors")
            
            # Check if webhook URL matches expected
            expected_url = f"{webhook_base}/webhook/{webhook_secret}"
            if webhook_info.url == expected_url:
                print(f"   ✅ Webhook URL matches config")
            else:
                print(f"   ⚠️  Webhook URL mismatch!")
                print(f"      Expected: {expected_url}")
                print(f"      Actual:   {webhook_info.url}")
        else:
            print(f"   ⚠️  No webhook set (bot in polling mode or not configured)")
        
        await bot.session.close()
        return True
        
    except Exception as e:
        print(f"   ❌ Failed to connect to bot: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_webhook_endpoint():
    """Test webhook endpoint HTTP"""
    print("\n4️⃣ WEBHOOK ENDPOINT TEST:")
    
    webhook_base = os.getenv("WEBHOOK_BASE_URL", "")
    if not webhook_base:
        print("   ⏭️  Skipped (no WEBHOOK_BASE_URL)")
        return
    
    try:
        import aiohttp
        
        # Test health endpoint
        async with aiohttp.ClientSession() as session:
            health_url = f"{webhook_base}/health"
            print(f"   Testing: {health_url}")
            
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                status = resp.status
                text = await resp.text()
                
                if status == 200:
                    print(f"   ✅ Health endpoint: {status}")
                    try:
                        data = json.loads(text) if text else {}
                        print(f"      Active: {data.get('active', '?')}")
                        print(f"      Lock: {data.get('lock_acquired', '?')}")
                    except:
                        pass
                else:
                    print(f"   ❌ Health endpoint: {status}")
                    print(f"      Response: {text[:200]}")
    
    except Exception as e:
        print(f"   ❌ Failed to test endpoint: {e}")


async def check_migrations():
    """Check migration status"""
    print("\n5️⃣ DATABASE MIGRATIONS:")
    
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("   ⏭️  Skipped (no DATABASE_URL)")
        return
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(db_url)
        
        # Check applied_migrations table
        result = await conn.fetch("""
            SELECT filename FROM applied_migrations ORDER BY applied_at
        """)
        
        print(f"   ✅ Applied migrations: {len(result)}")
        for row in result:
            print(f"      - {row['filename']}")
        
        # Check critical tables
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        
        critical_tables = ['users', 'jobs', 'wallets', 'ledger']
        existing = {row['table_name'] for row in tables}
        
        print(f"\n   📊 Critical tables:")
        for table in critical_tables:
            if table in existing:
                print(f"      ✅ {table}")
            else:
                print(f"      ❌ {table} MISSING")
        
        await conn.close()
        
    except Exception as e:
        print(f"   ❌ Failed to check migrations: {e}")


async def main():
    """Main diagnostic"""
    import json
    
    success = await diagnose_webhook()
    await test_webhook_endpoint()
    await check_migrations()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ DIAGNOSTIC COMPLETE - Check results above")
        print("=" * 70)
        return 0
    else:
        print("❌ DIAGNOSTIC FAILED - Fix errors above")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
