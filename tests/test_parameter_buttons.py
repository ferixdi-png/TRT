from types import SimpleNamespace

import pytest

import bot_kie
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_optional_enum_shows_skip_button():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3001
    update = harness.create_mock_update_command("/start", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    bot_kie.user_sessions[user_id] = {
        "model_id": "test-model",
        "model_info": {"name": "Test Model", "model_type": "text_to_image"},
        "properties": {
            "style": {
                "type": "string",
                "required": False,
                "enum": ["a", "b"],
            }
        },
        "required": ["style"],
        "params": {},
    }

    try:
        await bot_kie.start_next_parameter(update, context, user_id)
        message = harness.outbox.get_last_message()
        keyboard = message["reply_markup"].inline_keyboard
        buttons = [button.text for row in keyboard for button in row]
        assert any("Пропустить" in text for text in buttons)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
async def test_optional_text_shows_skip_button():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3002
    update = harness.create_mock_update_command("/start", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    bot_kie.user_sessions[user_id] = {
        "model_id": "test-model",
        "model_info": {"name": "Test Model", "model_type": "text_to_image"},
        "properties": {
            "note": {
                "type": "string",
                "required": False,
            }
        },
        "required": ["note"],
        "params": {},
    }

    try:
        await bot_kie.start_next_parameter(update, context, user_id)
        message = harness.outbox.get_last_message()
        keyboard = message["reply_markup"].inline_keyboard
        buttons = [button.text for row in keyboard for button in row]
        assert any("Пропустить" in text for text in buttons)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
async def test_optional_boolean_shows_skip_button():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3003
    update = harness.create_mock_update_command("/start", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    bot_kie.user_sessions[user_id] = {
        "model_id": "test-model",
        "model_info": {"name": "Test Model", "model_type": "text_to_image"},
        "properties": {
            "flag": {
                "type": "boolean",
                "required": False,
            }
        },
        "required": ["flag"],
        "params": {},
    }

    try:
        await bot_kie.start_next_parameter(update, context, user_id)
        message = harness.outbox.get_last_message()
        keyboard = message["reply_markup"].inline_keyboard
        buttons = [button.text for row in keyboard for button in row]
        assert any("Пропустить" in text for text in buttons)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
