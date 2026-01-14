#!/usr/bin/env python3
"""
Smoke test for button instrumentation - simulates main menu → categories → model selection.
Validates telemetry chains and responses.
"""

import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_category_buttons():
    """Test category button callbacks."""
    logger.info("=" * 60)
    logger.info("SMOKE TEST: Category Buttons")
    logger.info("=" * 60)
    
    # Import after path setup
    from bot.handlers.flow import category_cb, _category_keyboard
    from aiogram.fsm.context import FSMContext
    from aiogram.types import CallbackQuery, User, Chat, Message
    from unittest.mock import AsyncMock, Mock
    
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
    mock_callback.id = "test_query_id"
    mock_callback.from_user = mock_user
    mock_callback.message = mock_message
    mock_callback.answer = AsyncMock()
    mock_callback.data = "cat:image"
    
    # Create mock state
    mock_state = Mock(spec=FSMContext)
    mock_state.update_data = AsyncMock()
    mock_state.get_data = AsyncMock(return_value={})
    
    # Test category callback
    try:
        await category_cb(mock_callback, mock_state, data={})
        logger.info("✅ category_cb executed without exceptions")
        assert mock_callback.answer.called, "callback.answer() should be called"
        logger.info("✅ callback.answer() was called")
    except Exception as e:
        logger.error(f"❌ category_cb failed: {e}", exc_info=True)
        return False
    
    return True


async def test_telemetry_helpers():
    """Test telemetry helper functions."""
    logger.info("=" * 60)
    logger.info("SMOKE TEST: Telemetry Helpers")
    logger.info("=" * 60)
    
    from app.telemetry.telemetry_helpers import (
        get_update_id, get_callback_id, get_user_id, get_chat_id
    )
    from aiogram.types import CallbackQuery, User, Chat, Message, Update
    from unittest.mock import Mock
    
    # Test get_callback_id
    mock_callback = Mock(spec=CallbackQuery)
    mock_callback.id = "test_id"
    callback_id = get_callback_id(mock_callback)
    assert callback_id == "test_id", f"Expected 'test_id', got {callback_id}"
    logger.info("✅ get_callback_id works")
    
    # Test get_user_id
    mock_user = Mock(spec=User)
    mock_user.id = 12345
    mock_callback.from_user = mock_user
    user_id = get_user_id(mock_callback)
    assert user_id == 12345, f"Expected 12345, got {user_id}"
    logger.info("✅ get_user_id works")
    
    # Test get_update_id with data
    data = {"event_update": Mock(spec=Update, update_id=123)}
    update_id = get_update_id(mock_callback, data)
    assert update_id == 123, f"Expected 123, got {update_id}"
    logger.info("✅ get_update_id works with event_update")
    
    return True


async def test_log_callback_rejected():
    """Test log_callback_rejected with all parameters."""
    logger.info("=" * 60)
    logger.info("SMOKE TEST: log_callback_rejected signature")
    logger.info("=" * 60)
    
    from app.telemetry.events import log_callback_rejected, generate_cid
    
    cid = generate_cid()
    
    # Test with all parameters (should not raise TypeError)
    try:
        log_callback_rejected(
            callback_data="test:data",
            reason_code="TEST_REJECT",
            reason_detail="Test detail",
            error_type="TestError",
            error_message="Test error message",
            cid=cid
        )
        logger.info("✅ log_callback_rejected accepts all parameters")
    except TypeError as e:
        logger.error(f"❌ log_callback_rejected signature mismatch: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ log_callback_rejected failed: {e}", exc_info=True)
        return False
    
    return True


async def test_unified_pipeline():
    """Test unified pipeline basic functions."""
    logger.info("=" * 60)
    logger.info("SMOKE TEST: Unified Pipeline")
    logger.info("=" * 60)
    
    from app.kie.unified_pipeline import get_unified_pipeline
    
    pipeline = get_unified_pipeline()
    
    # Test resolve_model (may return None if model not found, that's OK)
    model = pipeline.resolve_model("test_model_id")
    logger.info(f"✅ resolve_model works (returned: {model is not None})")
    
    # Test get_schema
    schema = pipeline.get_schema("test_model_id")
    assert isinstance(schema, dict), f"Expected dict, got {type(schema)}"
    logger.info("✅ get_schema works")
    
    # Test apply_defaults
    test_schema = {
        "properties": {
            "prompt": {"type": "string", "required": True},
            "optional_field": {"type": "string", "default": "default_value"}
        },
        "required": ["prompt"]
    }
    collected = {"prompt": "test prompt"}
    result = pipeline.apply_defaults(test_schema, collected)
    assert "optional_field" in result, "Default should be applied"
    assert result["optional_field"] == "default_value", "Default value should be correct"
    logger.info("✅ apply_defaults works")
    
    return True


async def main():
    """Run all smoke tests."""
    logger.info("=" * 60)
    logger.info("SMOKE TESTS: Button Instrumentation")
    logger.info("=" * 60)
    
    tests = [
        ("Telemetry Helpers", test_telemetry_helpers),
        ("log_callback_rejected", test_log_callback_rejected),
        ("Unified Pipeline", test_unified_pipeline),
        ("Category Buttons", test_category_buttons),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ {test_name} failed with exception: {e}", exc_info=True)
            results.append((test_name, False))
    
    # Summary
    logger.info("=" * 60)
    logger.info("SMOKE TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("✅ All smoke tests passed!")
        return 0
    else:
        logger.error(f"❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
