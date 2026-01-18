from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update

import bot_kie
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_flux_prompt_advances_to_aspect_ratio():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3001
    message = MagicMock()
    message.text = "A neon city prompt"
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

    message.reply_text = AsyncMock()

    bot_kie.user_sessions[user_id] = {
        "model_id": "flux-2/pro-text-to-image",
        "model_info": {
            "name": "Flux Pro",
            "input_params": {
                "prompt": {"required": True, "type": "string"},
                "aspect_ratio": {"required": True, "type": "string", "enum": ["1:1", "16:9"]},
                "resolution": {"required": True, "type": "string", "enum": ["1024x1024", "1536x1024"]},
            },
        },
        "properties": {
            "prompt": {"type": "string", "required": True},
            "aspect_ratio": {"type": "string", "required": True, "enum": ["1:1", "16:9"]},
            "resolution": {"type": "string", "required": True, "enum": ["1024x1024", "1536x1024"]},
        },
        "required": ["prompt", "aspect_ratio", "resolution"],
        "param_order": ["prompt", "aspect_ratio", "resolution"],
        "waiting_for": "prompt",
        "current_param": "prompt",
        "params": {},
        "param_history": [],
        "has_image_input": False,
    }

    try:
        await bot_kie.input_parameters(update, context)
        assert bot_kie.user_sessions[user_id]["waiting_for"] == "aspect_ratio"
        assert any("aspect ratio" in msg["text"].lower() for msg in harness.outbox.messages)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
async def test_back_to_previous_step_uses_history_stack():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3002
    update = harness.create_mock_update_callback("back_to_previous_step", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    bot_kie.user_sessions[user_id] = {
        "model_id": "flux-2/pro-text-to-image",
        "model_info": {
            "name": "Flux Pro",
            "input_params": {
                "prompt": {"required": True, "type": "string"},
                "aspect_ratio": {"required": True, "type": "string", "enum": ["1:1", "16:9"]},
                "resolution": {"required": True, "type": "string", "enum": ["1024x1024", "1536x1024"]},
            },
        },
        "properties": {
            "prompt": {"type": "string", "required": True},
            "aspect_ratio": {"type": "string", "required": True, "enum": ["1:1", "16:9"]},
            "resolution": {"type": "string", "required": True, "enum": ["1024x1024", "1536x1024"]},
        },
        "required": ["prompt", "aspect_ratio", "resolution"],
        "param_order": ["prompt", "aspect_ratio", "resolution"],
        "waiting_for": "resolution",
        "current_param": "resolution",
        "params": {"prompt": "Test", "aspect_ratio": "1:1"},
        "param_history": ["prompt", "aspect_ratio"],
    }

    try:
        await bot_kie.button_callback(update, context)
        session = bot_kie.user_sessions[user_id]
        assert session["waiting_for"] == "aspect_ratio"
        assert "aspect_ratio" not in session["params"]
        assert any("aspect ratio" in msg["text"].lower() for msg in harness.outbox.messages)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
async def test_text_not_expected_shows_guidance_and_keeps_params():
    harness = PTBHarness()
    await harness.setup()
    user_id = 3003
    message = MagicMock()
    message.text = "Unexpected text"
    message.photo = None
    message.audio = None
    message.voice = None
    message.document = None
    message.message_id = 1
    message.chat_id = user_id
    message.date = None
    message.from_user = harness.create_mock_user(user_id)
    update = Update(update_id=2, message=message)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    sent_messages = []

    async def fake_reply_text(text, **kwargs):
        sent_messages.append(text)

    message.reply_text = AsyncMock(side_effect=fake_reply_text)

    bot_kie.user_sessions[user_id] = {
        "model_id": "flux-2/pro-text-to-image",
        "model_info": {"name": "Flux Pro", "input_params": {"prompt": {"required": True, "type": "string"}}},
        "properties": {"prompt": {"type": "string", "required": True}},
        "required": ["prompt"],
        "waiting_for": None,
        "current_param": None,
        "params": {"prompt": "Already set"},
        "param_history": ["prompt"],
    }

    try:
        await bot_kie.input_parameters(update, context)
        assert bot_kie.user_sessions[user_id]["params"]["prompt"] == "Already set"
        assert any("⚙️" in text or "parameters" in text.lower() for text in sent_messages)
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
