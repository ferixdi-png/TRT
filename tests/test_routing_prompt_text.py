import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot_kie import (
    active_session_router,
    button_callback,
    input_parameters,
    start,
    unhandled_update_fallback,
    user_sessions,
)


@pytest.mark.asyncio
async def test_prompt_text_is_handled(harness):
    user_id = 55123

    harness.application.add_handler(CommandHandler("start", start))
    harness.application.add_handler(CallbackQueryHandler(button_callback))
    harness.application.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.AUDIO | filters.VOICE | filters.Document.ALL,
            active_session_router,
        ),
        group=-2,
    )
    harness.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters))

    called = {"fallback": False}

    async def sentinel_fallback(update, context):
        called["fallback"] = True
        return await unhandled_update_fallback(update, context)

    harness.application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, sentinel_fallback, block=False),
        group=100,
    )

    result = await harness.process_command("/start", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback("gen_type:text-to-image", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback("select_model:bytedance/seedream", user_id=user_id)
    assert result["success"]

    result = await harness.process_message("котик", user_id=user_id)
    assert result["success"]

    session = user_sessions.get(user_id)
    assert session
    assert session.get("params", {}).get("prompt") == "котик"
    assert session.get("waiting_for") != "prompt"
    assert called["fallback"] is False


@pytest.mark.asyncio
async def test_fallback_no_session_no_crash(harness):
    harness.application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unhandled_update_fallback,
            block=False,
        )
    )

    result = await harness.process_message("привет", user_id=77890)
    assert result["success"]
    assert result["outbox"]["messages"]
    last_text = result["outbox"]["messages"][-1]["text"].lower()
    assert "главное меню" in last_text or "main menu" in last_text
