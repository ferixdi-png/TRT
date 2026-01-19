import pytest
from telegram import Update

import bot_kie
from bot_kie import _register_all_handlers_internal


@pytest.mark.asyncio
async def test_z_image_aspect_ratio_flow_no_unknown_menu(harness):
    await _register_all_handlers_internal(harness.application)
    user_id = 42001

    try:
        result = await harness.process_command("/start", user_id=user_id)
        assert result["success"], result.get("error")

        result = await harness.process_callback("gen_type:text-to-image", user_id=user_id)
        assert result["success"], result.get("error")

        result = await harness.process_callback("select_model:z-image", user_id=user_id)
        assert result["success"], result.get("error")

        harness.outbox.clear()
        message = harness.create_mock_message(text="Test prompt", user_id=user_id, chat_id=user_id)
        update = Update(update_id=99, message=message)
        harness._attach_bot(update)
        await harness.application.process_update(update)

        session = bot_kie.user_sessions[user_id]
        assert session["waiting_for"] == "aspect_ratio"

        result = await harness.process_callback("set_param:aspect_ratio:9:16", user_id=user_id)
        assert result["success"], result.get("error")

        session = bot_kie.user_sessions[user_id]
        assert session.get("waiting_for") is None
        payloads = result["outbox"]["edited_messages"] + result["outbox"]["messages"]
        assert payloads
        assert any(
            "Подтверждение" in payload["text"] or "Generation Confirmation" in payload["text"]
            for payload in payloads
        )
        assert all("Привет" not in payload["text"] and "Welcome" not in payload["text"] for payload in payloads)
        assert not any(
            answer.get("text") and "не понял" in answer["text"].lower()
            for answer in result["outbox"]["callback_answers"]
        )
    finally:
        bot_kie.user_sessions.pop(user_id, None)
