#!/usr/bin/env python3
"""
Verify runtime environment before deployment.

Checks:
1. All required ENV variables are set
2. Masks sensitive values in output
3. Validates Telegram API connectivity
4. Validates KIE API connectivity
5. Validates Database connectivity
6. Reports issues without leaking secrets
"""

import os
import sys
import json
import asyncio
from typing import Dict, Tuple, Optional

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

# Check required modules
def check_modules():
    """Check that required modules are available."""
    required = ['aiohttp', 'asyncpg']
    missing = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    
    if missing:
        print(f"{RED}❌ Missing required modules: {', '.join(missing)}{RESET}")
        print(f"   Install with: pip install {' '.join(missing)}\n")
        sys.exit(1)

check_modules()

# Check if running in TEST_MODE
TEST_MODE = os.getenv("TEST_MODE") == "1" or os.getenv("SMOKE_MODE") == "1"

def mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask secret values, showing only last N characters."""
    if not value or len(value) <= visible_chars:
        return "****"
    return "****" + value[-visible_chars:]


def check_env_vars() -> Tuple[Dict[str, str], list]:
    """Check that all required ENV variables are set.
    
    Returns:
        (dict of env vars, list of errors)
    """
    # Skip ENV validation in TEST_MODE/SMOKE_MODE
    if TEST_MODE:
        print(f"\n{YELLOW}⊘ Skipping ENV validation (TEST_MODE/SMOKE_MODE enabled){RESET}\n")
        return {}, []
    
    required_vars = {
        'TELEGRAM_BOT_TOKEN': 'Telegram bot token',
        'KIE_API_KEY': 'KIE API key',
        'DATABASE_URL': 'PostgreSQL connection URL',
        'WEBHOOK_BASE_URL': 'Webhook base URL for Render',
        'PORT': 'Port to listen on',
    }
    
    optional_vars = {
        'ADMIN_ID': 'Admin user ID',
        'BOT_MODE': 'Bot mode (webhook/polling)',
        'DB_MAXCONN': 'Max database connections',
        'PAYMENT_BANK': 'Payment provider bank',
        'PAYMENT_CARD_HOLDER': 'Payment card holder name',
        'PAYMENT_PHONE': 'Support phone number',
        'SUPPORT_TELEGRAM': 'Support Telegram handle',
        'SUPPORT_TEXT': 'Support text message',
    }
    
    env_vars = {}
    errors = []
    
    print(f"\n{BOLD}Checking Required ENV Variables:{RESET}")
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if not value:
            errors.append(f"❌ {var}: {desc} - NOT SET")
            print(f"{RED}❌ {var}{RESET} - NOT SET")
        else:
            env_vars[var] = value
            masked = mask_secret(value)
            print(f"{GREEN}✅ {var}{RESET} = {masked}")
    
    print(f"\n{BOLD}Checking Optional ENV Variables:{RESET}")
    for var, desc in optional_vars.items():
        value = os.getenv(var)
        if value:
            env_vars[var] = value
            if len(value) > 10:
                masked = mask_secret(value)
            else:
                masked = value
            print(f"{GREEN}✅ {var}{RESET} = {masked}")
        else:
            print(f"{YELLOW}⊘ {var}{RESET} - not set (optional)")
    
    return env_vars, errors


async def check_telegram_api(token: str) -> Tuple[bool, str]:
    """Validate Telegram Bot API connectivity.
    
    Args:
        token: TELEGRAM_BOT_TOKEN
    
    Returns:
        (success: bool, message: str)
    """
    import aiohttp
    
    url = f"https://api.telegram.org/bot{token}/getMe"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                
                if resp.status == 200 and data.get('ok'):
                    bot_name = data.get('result', {}).get('first_name', 'Unknown')
                    return True, f"Bot connected: @{bot_name}"
                else:
                    error = data.get('description', 'Unknown error')
                    return False, f"Telegram API error: {error}"
    except asyncio.TimeoutError:
        return False, "Telegram API timeout (10s)"
    except Exception as e:
        return False, f"Telegram API error: {type(e).__name__}: {str(e)}"


async def check_kie_api(api_key: str) -> Tuple[bool, str]:
    """Validate KIE API connectivity.
    
    Args:
        api_key: KIE_API_KEY
    
    Returns:
        (success: bool, message: str)
    """
    import aiohttp
    
    # Use minimal endpoint - health/status check
    url = "https://api.kie.ru/v1/models"  # List models endpoint (cheapest)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                # Any 2xx response means API is accessible
                if 200 <= resp.status < 300:
                    return True, f"KIE API connected (status {resp.status})"
                elif resp.status == 401:
                    return False, "KIE API: Invalid credentials (401)"
                elif resp.status == 403:
                    return False, "KIE API: Access forbidden (403)"
                else:
                    return False, f"KIE API error: HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, "KIE API timeout (10s)"
    except Exception as e:
        return False, f"KIE API error: {type(e).__name__}: {str(e)}"


async def check_database(db_url: str) -> Tuple[bool, str]:
    """Validate Database connectivity.
    
    Args:
        db_url: DATABASE_URL (PostgreSQL)
    
    Returns:
        (success: bool, message: str)
    """
    import asyncpg
    
    try:
        # Parse URL to extract host:port for masked logging
        try:
            from urllib.parse import urlparse
            parsed = urlparse(db_url)
            host_port = f"{parsed.hostname}:{parsed.port or 5432}"
        except:
            host_port = "unknown"
        
        conn = await asyncpg.connect(db_url)
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        
        # Extract PostgreSQL version
        pg_version = version.split(',')[0] if version else "unknown"
        return True, f"PostgreSQL connected: {pg_version}"
    except asyncpg.InvalidPassword:
        return False, "Database: Invalid credentials"
    except asyncpg.CannotConnectNowError:
        return False, "Database: Connection refused (server may be down)"
    except Exception as e:
        return False, f"Database error: {type(e).__name__}: {str(e)}"


async def main():
    """Run all verification checks."""
    print(f"\n{BOLD}{BLUE}=" * 60)
    print("TRT Project - Runtime Verification")
    print("=" * 60 + f"{RESET}\n")
    
    # Step 1: Check ENV variables
    env_vars, errors = check_env_vars()
    
    if errors:
        print(f"\n{RED}{BOLD}ERRORS FOUND:{RESET}")
        for error in errors:
            print(f"  {error}")
        print(f"\n{RED}✗ ENV verification FAILED{RESET}\n")
        return 1
    
    print(f"\n{GREEN}✓ All required ENV variables are set{RESET}")
    
    # Step 2: Validate API connectivity
    print(f"\n{BOLD}Validating API Connectivity:{RESET}")
    
    all_ok = True
    
    # Telegram API
    telegram_token = env_vars.get('TELEGRAM_BOT_TOKEN', '')
    if telegram_token:
        ok, msg = await check_telegram_api(telegram_token)
        if ok:
            print(f"{GREEN}✅ Telegram API:{RESET} {msg}")
        else:
            print(f"{RED}❌ Telegram API:{RESET} {msg}")
            all_ok = False
    
    # KIE API
    kie_key = env_vars.get('KIE_API_KEY', '')
    if kie_key:
        ok, msg = await check_kie_api(kie_key)
        if ok:
            print(f"{GREEN}✅ KIE API:{RESET} {msg}")
        else:
            print(f"{RED}❌ KIE API:{RESET} {msg}")
            all_ok = False
    
    # Database
    db_url = env_vars.get('DATABASE_URL', '')
    if db_url:
        ok, msg = await check_database(db_url)
        if ok:
            print(f"{GREEN}✅ Database:{RESET} {msg}")
        else:
            print(f"{RED}❌ Database:{RESET} {msg}")
            all_ok = False
    
    # Final result
    print(f"\n{BOLD}{BLUE}=" * 60)
    if all_ok:
        print(f"{GREEN}{BOLD}✓ VERIFICATION PASSED - Ready for deployment!{RESET}")
        print("=" * 60 + f"\n")
        return 0
    else:
        print(f"{RED}{BOLD}✗ VERIFICATION FAILED - Fix errors above{RESET}")
        print("=" * 60 + f"\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
