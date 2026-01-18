import pytest

from bot_kie import _register_all_handlers_internal


def _has_back_to_menu(payloads):
    for payload in payloads:
        markup = payload.get("reply_markup")
        if not markup:
            continue
        for row in markup.inline_keyboard:
            for button in row:
                if getattr(button, "callback_data", None) == "back_to_menu":
                    return True
    return False


@pytest.mark.asyncio
async def test_top_level_buttons_have_back_menu(harness):
    await _register_all_handlers_internal(harness.application)
    result = await harness.process_command("/start", user_id=12345)
    assert result["success"], result.get("error")
    header_message = result["outbox"]["messages"][0]
    keyboard = header_message["reply_markup"].inline_keyboard

    callbacks = [button.callback_data for row in keyboard for button in row]

    for callback_data in callbacks:
        response = await harness.process_callback(callback_data, user_id=12345)
        assert response["success"], response.get("error")
        payloads = response["outbox"]["edited_messages"] + response["outbox"]["messages"]
        assert payloads
        assert _has_back_to_menu(payloads)


@pytest.mark.asyncio
async def test_model_card_contains_required_fields_and_examples(harness):
    await _register_all_handlers_internal(harness.application)
    await harness.process_command("/start", user_id=12345)
    response = await harness.process_callback("model:z-image", user_id=12345)
    assert response["success"], response.get("error")
    payloads = response["outbox"]["edited_messages"] + response["outbox"]["messages"]
    assert payloads
    text = payloads[0]["text"]
    assert "Обязательные поля" in text
    assert "Пример" in text
