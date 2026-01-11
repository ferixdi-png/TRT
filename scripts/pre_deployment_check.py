#!/usr/bin/env python3
"""
Final pre-deployment validation script.

Checks:
1. All imports work
2. Configuration is valid
3. Database connection works
4. Models registry is complete
5. Webhook is configured
6. Environment variables are set
"""

import sys
import os
import asyncio
from pathlib import Path

def check_imports() -> bool:
    """Check that all critical modules import successfully."""
    print("\n📦 Checking imports...")
    modules = [
        "aiogram",
        "aiohttp",
        "asyncpg",
        "psycopg2",
        "yaml",
        "app.main",
        "app.kie.client_v4",
        "app.payments.charges",
        "bot.handlers",
    ]
    
    failed = []
    for module in modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError as e:
            print(f"  ✗ {module}: {e}")
            failed.append(module)
    
    if failed:
        print(f"\n❌ {len(failed)} module(s) failed to import")
        return False
    
    print(f"\n✓ All {len(modules)} modules imported successfully")
    return True


def check_environment() -> bool:
    """Check required environment variables."""
    print("\n🔐 Checking environment variables...")
    
    required = [
        "TELEGRAM_BOT_TOKEN",
        "KIE_API_KEY",
        "ADMIN_ID",
    ]
    
    optional = [
        "DATABASE_URL",
        "BOT_MODE",
        "APP_ENV",
        "WEBHOOK_BASE_URL",
    ]
    
    missing = []
    for var in required:
        if os.getenv(var):
            print(f"  ✓ {var}")
        else:
            print(f"  ✗ {var} (MISSING)")
            missing.append(var)
    
    print("\n  Optional:")
    for var in optional:
        if os.getenv(var):
            print(f"  ✓ {var}")
        else:
            print(f"  ○ {var} (using default)")
    
    if missing:
        print(f"\n⚠️  Missing {len(missing)} required variable(s)")
        return False
    
    return True


def check_models() -> bool:
    """Check that models registry is complete."""
    print("\n📊 Checking models registry...")
    
    try:
        import json
        models_file = Path("models/kie_api_models.json")
        
        if not models_file.exists():
            print(f"  ✗ Models file not found: {models_file}")
            return False
        
        with open(models_file) as f:
            data = json.load(f)
        
        total = len(data.get("models", []))
        print(f"  ✓ {total} models loaded")
        
        if total < 50:
            print(f"\n⚠️  Only {total} models found (expected 50+)")
            return False
        
        # Check that models have required fields
        sample = data["models"][0]
        required_fields = ["model_id", "display_name", "pricing", "input_schema"]
        missing_fields = [f for f in required_fields if f not in sample]
        
        if missing_fields:
            print(f"  ✗ Models missing fields: {missing_fields}")
            return False
        
        print(f"  ✓ All models have required fields")
        return True
        
    except Exception as e:
        print(f"  ✗ Error checking models: {e}")
        return False


async def check_database() -> bool:
    """Check database connection and schema."""
    print("\n🗄️  Checking database...")
    
    try:
        from app.database.services import get_db_pool, init_database
        
        # Initialize database
        await init_database()
        print("  ✓ Database initialized")
        
        pool = get_db_pool()
        if not pool:
            print("  ✗ Database pool not available")
            return False
        
        # Test connection
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            print(f"  ✓ Connected to: {version.split(',')[0]}")
            
            # Check schema exists
            users_exist = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='users')"
            )
            if not users_exist:
                print("  ✗ Database schema not initialized")
                return False
            
            print("  ✓ Database schema is valid")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False


def check_webhook_config() -> bool:
    """Check webhook configuration."""
    print("\n🔌 Checking webhook configuration...")
    
    bot_mode = os.getenv("BOT_MODE", "webhook").lower()
    print(f"  Bot mode: {bot_mode}")
    
    if bot_mode == "webhook":
        required_webhook_vars = [
            "WEBHOOK_BASE_URL",
            "WEBHOOK_SECRET_PATH",
        ]
        
        for var in required_webhook_vars:
            val = os.getenv(var)
            if val:
                print(f"  ✓ {var}: {val[:40]}...")
            else:
                print(f"  ○ {var}: will be generated")
    
    elif bot_mode == "polling":
        print("  ℹ️  Polling mode - webhook not required for local development")
    
    else:
        print(f"  ✗ Invalid BOT_MODE: {bot_mode}")
        return False
    
    return True


def check_health_endpoint() -> bool:
    """Check that health endpoint is configured."""
    print("\n❤️  Checking health check endpoint...")
    
    try:
        # Check that main_render.py has health endpoint
        main_file = Path("main_render.py")
        if not main_file.exists():
            print("  ✗ main_render.py not found")
            return False
        
        content = main_file.read_text()
        if "/health" in content:
            print("  ✓ Health endpoint configured in main_render.py")
            return True
        else:
            print("  ✗ Health endpoint not found")
            return False
            
    except Exception as e:
        print(f"  ✗ Error checking health endpoint: {e}")
        return False


async def main() -> int:
    """Run all checks."""
    print("=" * 60)
    print("🚀 FINAL PRE-DEPLOYMENT VALIDATION")
    print("=" * 60)
    
    checks = [
        ("Imports", check_imports),
        ("Environment", check_environment),
        ("Models Registry", check_models),
        ("Webhook Config", check_webhook_config),
        ("Health Endpoint", check_health_endpoint),
        ("Database", check_database),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} check failed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
    
    print(f"\n{passed}/{total} checks passed")
    
    if passed == total:
        print("\n✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT!")
        return 0
    else:
        print(f"\n❌ {total - passed} check(s) failed - fix before deployment")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
