#!/usr/bin/env python3
"""
Smoke test for PASSIVE mode user feedback (direct Telegram API).

Tests that _send_passive_ack function correctly:
1. Parses update (dict and aiogram Update-like)
2. Extracts callback_query_id or chat_id
3. Forms correct Telegram API request
4. Handles errors gracefully
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import function to test
from app.utils.update_queue import _send_passive_ack


async def test_callback_query_dict():
    """Test 1: callback_query update as dict."""
    print("Test 1: callback_query update as dict...")
    
    update = {
        "update_id": 12345,
        "callback_query": {
            "id": "test_query_123",
            "from": {"id": 12345, "first_name": "Test"},
            "message": {"chat": {"id": 12345}, "message_id": 1},
            "data": "cat:image"
        }
    }
    
    # Mock aiohttp.ClientSession
    with patch('app.utils.update_queue.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Mock os.getenv
        with patch('app.utils.update_queue.os.getenv', return_value='test_token_123'):
            success, cid = await _send_passive_ack(update, 12345, 0)
            
            assert success, "Should succeed with valid callback_query"
            assert cid is not None, "Should generate CID"
            assert cid.startswith("cid_"), "CID should start with 'cid_'"
            
            # Verify API call
            assert mock_post.called, "Should call Telegram API"
            call_args = mock_post.call_args
            assert 'answerCallbackQuery' in call_args[0][0], "Should call answerCallbackQuery endpoint"
            
            payload = call_args[1]['json']
            assert payload['callback_query_id'] == "test_query_123", "Should use correct callback_query_id"
            assert "Сервис перезапускается" in payload['text'], "Should contain passive message"
            assert payload['show_alert'] is False, "Should not show alert"
            
            print("  ✅ PASS: callback_query dict")
            return True


async def test_message_dict():
    """Test 2: message update as dict."""
    print("Test 2: message update as dict...")
    
    update = {
        "update_id": 12346,
        "message": {
            "chat": {"id": 12345},
            "from": {"id": 12345, "first_name": "Test"},
            "text": "/start",
            "message_id": 1
        }
    }
    
    # Mock aiohttp.ClientSession
    with patch('app.utils.update_queue.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Mock os.getenv
        with patch('app.utils.update_queue.os.getenv', return_value='test_token_123'):
            success, cid = await _send_passive_ack(update, 12346, 0)
            
            assert success, "Should succeed with valid message"
            assert cid is not None, "Should generate CID"
            
            # Verify API call
            assert mock_post.called, "Should call Telegram API"
            call_args = mock_post.call_args
            assert 'sendMessage' in call_args[0][0], "Should call sendMessage endpoint"
            
            payload = call_args[1]['json']
            assert payload['chat_id'] == 12345, "Should use correct chat_id"
            assert "Сервис перезапускается" in payload['text'], "Should contain passive message"
            assert payload['disable_web_page_preview'] is True, "Should disable preview"
            
            print("  ✅ PASS: message dict")
            return True


async def test_callback_query_aiogram_like():
    """Test 3: callback_query update as aiogram-like object."""
    print("Test 3: callback_query update as aiogram-like object...")
    
    # Create mock objects
    mock_callback = Mock()
    mock_callback.id = "test_query_456"
    mock_callback.data = "cat:enhance"
    
    mock_message = Mock()
    mock_message.chat.id = 12345
    mock_message.message_id = 1
    mock_callback.message = mock_message
    
    mock_update = Mock()
    mock_update.update_id = 12347
    mock_update.callback_query = mock_callback
    
    # Mock aiohttp.ClientSession
    with patch('app.utils.update_queue.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Mock os.getenv
        with patch('app.utils.update_queue.os.getenv', return_value='test_token_123'):
            success, cid = await _send_passive_ack(mock_update, 12347, 0)
            
            assert success, "Should succeed with valid callback_query object"
            assert cid is not None, "Should generate CID"
            
            # Verify API call
            assert mock_post.called, "Should call Telegram API"
            call_args = mock_post.call_args
            assert 'answerCallbackQuery' in call_args[0][0], "Should call answerCallbackQuery endpoint"
            
            payload = call_args[1]['json']
            assert payload['callback_query_id'] == "test_query_456", "Should use correct callback_query_id"
            
            print("  ✅ PASS: callback_query aiogram-like")
            return True


async def test_unknown_update():
    """Test 4: unknown update type (no callback_query or message)."""
    print("Test 4: unknown update type...")
    
    update = {
        "update_id": 12348,
        "edited_message": {"text": "edited"}
    }
    
    # Mock os.getenv
    with patch('app.utils.update_queue.os.getenv', return_value='test_token_123'):
        success, cid = await _send_passive_ack(update, 12348, 0)
        
        assert not success, "Should fail with unknown update type"
        assert cid is not None, "Should still generate CID"
        
        print("  ✅ PASS: unknown update")
        return True


async def test_missing_token():
    """Test 5: missing TELEGRAM_BOT_TOKEN."""
    print("Test 5: missing TELEGRAM_BOT_TOKEN...")
    
    update = {
        "update_id": 12349,
        "callback_query": {
            "id": "test_query_789",
            "data": "cat:image"
        }
    }
    
    # Mock os.getenv to return empty string
    with patch('app.utils.update_queue.os.getenv', return_value=''):
        success, cid = await _send_passive_ack(update, 12349, 0)
        
        assert not success, "Should fail without token"
        assert cid is not None, "Should still generate CID"
        
        print("  ✅ PASS: missing token")
        return True


async def test_api_error():
    """Test 6: Telegram API returns error."""
    print("Test 6: Telegram API error...")
    
    update = {
        "update_id": 12350,
        "callback_query": {
            "id": "test_query_error",
            "data": "cat:image"
        }
    }
    
    # Mock aiohttp.ClientSession with error response
    with patch('app.utils.update_queue.aiohttp.ClientSession') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value='{"ok": false, "description": "Bad Request"}')
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_session.return_value.__aenter__.return_value.post = mock_post
        
        # Mock os.getenv
        with patch('app.utils.update_queue.os.getenv', return_value='test_token_123'):
            success, cid = await _send_passive_ack(update, 12350, 0)
            
            assert not success, "Should fail with API error"
            assert cid is not None, "Should still generate CID"
            
            print("  ✅ PASS: API error handling")
            return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("SMOKE TEST: PASSIVE Mode User Feedback")
    print("=" * 60)
    print()
    
    tests = [
        test_callback_query_dict,
        test_message_dict,
        test_callback_query_aiogram_like,
        test_unknown_update,
        test_missing_token,
        test_api_error,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✅ PASSED: {passed}/{len(tests)}")
    print(f"❌ FAILED: {failed}/{len(tests)}")
    
    if failed == 0:
        print()
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print()
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

