from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telegram import Update

import pytest

import bot_kie
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_input_parameters_prompt_always_replies():
    harness = PTBHarness()
    await harness.setup()
    user_id = 2222
    message = MagicMock()
    message.text = "A test prompt"
    message.photo = None
    message.audio = None
    message.voice = None
    message.document = None
    message.message_id = 1
    message.chat_id = user_id
    message.date = None
    message.from_user = harness.create_mock_user(user_id)
    update = Update(update_id=1, message=message)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    sent_messages = []

    async def fake_reply_text(text, **kwargs):
        sent_messages.append(text)

    update.message.reply_text = AsyncMock(side_effect=fake_reply_text)

    bot_kie.user_sessions[user_id] = {
        "model_id": "test-model",
        "model_info": {"name": "Test Model", "input_params": {"prompt": {"required": True}}},
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
        "waiting_for": "prompt",
        "current_param": "prompt",
        "params": {},
        "has_image_input": False,
    }

    try:
        await bot_kie.input_parameters(update, context)
        assert sent_messages, "input_parameters should send at least one response"
        assert bot_kie.user_sessions[user_id]["params"]["prompt"] == "A test prompt"
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
