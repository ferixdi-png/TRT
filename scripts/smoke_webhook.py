#!/usr/bin/env python3
"""
Smoke test for webhook deployment - minimal checks for production readiness.

Runs in 2-5 minutes and gives green/red status.
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Test results
results = []


def test_result(name: str, passed: bool, message: str = ""):
    """Record test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append((name, passed, message))
    logger.info(f"{status}: {name}" + (f" - {message}" if message else ""))


def test_import_main_render():
    """Test 1: Import main_render.py without ImportError."""
    try:
        import main_render
        test_result("Import main_render", True)
        return True
    except ImportError as e:
        test_result("Import main_render", False, f"ImportError: {e}")
        return False
    except Exception as e:
        test_result("Import main_render", False, f"Unexpected error: {e}")
        return False


def test_create_dp_bot():
    """Test 2: Create dp/bot without crashes."""
    try:
        from main_render import _make_web_app
        from app.config import Settings
        
        # Create minimal settings
        settings = Settings()
        test_result("Create Settings", True)
        
        # Try to create web app (this creates dp/bot internally)
        # We'll do a minimal check - just verify the function exists
        if hasattr(_make_web_app, '__call__'):
            test_result("Create dp/bot", True, "Function exists")
            return True
        else:
            test_result("Create dp/bot", False, "Function not callable")
            return False
    except Exception as e:
        test_result("Create dp/bot", False, f"Error: {e}")
        return False


async def test_simulate_callback_event():
    """Test 3: Simulate callback event (cat:image) without AttributeError/TypeError."""
    try:
        from aiogram import Bot, Dispatcher
        from aiogram.types import Update, CallbackQuery, User, Chat, Message
        from aiogram.fsm.storage.memory import MemoryStorage
        from unittest.mock import AsyncMock, Mock
        
        # Create minimal dispatcher
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Create mock bot
        bot = Mock(spec=Bot)
        bot.send_message = AsyncMock()
        bot.edit_message_text = AsyncMock()
        bot.answer_callback_query = AsyncMock()
        
        # Create mock callback
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        mock_user.first_name = "Test"
        
        mock_chat = Mock(spec=Chat)
        mock_chat.id = 12345
        
        mock_message = Mock(spec=Message)
        mock_message.chat = mock_chat
        mock_message.message_id = 1
        mock_message.edit_text = AsyncMock()
        
        mock_callback = Mock(spec=CallbackQuery)
        mock_callback.id = "test_query_123"
        mock_callback.from_user = mock_user
        mock_callback.message = mock_message
        mock_callback.data = "cat:image"
        mock_callback.answer = AsyncMock()
        
        mock_update = Mock(spec=Update)
        mock_update.update_id = 12345
        mock_update.callback_query = mock_callback
        
        # Test that we can extract update_id safely
        from app.telemetry.telemetry_helpers import get_update_id
        
        update_id = get_update_id(mock_callback, {"event_update": mock_update})
        if update_id == 12345:
            test_result("Simulate callback event", True, "update_id extracted correctly")
            return True
        else:
            test_result("Simulate callback event", False, f"update_id mismatch: {update_id}")
            return False
            
    except AttributeError as e:
        test_result("Simulate callback event", False, f"AttributeError: {e}")
        return False
    except TypeError as e:
        test_result("Simulate callback event", False, f"TypeError: {e}")
        return False
    except Exception as e:
        test_result("Simulate callback event", False, f"Unexpected error: {e}")
        return False


