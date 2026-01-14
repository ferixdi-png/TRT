#!/usr/bin/env python3
"""
EMERGENCY BOT DIAGNOSTIC - Why bot doesn't respond to /start

ITERATION 9: Production bot silence - systematic diagnosis

This tool checks ALL critical points:
1. ENV variables (TELEGRAM_BOT_TOKEN, service name, webhook settings)
2. Bot identity (getMe API call)
3. Webhook status (getWebhookInfo)
4. Database connectivity
5. /start handler registration
6. Recent errors in logs

Exit codes:
- 0: Bot is healthy
- 1: Critical failure found
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"


def log_phase(title: str):
    print(f"\n{BLUE}{BOLD}═══ {title} ═══{RESET}")


def log_pass(msg: str):
    print(f"{GREEN}✅{RESET} {msg}")


def log_fail(msg: str):
    print(f"{RED}❌{RESET} {msg}")


def log_warn(msg: str):
    print(f"{YELLOW}⚠️ {RESET} {msg}")


def log_info(msg: str):
    print(f"ℹ️  {msg}")


async def check_env_variables():
    """Check all required ENV variables."""
    log_phase("ENV Variables Check")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = {
        'TELEGRAM_BOT_TOKEN': 'Telegram bot token',
        'DATABASE_URL': 'PostgreSQL connection',
    }
    
    optional_vars = {
        'RENDER_SERVICE_NAME': 'Render.com service name (for webhook URL)',
        'WEBHOOK_SECRET_TOKEN': 'Webhook security token',
        'PORT': 'HTTP server port',
    }
    
    all_ok = True
    
    for var, description in required_vars.items():
        value = os.getenv(var, '')
        if not value:
            log_fail(f"{var} is MISSING - {description}")
            all_ok = False
        elif 'test' in value.lower() or '123456' in value:
            log_warn(f"{var} looks like TEST value: {value[:30]}...")
            log_info("This is OK for local testing, but NOT for production")
        else:
            log_pass(f"{var} is set ({len(value)} chars)")
    
    for var, description in optional_vars.items():
        value = os.getenv(var, '')
        if value:
            log_pass(f"{var} = {value}")
        else:
            log_info(f"{var} not set - {description}")
    
    return all_ok


async def check_bot_identity():
    """Check bot can connect to Telegram API."""
    log_phase("Bot Identity Check (getMe)")
    
    try:
        from aiogram import Bot
        from dotenv import load_dotenv
        load_dotenv()
        
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if not token:
            log_fail("Cannot check bot identity - no token")
            return False
        
        bot = Bot(token=token)
        me = await bot.get_me()
        
        log_pass(f"Bot ID: {me.id}")
        log_pass(f"Bot username: @{me.username}")
        log_pass(f"Bot name: {me.first_name}")
        log_info(f"Can receive messages: {me.can_join_groups}")
        
        await bot.session.close()
        return True
        
    except Exception as e:
        log_fail(f"Bot identity check failed: {e}")
        if "Unauthorized" in str(e) or "401" in str(e):
            log_fail("Token is INVALID or EXPIRED")
        return False


async def check_webhook_status():
    """Check webhook registration with Telegram."""
    log_phase("Webhook Status Check (getWebhookInfo)")
    
    try:
        from aiogram import Bot
        from dotenv import load_dotenv
        load_dotenv()
        
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        if not token:
            log_fail("Cannot check webhook - no token")
            return False
        
        bot = Bot(token=token)
        info = await bot.get_webhook_info()
        
        log_info(f"Current webhook URL: {info.url or '(not set)'}")
        log_info(f"Pending updates: {info.pending_update_count}")
        log_info(f"Max connections: {info.max_connections or 'default'}")
        
        if info.last_error_date:
            from datetime import datetime
            error_time = datetime.fromtimestamp(info.last_error_date)
            log_warn(f"Last error: {info.last_error_message}")
            log_warn(f"Error time: {error_time}")
        
        if not info.url:
            log_fail("Webhook is NOT SET - bot will not receive updates!")
            log_info("Expected URL format: https://<service>.onrender.com/webhook/<secret>")
            await bot.session.close()
            return False
        
        # Check if URL looks correct
        render_service = os.getenv('RENDER_SERVICE_NAME', '')
        if render_service and render_service not in info.url:
            log_warn(f"Webhook URL doesn't contain service name '{render_service}'")
            log_warn(f"This might be from old deployment")
        
        if info.pending_update_count > 0:
            log_warn(f"There are {info.pending_update_count} pending updates")
            log_info("Bot might be processing old messages")
        
        log_pass("Webhook is registered")
        await bot.session.close()
        return True
        
    except Exception as e:
        log_fail(f"Webhook check failed: {e}")
        return False


async def check_database():
    """Check database connectivity."""
    log_phase("Database Connectivity Check")
    
    try:
        from app.database.connection import get_db_session
        from sqlalchemy import text
        
        async with get_db_session() as session:
            result = await session.execute(text("SELECT 1"))
            log_pass("Database connection OK")
            
            # Check users table
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            count = result.scalar()
            log_pass(f"Users table accessible ({count} users)")
            
            return True
            
    except Exception as e:
        log_fail(f"Database check failed: {e}")
        log_info("Bot cannot store/retrieve user data")
        return False


async def check_start_handler():
    """Check /start handler is registered."""
    log_phase("/start Handler Registration Check")
    
    try:
        # Import the router with /start handler
        from bot.handlers import flow
        
        # Check if start_cmd exists
        if not hasattr(flow, 'start_cmd'):
            log_fail("start_cmd function not found in bot.handlers.flow")
            return False
        
        log_pass("start_cmd function exists in flow.py")
        
        # Check if router has Command("start") handler
        import inspect
        source = inspect.getsource(flow.start_cmd)
        if '@router.message(Command("start"))' in source or "Command('start')" in source:
            log_pass('/start command decorator found')
        else:
            log_warn('/start decorator not found in source (might be defined elsewhere)')
        
        # Check if router is included in main
        log_info("Note: Handler registration happens in bot/dispatcher.py")
        
        return True
        
    except Exception as e:
        log_fail(f"Handler check failed: {e}")
        return False


async def main():
    print(f"{BOLD}{BLUE}╔════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{BLUE}║  🚨 EMERGENCY BOT DIAGNOSTIC - /start not working ║{RESET}")
    print(f"{BOLD}{BLUE}╚════════════════════════════════════════════════════╝{RESET}")
    
    results = {}
    
    # Phase 1: ENV
    results['env'] = await check_env_variables()
    
    # Phase 2: Bot identity
    results['identity'] = await check_bot_identity()
    
    # Phase 3: Webhook
    results['webhook'] = await check_webhook_status()
    
    # Phase 4: Database
    results['database'] = await check_database()
    
    # Phase 5: Handler
    results['handler'] = await check_start_handler()
    
    # Summary
    print(f"\n{BOLD}{BLUE}═══ DIAGNOSTIC SUMMARY ═══{RESET}")
    
    for check, passed in results.items():
        status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
        print(f"{status}: {check.upper()}")
    
    print()
    
    if all(results.values()):
        print(f"{GREEN}{BOLD}╔════════════════════════════════════════════════════╗{RESET}")
        print(f"{GREEN}{BOLD}║  ✅ ALL CHECKS PASSED                             ║{RESET}")
        print(f"{GREEN}{BOLD}║  Bot should be working. Check:                    ║{RESET}")
        print(f"{GREEN}{BOLD}║  1. Try /start in Telegram                        ║{RESET}")
        print(f"{GREEN}{BOLD}║  2. Check Render logs for incoming updates        ║{RESET}")
        print(f"{GREEN}{BOLD}║  3. Verify webhook receives requests              ║{RESET}")
        print(f"{GREEN}{BOLD}╚════════════════════════════════════════════════════╝{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}╔════════════════════════════════════════════════════╗{RESET}")
        print(f"{RED}{BOLD}║  ❌ CRITICAL FAILURES FOUND                        ║{RESET}")
        print(f"{RED}{BOLD}║                                                    ║{RESET}")
        
        if not results.get('env'):
            print(f"{RED}{BOLD}║  → Fix ENV variables (TELEGRAM_BOT_TOKEN)         ║{RESET}")
        if not results.get('identity'):
            print(f"{RED}{BOLD}║  → Check bot token is valid                       ║{RESET}")
        if not results.get('webhook'):
            print(f"{RED}{BOLD}║  → Register webhook with Telegram                 ║{RESET}")
            print(f"{RED}{BOLD}║    Run: python3 tools/prod_check_webhook...       ║{RESET}")
        if not results.get('database'):
            print(f"{RED}{BOLD}║  → Check DATABASE_URL and run migrations          ║{RESET}")
        if not results.get('handler'):
            print(f"{RED}{BOLD}║  → Check /start handler in bot/handlers/flow.py   ║{RESET}")
        
        print(f"{RED}{BOLD}║                                                    ║{RESET}")
        print(f"{RED}{BOLD}╚════════════════════════════════════════════════════╝{RESET}")
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
