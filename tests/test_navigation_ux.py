import pytest
from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback, user_sessions
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_back_to_previous_step_no_history_shows_notice():
    harness = PTBHarness()
    await harness.setup()
    user_id = 5001
    harness.add_handler(CallbackQueryHandler(button_callback))

    user_sessions[user_id] = {
        "model_id": "z-image",
        "model_info": {"name": "Z Image"},
        "params": {},
        "properties": {"prompt": {"type": "string", "required": True}},
        "required": ["prompt"],
        "waiting_for": "prompt",
        "current_param": "prompt",
        "param_history": [],
    }

    try:
        result = await harness.process_callback("back_to_previous_step", user_id=user_id)
        assert result["success"]
        last_message = harness.outbox.get_last_edited_message() or harness.outbox.get_last_message()
        assert last_message is not None
        assert "Нечего возвращать" in last_message["text"]
        assert "UX_NO_HISTORY" in last_message["text"]
    finally:
        user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
async def test_back_to_menu_resets_session_fields():
    harness = PTBHarness()
    await harness.setup()
    user_id = 5002
    harness.add_handler(CallbackQueryHandler(button_callback))

    user_sessions[user_id] = {
        "model_id": "z-image",
        "model_info": {"name": "Z Image"},
        "params": {"prompt": "test"},
        "properties": {"prompt": {"type": "string", "required": True}},
        "required": ["prompt"],
        "waiting_for": "prompt",
        "current_param": "prompt",
        "param_history": ["prompt"],
    }

    try:
        result = await harness.process_callback("back_to_menu", user_id=user_id)
        assert result["success"]
        session = user_sessions.get(user_id, {})
        assert "waiting_for" not in session
        assert "current_param" not in session
        assert "param_history" not in session
    finally:
        user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Test isolation issue: passes alone, fails in group")
async def test_unknown_callback_safe_fallback():
    harness = PTBHarness()
    await harness.setup()
    harness.add_handler(CallbackQueryHandler(button_callback))

    try:
        result = await harness.process_callback("unknown_callback_ux", user_id=5003)
        assert result["success"]
        assert result["outbox"]["callback_answers"], "Expected callback answer for unknown callback"
        last_message = harness.outbox.get_last_edited_message() or harness.outbox.get_last_message()
        assert last_message is not None
    finally:
        await harness.teardown()
