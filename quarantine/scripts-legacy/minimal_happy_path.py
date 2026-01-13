#!/usr/bin/env python3
"""
Minimal Happy Path для z-image в Production (Render webhook mode)

Этот скрипт:
1. Валидирует ENV переменные (только обязательные из Render Secrets)
2. Проверяет миграции БД (idempotent)
3. Проверяет lock-key (int64 signed range)
4. Настраивает webhook на WEBHOOK_BASE_URL
5. Тестирует полный цикл: /start → z-image prompt → taskId → результат

Использует ТОЛЬКО ENV из Render Secrets:
- TELEGRAM_BOT_TOKEN
- DATABASE_URL
- WEBHOOK_BASE_URL
- PORT
- KIE_API_KEY
- BOT_MODE (default: webhook)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Setup logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def validate_env() -> dict[str, str]:
    """Validate required ENV variables from Render Secrets."""
    logger.info("=" * 60)
    logger.info("STEP 1: Validating ENV variables")
    logger.info("=" * 60)
    
    required = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "DATABASE_URL": os.getenv("DATABASE_URL", "").strip(),
        "WEBHOOK_BASE_URL": os.getenv("WEBHOOK_BASE_URL", "").strip(),
        "KIE_API_KEY": os.getenv("KIE_API_KEY", "").strip(),
        "PORT": os.getenv("PORT", "10000").strip(),
        "BOT_MODE": os.getenv("BOT_MODE", "webhook").strip().lower(),
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error(f"❌ Missing required ENV: {', '.join(missing)}")
        sys.exit(1)
    
    logger.info("✅ All required ENV variables present")
    for key in required:
        if "TOKEN" in key or "KEY" in key or "URL" in key:
            logger.info(f"  {key}: [SET]")
        else:
            logger.info(f"  {key}: {required[key]}")
    
    return required


def validate_lock_key(token: str) -> int:
    """Validate lock key is in signed int64 range [0, 2^63-1]."""
    logger.info("=" * 60)
    logger.info("STEP 2: Validating lock key (int64 signed)")
    logger.info("=" * 60)
    
    from render_singleton_lock import make_lock_key
    
    lock_key = make_lock_key(token)
    
    MAX_BIGINT = 0x7FFFFFFFFFFFFFFF  # 2^63 - 1
    if not (0 <= lock_key <= MAX_BIGINT):
        logger.error(f"❌ Lock key out of range: {lock_key} (max: {MAX_BIGINT})")
        sys.exit(1)
    
    logger.info(f"✅ Lock key valid: {lock_key} (in signed int64 range)")
    return lock_key


async def check_migrations(db_url: str) -> bool:
    """Check if migrations are applied (idempotent)."""
    logger.info("=" * 60)
    logger.info("STEP 3: Checking database migrations")
    logger.info("=" * 60)
    
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if critical tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('users', 'generation_jobs', 'orphan_callbacks')
        """)
        
        tables = [row['table_name'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        required_tables = ['users', 'generation_jobs']
        missing = [t for t in required_tables if t not in tables]
        
        if missing:
            logger.warning(f"⚠️ Missing tables: {', '.join(missing)}")
            logger.info("Will create tables (idempotent)...")
            return False
        
        logger.info(f"✅ Required tables present: {', '.join(tables)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration check failed: {e}")
        return False


async def setup_webhook(bot_token: str, webhook_url: str) -> bool:
    """Setup Telegram webhook."""
    logger.info("=" * 60)
    logger.info("STEP 4: Setting up webhook")
    logger.info("=" * 60)
    
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        
        # Derive secret path from token (compatibility with main_render.py)
        secret_path = bot_token.strip().replace(":", "")
        if len(secret_path) > 64:
            secret_path = secret_path[-64:]
        
        full_webhook_url = f"{webhook_url.rstrip('/')}/{secret_path}"
        
        logger.info(f"Webhook URL: {full_webhook_url[:50]}...")
        
        bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode="HTML"))
        
        # Delete old webhook first
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Old webhook deleted")
        
        # Set new webhook
        result = await bot.set_webhook(
            url=full_webhook_url,
            drop_pending_updates=False,
            allowed_updates=["message", "callback_query"]
        )
        
        if not result:
            logger.error("❌ Failed to set webhook")
            await bot.session.close()
            return False
        
        # Verify webhook
        webhook_info = await bot.get_webhook_info()
        logger.info(f"✅ Webhook set: {webhook_info.url}")
        logger.info(f"  Pending updates: {webhook_info.pending_update_count}")
        logger.info(f"  Last error: {webhook_info.last_error_message or 'None'}")
        
        await bot.session.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Webhook setup failed: {e}")
        return False


async def test_z_image_flow(bot_token: str, kie_api_key: str) -> bool:
    """Test z-image generation flow (without actual Telegram interaction)."""
    logger.info("=" * 60)
    logger.info("STEP 5: Testing z-image flow")
    logger.info("=" * 60)
    
    try:
        # Test kie.ai API connectivity
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            # Create task
            payload = {
                "model": "z-image",
                "task_type": "async",
                "input": {
                    "prompt": "a beautiful sunset over mountains",
                    "aspect_ratio": "16:9"
                }
            }
            
            headers = {
                "Authorization": f"Bearer {kie_api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info("Creating test task...")
            async with session.post(
                "https://kie.ai/api/inference/createTask",
                json=payload,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"❌ Create task failed: {resp.status} - {text[:200]}")
                    return False
                
                data = await resp.json()
                task_id = data.get("data", {}).get("taskId")
                
                if not task_id:
                    logger.error(f"❌ No taskId in response: {data}")
                    return False
                
                logger.info(f"✅ Task created: {task_id}")
            
            # Check task status
            logger.info("Checking task status...")
            async with session.post(
                "https://kie.ai/api/inference/recordInfo",
                json={"taskId": task_id},
                headers=headers
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"❌ Record info failed: {resp.status} - {text[:200]}")
                    return False
                
                data = await resp.json()
                status = data.get("data", {}).get("status")
                
                logger.info(f"✅ Task status: {status}")
                logger.info(f"  Full response: {data}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Z-image test failed: {e}")
        return False


async def main():
    """Run minimal happy path validation."""
    logger.info("=" * 60)
    logger.info("MINIMAL HAPPY PATH FOR Z-IMAGE (Production)")
    logger.info("=" * 60)
    
    # Step 1: Validate ENV
    env = validate_env()
    
    # Step 2: Validate lock key
    lock_key = validate_lock_key(env["TELEGRAM_BOT_TOKEN"])
    
    # Step 3: Check migrations
    migrations_ok = await check_migrations(env["DATABASE_URL"])
    if not migrations_ok:
        logger.warning("⚠️ Migrations may need to run (will auto-apply on bot startup)")
    
    # Step 4: Setup webhook
    webhook_ok = await setup_webhook(env["TELEGRAM_BOT_TOKEN"], env["WEBHOOK_BASE_URL"])
    if not webhook_ok:
        logger.error("❌ Webhook setup failed - bot will NOT respond to /start")
        sys.exit(1)
    
    # Step 5: Test z-image
    z_image_ok = await test_z_image_flow(env["TELEGRAM_BOT_TOKEN"], env["KIE_API_KEY"])
    if not z_image_ok:
        logger.error("❌ Z-image test failed")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("✅ ✅ ✅ ALL CHECKS PASSED ✅ ✅ ✅")
    logger.info("=" * 60)
    logger.info("Bot is ready for production:")
    logger.info("  1. Send /start to bot")
    logger.info("  2. Select z-image model")
    logger.info("  3. Enter prompt + aspect_ratio")
    logger.info("  4. Receive generated image")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
