import pytest
from telegram.ext import CallbackQueryHandler

import bot_kie
from bot_kie import confirm_generation


@pytest.mark.asyncio
async def test_balance_gate_blocks_kie_call(harness, monkeypatch):
    user_id = 5555
    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "test", "aspect_ratio": "portrait"},
        "model_info": {"name": "Sora 2"},
    }

    def fake_normalize(model_id, params):
        return params, []

    async def fake_check_and_consume(*_args, **_kwargs):
        return {"status": "not_free"}

    async def fake_balance(_user_id):
        return 0.0

    def fake_price(*_args, **_kwargs):
        return 10.0

    async def fake_run_generation(*_args, **_kwargs):
        raise AssertionError("run_generation should not be called when balance is insufficient")

    monkeypatch.setattr("kie_input_adapter.normalize_for_generation", fake_normalize)
    monkeypatch.setattr(bot_kie, "check_and_consume_free_generation", fake_check_and_consume)
    monkeypatch.setattr(bot_kie, "get_user_balance_async", fake_balance)
    monkeypatch.setattr(bot_kie, "calculate_price_rub", fake_price)
    monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern='^confirm_generate$'))
    result = await harness.process_callback("confirm_generate", user_id=user_id)

    outbox = result["outbox"]
    payload = (outbox.get("edited_messages") or outbox.get("messages"))[-1]
    assert "Недостаточно" in payload["text"] or "Insufficient" in payload["text"]
