from types import SimpleNamespace

import pytest

import bot_kie
from app.generations.universal_engine import JobResult
from app.pricing.ssot_catalog import get_free_sku_ids
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_free_consume_uses_sku_id(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    user_id = 9911
    try:
        free_sku_ids = get_free_sku_ids()
        assert free_sku_ids
        free_sku_id = free_sku_ids[0]
        captured = {}

        async def fake_consume(user_id, sku_id, correlation_id=None, source=None):
            captured["sku_id"] = sku_id
            return {
                "status": "ok",
                "used_today": 1,
                "remaining": 4,
                "limit_per_day": 5,
            }

        async def fake_check_available(user_id, sku_id, correlation_id=None):
            return {"status": "ok"}

        async def fake_run_generation(*_args, **_kwargs):
            return JobResult(
                task_id="task-123",
                state="success",
                media_type="image",
                urls=["https://example.com/result.png"],
                text=None,
                raw={"elapsed": 0.1},
            )

        async def fake_deliver_result(*_args, **_kwargs):
            return True

        monkeypatch.setattr(bot_kie, "consume_free_generation", fake_consume)
        monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
        monkeypatch.setattr(bot_kie, "_update_price_quote", lambda *_args, **_kwargs: {"price_rub": "1.0"})
        monkeypatch.setattr(bot_kie, "is_dry_run", lambda: False)
        monkeypatch.setattr(bot_kie, "allow_real_generation", lambda: True)
        monkeypatch.setattr(bot_kie, "_kie_readiness_state", lambda: (True, "ready"))
        monkeypatch.setattr("kie_input_adapter.normalize_for_generation", lambda _model_id, params: (params, []))
        monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)
        monkeypatch.setattr("app.generations.telegram_sender.deliver_result", fake_deliver_result)
        monkeypatch.setattr(
            "app.kie_catalog.get_model",
            lambda _model_id: SimpleNamespace(model_mode="image", output_media_type="image"),
        )

        bot_kie.user_sessions[user_id] = {
            "model_id": "test-model",
            "model_info": {"name": "Test Model"},
            "params": {},
            "properties": {},
            "required": [],
            "sku_id": free_sku_id,
        }

        update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
        context = SimpleNamespace(bot=harness.application.bot, user_data={})

        await bot_kie.confirm_generation(update, context)

        assert captured["sku_id"] == free_sku_id
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
