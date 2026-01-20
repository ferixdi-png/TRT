import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler

from app.kie_catalog import get_model_map
from bot_kie import ADMIN_ID, button_callback, start, user_sessions


def _collect_callback_data(reply_markup):
    if not reply_markup:
        return []
    data = []
    keyboard = getattr(reply_markup, "inline_keyboard", [])
    for row in keyboard:
        for button in row:
            if button.callback_data:
                data.append(button.callback_data)
    return data


@pytest.mark.asyncio
async def test_recraft_crisp_upscale_requires_image(harness):
    user_id = ADMIN_ID
    harness.add_handler(CallbackQueryHandler(button_callback, block=True))

    result = await harness.process_callback("select_model:recraft/crisp-upscale", user_id=user_id)
    assert result["success"]

    session = user_sessions.get(user_id)
    assert session
    assert session.get("waiting_for") in {"image_input", "image_urls"}

    payload = (result["outbox"]["edited_messages"] or result["outbox"]["messages"])[-1]
    callbacks = _collect_callback_data(payload.get("reply_markup"))
    assert "confirm_generate" not in callbacks

    result = await harness.process_callback("confirm_generate", user_id=user_id)
    assert result["success"]
    latest = (result["outbox"]["messages"] or result["outbox"]["edited_messages"])[-1]
    latest_text = latest["text"].lower()
    assert "нужно загрузить" in latest_text
    assert "изображ" in latest_text
    session = user_sessions.get(user_id)
    assert session and session.get("waiting_for") in {"image_input", "image_urls"}

    user_sessions.pop(user_id, None)


@pytest.mark.asyncio
async def test_seedream_required_prompt_flow(harness):
    user_id = ADMIN_ID
    harness.add_handler(CallbackQueryHandler(button_callback, block=True))

    result = await harness.process_callback("select_model:bytedance/seedream", user_id=user_id)
    assert result["success"]

    session = user_sessions.get(user_id)
    assert session
    assert session.get("waiting_for") in {"prompt", "text"}

    user_sessions.pop(user_id, None)


@pytest.mark.asyncio
async def test_video_model_requires_prompt(harness):
    user_id = ADMIN_ID
    harness.add_handler(CallbackQueryHandler(button_callback, block=True))

    model_id = "sora-2-text-to-video"
    if model_id not in get_model_map():
        pytest.skip("video model not available in catalog")

    result = await harness.process_callback(f"select_model:{model_id}", user_id=user_id)
    assert result["success"]

    session = user_sessions.get(user_id)
    assert session
    assert session.get("waiting_for") in {"prompt", "text"}

    user_sessions.pop(user_id, None)


@pytest.mark.asyncio
async def test_reset_step_not_unknown_callback(harness):
    user_id = ADMIN_ID
    harness.add_handler(CommandHandler("start", start))
    harness.add_handler(CallbackQueryHandler(button_callback, block=True))

    result = await harness.process_command("/start", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback("reset_step", user_id=user_id)
    assert result["success"]

    callback_texts = [entry.get("text") for entry in result["outbox"]["callback_answers"]]
    assert not any(text and "не понял" in text.lower() for text in callback_texts)

    user_sessions.pop(user_id, None)
