import pytest
from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback, _processed_update_ids


def _reset_dedupe():
    _processed_update_ids.clear()


@pytest.mark.asyncio
async def test_other_models_opens_sora_card(harness):
    harness.add_handler(CallbackQueryHandler(button_callback))
    _reset_dedupe()

    result = await harness.process_callback("other_models", user_id=12345)

    assert result["success"], result.get("error")
    payloads = result["outbox"]["edited_messages"] + result["outbox"]["messages"]
    assert payloads, "Expected a response for other_models"

    from app.kie_catalog import get_model

    model = get_model("sora-watermark-remover")
    expected_title = model.title_ru if model else "sora-watermark-remover"
    assert any(expected_title in payload.get("text", "") for payload in payloads)


@pytest.mark.asyncio
async def test_type_header_invalid_fallback(harness):
    harness.add_handler(CallbackQueryHandler(button_callback))
    _reset_dedupe()

    result = await harness.process_callback("type_header:unknown_type", user_id=12345)

    assert result["success"], result.get("error")
    payloads = result["outbox"]["edited_messages"] + result["outbox"]["messages"]
    assert payloads, "Expected a response for invalid type header"
    assert any("Доступно моделей" in payload.get("text", "") for payload in payloads)
