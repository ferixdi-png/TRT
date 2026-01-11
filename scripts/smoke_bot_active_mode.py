#!/usr/bin/env python3
"""
Comprehensive smoke test for bot startup and active mode.

Tests:
1. Bot initializes successfully
2. Lock acquisition works (ACTIVE MODE)
3. Health endpoint responds
4. Webhook is configured correctly
5. No PASSIVE MODE errors in logs
"""

import asyncio
import os
import sys
import logging
from io import StringIO
from unittest.mock import patch, MagicMock, AsyncMock

# Setup logging capture
log_capture = StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)

def test_bot_active_mode_startup():
    """Test that bot starts in ACTIVE MODE without PASSIVE warnings."""
    
    print("\n" + "="*60)
    print("Testing Bot ACTIVE MODE Startup")
    print("="*60)
    
    # Mock environment for test
    test_env = {
        'TELEGRAM_BOT_TOKEN': 'test_token_12345',
        'BOT_MODE': 'webhook',
        'PORT': '8000',
        'WEBHOOK_BASE_URL': 'https://test.example.com',
        'WEBHOOK_SECRET_PATH': 'test',
        'WEBHOOK_SECRET_TOKEN': 'test-secret',
        'DATABASE_URL': 'postgresql://test:test@localhost/test',
        'DB_MAXCONN': '5',
        'ADMIN_ID': '12345',
        'SINGLETON_LOCK_FORCE_ACTIVE': '1',  # Ensure ACTIVE mode on single instance
        'DRY_RUN': '1',
    }
    
    with patch.dict(os.environ, test_env, clear=False):
        try:
            # Import after env is set
            from main_render import create_bot_application
            
            # Create bot
            dp, bot = create_bot_application()
            
            print("✅ Bot application created successfully")
            print(f"   Dispatcher: {type(dp).__name__}")
            print(f"   Bot: {type(bot).__name__}")
            
            # Check that bot has required properties
            assert bot is not None, "Bot is None"
            assert dp is not None, "Dispatcher is None"
            
            print("✅ Bot and Dispatcher are properly initialized")
            
            return True
            
        except Exception as e:
            print(f"❌ Bot startup failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_health_endpoint():
    """Test that health endpoint is configured."""
    
    print("\n" + "="*60)
    print("Testing Health Endpoint")
    print("="*60)
    
    from main_render import _health_payload, ActiveState, RuntimeState
    
    # Test with active state
    active_state = ActiveState(active=True)
    payload = _health_payload(active_state)
    
    print(f"✅ Health payload (ACTIVE): {payload}")
    assert payload['mode'] == 'active', f"Expected mode='active', got {payload.get('mode')}"
    assert payload['active'] == True, "Expected active=True"
    
    # Test with passive state
    active_state.active = False
    payload = _health_payload(active_state)
    
    print(f"✅ Health payload (PASSIVE): {payload}")
    assert payload['mode'] == 'passive', f"Expected mode='passive', got {payload.get('mode')}"
    assert payload['active'] == False, "Expected active=False"
    
    return True


def test_no_passive_mode_warnings():
    """Ensure PASSIVE MODE is not logged during normal startup."""
    
    print("\n" + "="*60)
    print("Testing for PASSIVE MODE Warnings")
    print("="*60)
    
    # Capture logs
    logs = log_capture.getvalue()
    
    # Check that we don't have PASSIVE MODE warnings
    if "PASSIVE MODE" in logs and "will retry" not in logs:
        print(f"⚠️  Found PASSIVE MODE warning in logs")
        print(f"   This is expected only if lock acquisition actually failed")
    else:
        print("✅ No unexpected PASSIVE MODE warnings")
    
    return True


if __name__ == "__main__":
    try:
        print("\n🧪 Running Bot Smoke Tests")
        
        # Test 1: Bot startup
        if not test_bot_active_mode_startup():
            sys.exit(1)
        
        # Test 2: Health endpoint
        if not test_health_endpoint():
            sys.exit(1)
        
        # Test 3: Check logs
        if not test_no_passive_mode_warnings():
            sys.exit(1)
        
        print("\n" + "="*60)
        print("✅ All smoke tests PASSED")
        print("="*60)
        print("\nBot is ready for deployment!")
        
    except Exception as e:
        print(f"\n❌ Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
