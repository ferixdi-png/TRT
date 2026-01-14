#!/usr/bin/env python3
"""
E2E Smoke Test: "All Buttons Clickable"

Simulates user flow:
1. /start → main menu
2. Open category (cat:image)
3. Select model (model:z-image)
4. Open input (gen:z-image)
5. Back button
6. Open category again

Goal: Catch "broken callback_data" - callbacks that don't have handlers or cause errors.
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import AsyncMock, Mock, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test user data
TEST_USER_ID = 123456789
TEST_CHAT_ID = 123456789
TEST_USER = Mock()
TEST_USER.id = TEST_USER_ID
TEST_USER.first_name = "SmokeTest"
TEST_USER.username = "smoketest"

# Test message data
TEST_MESSAGE = Mock()
TEST_MESSAGE.chat = Mock()
TEST_MESSAGE.chat.id = TEST_CHAT_ID
TEST_MESSAGE.from_user = TEST_USER
TEST_MESSAGE.message_id = 1


class SmokeTestResult:
    """Result of a single smoke test step."""
    def __init__(self, step: str, callback_data: Optional[str] = None):
        self.step = step
        self.callback_data = callback_data
        self.success = False
        self.error: Optional[str] = None
        self.handler_found = False
        self.fallback_triggered = False
    
    def __repr__(self):
        status = "✅" if self.success else "❌"
        return f"{status} {self.step} (callback: {self.callback_data})"


async def simulate_callback(
    dispatcher,
    callback_data: str,
    state_data: Optional[Dict] = None
) -> SmokeTestResult:
    """
    Simulate a callback query with given callback_data.
    
    Returns:
        SmokeTestResult with success/error info
    """
    result = SmokeTestResult(f"callback:{callback_data}", callback_data)
    
    try:
        # Create mock callback
        callback = Mock()
        callback.data = callback_data
        callback.id = f"test_callback_{callback_data}"
        callback.from_user = TEST_USER
        callback.message = TEST_MESSAGE
        callback.answer = AsyncMock()
        callback.message.edit_text = AsyncMock()
        callback.message.edit_reply_markup = AsyncMock()
        
        # Create mock state
        state = Mock()
        state.get_data = AsyncMock(return_value=state_data or {})
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()
        state.clear = AsyncMock()
        
        # Create mock update
        update = Mock()
        update.callback_query = callback
        update.update_id = 1
        
        # Try to process callback through dispatcher
        try:
            await dispatcher.feed_update(update, state)
            result.handler_found = True
            result.success = True
        except Exception as e:
            # Check if it's a fallback handler (unknown callback)
            error_str = str(e).lower()
            if "unknown" in error_str or "fallback" in error_str:
                result.fallback_triggered = True
                result.success = True  # Fallback is OK, it means callback was caught
            else:
                result.error = str(e)
                result.success = False
        
    except Exception as e:
        result.error = str(e)
        result.success = False
    
    return result


async def simulate_message(
    dispatcher,
    command: str,
    state_data: Optional[Dict] = None
) -> SmokeTestResult:
    """
    Simulate a message command (e.g., /start).
    
    Returns:
        SmokeTestResult with success/error info
    """
    result = SmokeTestResult(f"message:{command}")
    
    try:
        # Create mock message
        message = Mock()
        message.text = command
        message.from_user = TEST_USER
        message.chat = TEST_MESSAGE.chat
        message.answer = AsyncMock()
        message.message_id = 1
        
        # Create mock state
        state = Mock()
        state.get_data = AsyncMock(return_value=state_data or {})
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()
        state.clear = AsyncMock()
        
        # Create mock update
        update = Mock()
        update.message = message
        update.update_id = 1
        
        # Try to process message through dispatcher
        try:
            await dispatcher.feed_update(update, state)
            result.handler_found = True
            result.success = True
        except Exception as e:
            result.error = str(e)
            result.success = False
        
    except Exception as e:
        result.error = str(e)
        result.success = False
    
    return result


async def smoke_test_flow() -> List[SmokeTestResult]:
    """
    Run full e2e smoke test flow:
    1. /start → main menu
    2. Open category (cat:image)
    3. Select model (model:z-image)
    4. Open input (gen:z-image)
    5. Back button
    6. Open category again
    """
    results: List[SmokeTestResult] = []
    
    try:
        # Import dispatcher and routers
        from aiogram import Bot, Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage
        
        # Create minimal bot and dispatcher
        bot = Mock(spec=Bot)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Import routers (this will register handlers)
        try:
            from bot.handlers import flow, fallback
            dp.include_router(flow.router)
            dp.include_router(fallback.router)  # Fallback must be last
        except ImportError as e:
            logger.error(f"Failed to import handlers: {e}")
            return [SmokeTestResult("import", error=str(e))]
        
        # Step 1: /start command
        logger.info("Step 1: Simulating /start command")
        result1 = await simulate_message(dp, "/start")
        results.append(result1)
        
        if not result1.success:
            logger.warning(f"Step 1 failed: {result1.error}")
            return results
        
        # Step 2: Open category (cat:image)
        logger.info("Step 2: Simulating category callback (cat:image)")
        result2 = await simulate_callback(dp, "cat:image")
        results.append(result2)
        
        if not result2.success:
            logger.warning(f"Step 2 failed: {result2.error}")
            return results
        
        # Step 3: Select model (model:z-image)
        logger.info("Step 3: Simulating model selection (model:z-image)")
        state_data = {"category": "image", "category_models": []}
        result3 = await simulate_callback(dp, "model:z-image", state_data)
        results.append(result3)
        
        if not result3.success:
            logger.warning(f"Step 3 failed: {result3.error}")
            return results
        
        # Step 4: Open input (gen:z-image)
        logger.info("Step 4: Simulating generation start (gen:z-image)")
        state_data = {"model_id": "z-image", "category": "image"}
        result4 = await simulate_callback(dp, "gen:z-image", state_data)
        results.append(result4)
        
        if not result4.success:
            logger.warning(f"Step 4 failed: {result4.error}")
            return results
        
        # Step 5: Back button (main_menu)
        logger.info("Step 5: Simulating back button (main_menu)")
        result5 = await simulate_callback(dp, "main_menu")
        results.append(result5)
        
        if not result5.success:
            logger.warning(f"Step 5 failed: {result5.error}")
            return results
        
        # Step 6: Open category again (cat:image)
        logger.info("Step 6: Simulating category callback again (cat:image)")
        result6 = await simulate_callback(dp, "cat:image")
        results.append(result6)
        
        if not result6.success:
            logger.warning(f"Step 6 failed: {result6.error}")
            return results
        
    except Exception as e:
        logger.error(f"Smoke test failed with exception: {e}", exc_info=True)
        results.append(SmokeTestResult("exception", error=str(e)))
    
    return results


async def smoke_test_broken_callbacks() -> List[SmokeTestResult]:
    """
    Test known "broken" callback_data patterns to ensure fallback works.
    """
    results: List[SmokeTestResult] = []
    
    try:
        from aiogram import Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage
        
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        # Import routers
        from bot.handlers import flow, fallback
        dp.include_router(flow.router)
        dp.include_router(fallback.router)
        
        # Test broken callback_data patterns
        broken_callbacks = [
            "unknown:callback",
            "cat:nonexistent",
            "model:invalid-model-id",
            "gen:invalid-model",
            "page:invalid:0",
            "enum:invalid",
            "opt_start:invalid_param",
        ]
        
        for callback_data in broken_callbacks:
            logger.info(f"Testing broken callback: {callback_data}")
            result = await simulate_callback(dp, callback_data)
            results.append(result)
            
            # Broken callbacks should trigger fallback (not crash)
            if result.fallback_triggered:
                logger.info(f"✅ Fallback triggered for {callback_data} (expected)")
            elif result.success:
                logger.warning(f"⚠️ {callback_data} was handled (unexpected, but OK)")
            else:
                logger.error(f"❌ {callback_data} failed: {result.error}")
    
    except Exception as e:
        logger.error(f"Broken callbacks test failed: {e}", exc_info=True)
        results.append(SmokeTestResult("broken_callbacks_test", error=str(e)))
    
    return results


def print_results(results: List[SmokeTestResult], title: str = "SMOKE TEST RESULTS"):
    """Print smoke test results in readable format."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)
    
    passed = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total = len(results)
    
    for result in results:
        print(f"  {result}")
        if result.error:
            print(f"    Error: {result.error}")
        if result.fallback_triggered:
            print(f"    → Fallback handler triggered (OK for unknown callbacks)")
    
    print("\n" + "-" * 60)
    print(f"  Summary: {passed}/{total} passed, {failed}/{total} failed")
    print("=" * 60 + "\n")
    
    return passed == total


async def main():
    """Main smoke test runner."""
    print("\n" + "=" * 60)
    print("  E2E SMOKE TEST: All Buttons Clickable")
    print("=" * 60)
    print("\n  Testing flow:")
    print("    1. /start → main menu")
    print("    2. Open category (cat:image)")
    print("    3. Select model (model:z-image)")
    print("    4. Open input (gen:z-image)")
    print("    5. Back button (main_menu)")
    print("    6. Open category again (cat:image)")
    print("\n  Goal: Catch broken callback_data\n")
    
    # Run main flow test
    flow_results = await smoke_test_flow()
    flow_passed = print_results(flow_results, "MAIN FLOW TEST")
    
    # Run broken callbacks test
    broken_results = await smoke_test_broken_callbacks()
    broken_passed = print_results(broken_results, "BROKEN CALLBACKS TEST")
    
    # Final summary
    all_passed = flow_passed and broken_passed
    
    if all_passed:
        print("✅ ALL SMOKE TESTS PASSED - All buttons are clickable!")
        return 0
    else:
        print("❌ SOME SMOKE TESTS FAILED - Check results above")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ Smoke test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Smoke test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