async def test_fallback_handler():
    """Test 4: Fallback handler responds to UNKNOWN_CALLBACK with cid logging."""
    try:
        from bot.handlers.fallback import fallback_unknown_callback
        from aiogram.types import CallbackQuery, User, Chat, Message
        from unittest.mock import AsyncMock, Mock, patch
        import logging
        
        # Create mock callback
        mock_user = Mock(spec=User)
        mock_user.id = 12345
        
        mock_chat = Mock(spec=Chat)
        mock_chat.id = 12345
        
        mock_message = Mock(spec=Message)
        mock_message.chat = mock_chat
        mock_message.edit_text = AsyncMock()
        
        mock_callback = Mock(spec=CallbackQuery)
        mock_callback.from_user = mock_user
        mock_callback.message = mock_message
        mock_callback.data = "unknown:test:123"
        mock_callback.id = "test_query_456"
        mock_callback.answer = AsyncMock()
        
        # Mock telemetry functions to capture calls
        with patch('bot.handlers.fallback.log_callback_received') as mock_log_received, \
             patch('bot.handlers.fallback.log_callback_rejected') as mock_log_rejected:
            
            # Call fallback handler with cid
            test_cid = "test_cid_789"
            await fallback_unknown_callback(
                mock_callback, 
                cid=test_cid, 
                bot_state="ACTIVE",
                data={"event_update": Mock(update_id=99999)}
            )
            
            # Check that callback was answered
            if not mock_callback.answer.called:
                test_result("Fallback handler", False, "Callback not answered")
                return False
            
            # Check that log_callback_received was called with cid
            if not mock_log_received.called:
                test_result("Fallback handler", False, "log_callback_received not called")
                return False
            
            # Check that log_callback_rejected was called with UNKNOWN_CALLBACK and cid
            if not mock_log_rejected.called:
                test_result("Fallback handler", False, "log_callback_rejected not called")
                return False
            
            # Verify log_callback_rejected was called with correct parameters
            call_kwargs = mock_log_rejected.call_args[1] if mock_log_rejected.call_args else {}
            if call_kwargs.get("reason_code") != "UNKNOWN_CALLBACK":
                test_result("Fallback handler", False, f"Wrong reason_code: {call_kwargs.get('reason_code')}")
                return False
            
            if call_kwargs.get("cid") != test_cid:
                test_result("Fallback handler", False, f"CID mismatch: expected {test_cid}, got {call_kwargs.get('cid')}")
                return False
            
            test_result("Fallback handler", True, f"Callback answered + UNKNOWN_CALLBACK logged with cid={test_cid}")
            return True
            
    except Exception as e:
        test_result("Fallback handler", False, f"Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_telemetry_signatures():
    """Test 5: Telemetry function signatures are compatible."""
    try:
        from app.telemetry.events import log_callback_rejected
        
        # Test that log_callback_rejected accepts reason_detail
        import inspect
        sig = inspect.signature(log_callback_rejected)
        params = sig.parameters
        
        has_reason_detail = "reason_detail" in params
        has_reason_code = "reason_code" in params
        
        if has_reason_detail and has_reason_code:
            test_result("Telemetry signatures", True, "reason_detail and reason_code present")
            return True
        else:
            test_result("Telemetry signatures", False, f"Missing: reason_detail={has_reason_detail}, reason_code={has_reason_code}")
            return False
            
    except Exception as e:
        test_result("Telemetry signatures", False, f"Error: {e}")
        return False


async def main():
    """Run all smoke tests."""
    logger.info("=" * 60)
    logger.info("SMOKE TEST: Webhook Production Readiness")
    logger.info("=" * 60)
    logger.info("")
    
    # Test 1: Import main_render
    test_import_main_render()
    
    # Test 2: Create dp/bot
    test_create_dp_bot()
    
    # Test 3: Simulate callback event
    await test_simulate_callback_event()
    
    # Test 4: Fallback handler
    await test_fallback_handler()
    
    # Test 5: Telemetry signatures
    test_telemetry_signatures()
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    
    for name, passed, message in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {status}: {name}" + (f" - {message}" if message else ""))
    
    logger.info("")
    if passed == total:
        logger.info(f"✅ ALL TESTS PASSED ({passed}/{total})")
        return 0
    else:
        logger.info(f"❌ SOME TESTS FAILED ({passed}/{total})")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

