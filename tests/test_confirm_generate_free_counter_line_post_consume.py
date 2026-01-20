from types import SimpleNamespace

import pytest

import bot_kie
from app.generations.universal_engine import JobResult
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_confirm_generation_recomputes_free_counter_line(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    user_id = 8888
    try:
        counter_calls = {"count": 0}

        async def fake_free_counter_line(*_args, **_kwargs):
            counter_calls["count"] += 1
            return "after" if counter_calls["count"] > 1 else "before"

        async def fake_consume(user_id, sku_id, correlation_id=None, source=None):
            return {
                "status": "ok",
                "source": "daily",
                "used_today": 2,
                "remaining": 3,
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

        monkeypatch.setattr(bot_kie, "get_free_counter_line", fake_free_counter_line)
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
            "sku_id": "test-sku",
        }

        update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
        context = SimpleNamespace(bot=harness.application.bot, user_data={})

        await bot_kie.confirm_generation(update, context)

        message = harness.outbox.get_last_edited_message() or harness.outbox.get_last_message()
        assert message is not None
        assert "after" in message["text"]
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
