"""
Минимальный e2e smoke: /start -> free_tools -> gen_type -> select_model.
"""

import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler

from bot_kie import button_callback, start


def _last_payload(outbox: dict) -> dict:
    edited = outbox.get("edited_messages", [])
    messages = outbox.get("messages", [])
    return edited[-1] if edited else messages[-1]


@pytest.mark.asyncio
async def test_e2e_start_free_tools_select_model(harness):
    harness.add_handler(CommandHandler("start", start))
    harness.add_handler(CallbackQueryHandler(button_callback))

    result = await harness.process_command("/start", user_id=23456)
    assert result["success"]
    assert "Привет" in result["outbox"]["messages"][0]["text"] or "Welcome" in result["outbox"]["messages"][0]["text"]

    result = await harness.process_callback("free_tools", user_id=23456)
    assert result["success"]
    payload = _last_payload(result["outbox"])
    assert (
        "БЕСПЛАТНЫЕ ИНСТРУМЕНТЫ" in payload["text"]
        or "Бесплатные инструменты не найдены" in payload["text"]
    )

    result = await harness.process_callback("gen_type:text-to-video", user_id=23456)
    assert result["success"]
    payload = _last_payload(result["outbox"])
    assert payload["text"]

    result = await harness.process_callback("select_model:sora-2-text-to-video", user_id=23456)
    assert result["success"]
    payload = _last_payload(result["outbox"])
    assert "Недостаточно средств" in payload["text"] or "Insufficient" in payload["text"]
