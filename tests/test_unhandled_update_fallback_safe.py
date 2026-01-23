import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes

from bot_kie import (
    active_session_router,
    button_callback,
    global_text_router,
    input_parameters,
    start,
    unhandled_update_fallback,
    user_sessions,
)


@pytest.mark.asyncio
async def test_unhandled_update_fallback_no_session_safe_menu(harness, monkeypatch):
    events = []

    def fake_log_structured_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr("bot_kie.log_structured_event", fake_log_structured_event)
    harness.application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unhandled_update_fallback,
            block=False,
        ),
        group=100,
    )

    result = await harness.process_message("привет", user_id=88001)
    assert result["success"]
    assert result["outbox"]["messages"]
    assert any(
        event.get("action") == "UNHANDLED_UPDATE_FALLBACK_SAFE"
        and event.get("outcome") == "menu_shown"
        for event in events
    )


@pytest.mark.asyncio
async def test_unhandled_update_fallback_non_text_shows_menu(harness):
    user_id = 88004

    user_sessions.set(
        user_id,
        {
            "waiting_for": "prompt",
            "current_param": "prompt",
            "params": {},
            "properties": {},
            "required": [],
            "model_info": {},
        },
    )

    update = harness.create_mock_update_message(text=None, user_id=user_id)
    harness._attach_bot(update)
    context = ContextTypes.DEFAULT_TYPE.from_update(update, harness.application)

    await unhandled_update_fallback(update, context)

    assert harness.outbox.messages
    last = harness.outbox.messages[-1]
    reply_markup = last.get("reply_markup")
    assert reply_markup is not None
    keyboard = getattr(reply_markup, "inline_keyboard", [])
    labels = [button.text for row in keyboard for button in row]
    assert any("Главное меню" in label for label in labels)


@pytest.mark.asyncio
async def test_active_session_router_routes_prompt_text(harness):
    user_id = 88002

    harness.application.add_handler(CommandHandler("start", start))
    harness.application.add_handler(CallbackQueryHandler(button_callback))
    harness.application.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.Document.ALL,
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
async def test_back_to_menu_clears_waiting_for_and_text_not_routed(harness):
    user_id = 88003

    user_sessions.set(
        user_id,
        {
            "waiting_for": "prompt",
            "current_param": "prompt",
            "params": {},
            "properties": {},
            "required": [],
            "model_info": {},
        },
    )

    harness.application.add_handler(CallbackQueryHandler(button_callback))
    harness.application.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.Document.ALL,
            active_session_router,
        ),
        group=-2,
    )
    harness.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_router), group=1)

    result = await harness.process_callback("back_to_menu", user_id=user_id)
    assert result["success"]

    session = user_sessions.get(user_id, {})
    assert session.get("waiting_for") is None
    assert session.get("current_param") is None

    result = await harness.process_message("обычный текст", user_id=user_id)
    assert result["success"]

    session = user_sessions.get(user_id, {})
    assert session.get("params", {}).get("prompt") is None
