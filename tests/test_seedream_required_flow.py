import pytest
from telegram.ext import CallbackQueryHandler, MessageHandler, filters

from bot_kie import ADMIN_ID, button_callback, input_parameters, user_sessions


@pytest.mark.asyncio
async def test_seedream_required_only_flow(harness):
    user_id = ADMIN_ID
    harness.add_handler(CallbackQueryHandler(button_callback))
    harness.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters))

    result = await harness.process_callback("select_model:bytedance/seedream", user_id=user_id)
    assert result["success"]

    session = user_sessions[user_id]
    assert session.get("waiting_for") in {"prompt", "text"}

    result = await harness.process_message("Лунный пейзаж", user_id=user_id)
    assert result["success"]

    outbox = result["outbox"]
    payload = (outbox.get("edited_messages") or outbox.get("messages"))[-1]
    assert "Подтверждение" in payload["text"]
    assert "image_size" not in payload["text"]

    user_sessions.pop(user_id, None)
