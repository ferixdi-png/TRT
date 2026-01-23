import logging

import pytest


@pytest.mark.asyncio
async def test_unknown_callback_fallback_sends_menu(webhook_harness, caplog):
    caplog.set_level(logging.INFO)
    response = await webhook_harness.send_callback(
        user_id=5050,
        callback_data="unknown:payload",
        update_id=500,
        message_id=5,
        request_id="corr-unknown-1",
    )

    assert response.status == 200
    assert any("UNKNOWN_CALLBACK" in message for message in caplog.messages)
    assert any("correlation_id" in message for message in caplog.messages)

    combined = webhook_harness.outbox.messages + webhook_harness.outbox.edited_messages
    assert combined, "Expected fallback message with menu."
    last = combined[-1]
    reply_markup = last.get("reply_markup")
    assert reply_markup is not None
    keyboard = getattr(reply_markup, "inline_keyboard", [])
    labels = [button.text for row in keyboard for button in row]
    assert any("Главное меню" in label for label in labels)
