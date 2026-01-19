import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot_kie import button_callback, input_parameters, start, unhandled_update_fallback


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_id", "gen_type"),
    [
        ("bytedance/seedream", "text-to-image"),
        ("sora-2-text-to-video", "text-to-video"),
        ("elevenlabs/text-to-speech", "text-to-speech"),
    ],
)
async def test_prompt_flow_no_silence(harness, model_id, gen_type):
    user_id = 45678
    harness.add_handler(CommandHandler("start", start))
    harness.add_handler(CallbackQueryHandler(button_callback))
    harness.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters))

    result = await harness.process_command("/start", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback(f"gen_type:{gen_type}", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback(f"select_model:{model_id}", user_id=user_id)
    assert result["success"]
    assert result["outbox"]["messages"] or result["outbox"]["edited_messages"]

    result = await harness.process_message("котик", user_id=user_id)
    assert result["success"]
    assert result["outbox"]["messages"]
    assert any(msg.get("text") for msg in result["outbox"]["messages"])


@pytest.mark.asyncio
async def test_missing_session_fallback_reply(harness):
    harness.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unhandled_update_fallback,
            block=False,
        )
    )

    result = await harness.process_message("котик", user_id=98765)
    assert result["success"]
    assert result["outbox"]["messages"]
    response_text = result["outbox"]["messages"][-1]["text"].lower()
    assert "контекст" in response_text or "context" in response_text
