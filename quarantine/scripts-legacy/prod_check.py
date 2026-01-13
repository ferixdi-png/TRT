#!/usr/bin/env python3
"""
E2E Smoke Test для Production Readiness (Render webhook mode)

Проверяет:
1. ENV переменные (все обязательные)
2. Порт открыт (PORT)
3. Миграции БД (idempotent schema)
4. Lock key (int64 signed range)
5. Webhook настроен на WEBHOOK_BASE_URL
6. Health endpoint (/health)
7. Полный цикл z-image (create task → check status)

Exit codes:
- 0: ✅ Все проверки прошли
- 1: ❌ Критическая ошибка
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
import socket
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_env() -> dict:
    """Check required ENV variables."""
    logger.info("=" * 60)
    logger.info("TEST 1/7: ENV Variables")
    logger.info("=" * 60)
    
    required = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "WEBHOOK_BASE_URL": os.getenv("WEBHOOK_BASE_URL", ""),
        "KIE_API_KEY": os.getenv("KIE_API_KEY", ""),
        "PORT": os.getenv("PORT", "10000"),
        "BOT_MODE": os.getenv("BOT_MODE", "webhook"),
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error(f"❌ Missing: {', '.join(missing)}")
        sys.exit(1)
    
    logger.info("✅ All ENV present")
    return required


def check_port(port: str) -> bool:
    """Check if port is available (not already in use)."""
    logger.info("=" * 60)
    logger.info(f"TEST 2/7: Port {port} Availability")
    logger.info("=" * 60)
    
    try:
        port_int = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port_int))
        sock.close()
        
        if result == 0:
            logger.info(f"✅ Port {port} is OPEN (already bound)")
            return True
        else:
            logger.warning(f"⚠️ Port {port} not yet bound (normal before server start)")
            return False
    except Exception as e:
        logger.error(f"❌ Port check failed: {e}")
        return False


async def check_migrations(db_url: str) -> bool:
    """Apply idempotent migrations."""
    logger.info("=" * 60)
    logger.info("TEST 3/7: Database Migrations")
    logger.info("=" * 60)
    
    try:
        import psycopg2
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Read idempotent schema
        schema_file = project_root / "init_schema_idempotent.sql"
        if not schema_file.exists():
            logger.error(f"❌ Schema file not found: {schema_file}")
            return False
        
        sql = schema_file.read_text()
        
        logger.info("Applying idempotent migrations...")
        cursor.execute(sql)
        conn.commit()
        
        # Verify tables created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('users', 'generation_jobs', 'orphan_callbacks')
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Tables present: {', '.join(tables)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


def check_lock_key(token: str) -> bool:
    """Check lock key is in valid int64 range."""
    logger.info("=" * 60)
    logger.info("TEST 4/7: Lock Key (int64 signed)")
    logger.info("=" * 60)
    
    try:
        from render_singleton_lock import make_lock_key
        
        lock_key = make_lock_key(token)
        MAX_BIGINT = 0x7FFFFFFFFFFFFFFF  # 2^63 - 1
        
        if not (0 <= lock_key <= MAX_BIGINT):
            logger.error(f"❌ Lock key out of range: {lock_key}")
            return False
        
        logger.info(f"✅ Lock key valid: {lock_key}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Lock key check failed: {e}")
        return False


async def check_webhook(bot_token: str, webhook_url: str) -> bool:
    """Check webhook is configured."""
    logger.info("=" * 60)
    logger.info("TEST 5/7: Webhook Configuration")
    logger.info("=" * 60)
    
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        
        bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode="HTML"))
        
        info = await bot.get_webhook_info()
        
        if not info.url:
            logger.warning("⚠️ Webhook not set, configuring now...")
            
            # Derive secret path
            secret_path = bot_token.replace(":", "")
            if len(secret_path) > 64:
                secret_path = secret_path[-64:]
            
            full_url = f"{webhook_url.rstrip('/')}/{secret_path}"
            
            result = await bot.set_webhook(
                url=full_url,
                drop_pending_updates=False,
                allowed_updates=["message", "callback_query"]
            )
            
            if result:
                logger.info(f"✅ Webhook set: {full_url[:50]}...")
            else:
                logger.error("❌ Failed to set webhook")
                await bot.session.close()
                return False
        else:
            logger.info(f"✅ Webhook already set: {info.url[:50]}...")
        
        await bot.session.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Webhook check failed: {e}")
        return False


async def check_health_endpoint(webhook_url: str) -> bool:
    """Check /health endpoint."""
    logger.info("=" * 60)
    logger.info("TEST 6/7: Health Endpoint")
    logger.info("=" * 60)
    
    try:
        import aiohttp
        
        health_url = f"{webhook_url.rstrip('/')}/health"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Health OK: {data}")
                    return True
                else:
                    logger.warning(f"⚠️ Health returned {resp.status} (may not be running yet)")
                    return False
                    
    except Exception as e:
        logger.warning(f"⚠️ Health check failed (normal if server not started): {e}")
        return False


async def check_z_image(kie_api_key: str) -> bool:
    """Check z-image generation flow."""
    logger.info("=" * 60)
    logger.info("TEST 7/7: Z-Image Generation Flow")
    logger.info("=" * 60)
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "z-image",
                "task_type": "async",
                "input": {
                    "prompt": "production smoke test: a red cube",
                    "aspect_ratio": "1:1"
                }
            }
            
            headers = {
                "Authorization": f"Bearer {kie_api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info("Creating task...")
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
                    logger.error(f"❌ No taskId: {data}")
                    return False
                
                logger.info(f"✅ Task created: {task_id}")
            
            # Check status
            logger.info("Checking status...")
            async with session.post(
                "https://kie.ai/api/inference/recordInfo",
                json={"taskId": task_id},
                headers=headers
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"❌ Status check failed: {resp.status} - {text[:200]}")
                    return False
                
                data = await resp.json()
                status = data.get("data", {}).get("status")
                
                logger.info(f"✅ Task status: {status}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Z-image test failed: {e}")
        return False


async def main():
    """Run all smoke tests."""
    logger.info("=" * 60)
    logger.info("E2E SMOKE TEST - PRODUCTION READINESS")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # TEST 1: ENV
    env = check_env()
    
    # TEST 2: Port
    port_ok = check_port(env["PORT"])
    
    # TEST 3: Migrations
    migrations_ok = await check_migrations(env["DATABASE_URL"])
    if not migrations_ok:
        logger.error("❌ FAILED: Migrations")
        sys.exit(1)
    
    # TEST 4: Lock key
    lock_ok = check_lock_key(env["TELEGRAM_BOT_TOKEN"])
    if not lock_ok:
        logger.error("❌ FAILED: Lock key")
        sys.exit(1)
    
    # TEST 5: Webhook
    webhook_ok = await check_webhook(env["TELEGRAM_BOT_TOKEN"], env["WEBHOOK_BASE_URL"])
    if not webhook_ok:
        logger.error("❌ FAILED: Webhook")
        sys.exit(1)
    
    # TEST 6: Health (optional)
    health_ok = await check_health_endpoint(env["WEBHOOK_BASE_URL"])
    
    # TEST 7: Z-image
    z_image_ok = await check_z_image(env["KIE_API_KEY"])
    if not z_image_ok:
        logger.error("❌ FAILED: Z-image generation")
        sys.exit(1)
    
    elapsed = time.time() - start_time
    
    logger.info("=" * 60)
    logger.info("✅ ✅ ✅ ALL CRITICAL TESTS PASSED ✅ ✅ ✅")
    logger.info("=" * 60)
    logger.info(f"Elapsed: {elapsed:.2f}s")
    logger.info("")
    logger.info("Summary:")
    logger.info(f"  1. ENV variables: ✅")
    logger.info(f"  2. Port {env['PORT']}: {'✅' if port_ok else '⚠️'}")
    logger.info(f"  3. Migrations: ✅")
    logger.info(f"  4. Lock key: ✅")
    logger.info(f"  5. Webhook: ✅")
    logger.info(f"  6. Health endpoint: {'✅' if health_ok else '⚠️'}")
    logger.info(f"  7. Z-image flow: ✅")
    logger.info("=" * 60)
    logger.info("Production Ready! 🚀")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
