#!/usr/bin/env python3
"""Quick smoke test: balance callback with state."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, User, Chat, Message

async def test_balance_fix():
    """Test that balance_cb no longer crashes with state."""
    user = User(id=12345, is_bot=False, first_name="Test")
    chat = Chat(id=12345, type="private")
    message = MagicMock(spec=Message)
    message.chat = chat
    message.from_user = user
    message.answer = AsyncMock()
    
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = user
    callback.message = message
    callback.answer = AsyncMock()
    
    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    
    from bot.handlers.flow import balance_cb
    
    try:
        await balance_cb(callback, state)
        print("✅ balance_cb(callback, state) - PASS (no crash)")
        return 0
    except Exception as e:
        print(f"❌ balance_cb failed: {e}")
        return 1

if __name__ == "__main__":
    exit(asyncio.run(test_balance_fix()))
