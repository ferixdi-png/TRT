from types import SimpleNamespace

import pytest

import bot_kie
from app.generations.universal_engine import JobResult, KIERequestFailed
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_success_delivered_charge_idempotent(monkeypatch):
    calls = {"subtract": 0}

    async def fake_get_balance(user_id):
        return 100.0 - calls["subtract"]

    async def fake_subtract(user_id, amount):
        calls["subtract"] += 1
        return True

    async def fake_consume(user_id, sku_id, correlation_id=None, source=None):
        return {"status": "ok", "used_today": 1, "remaining": 4, "limit_per_day": 5}

    monkeypatch.setattr(bot_kie, "get_user_balance_async", fake_get_balance)
    monkeypatch.setattr(bot_kie, "subtract_user_balance_async", fake_subtract)
    monkeypatch.setattr(bot_kie, "consume_free_generation", fake_consume)

    session = {}
    await bot_kie._commit_post_delivery_charge(
        session=session,
        user_id=100,
        chat_id=100,
        task_id="task-1",
        sku_id="sku-1",
        price=10.0,
        is_free=False,
        is_admin_user=False,
        correlation_id="corr-1",
        model_id="model-1",
    )
    await bot_kie._commit_post_delivery_charge(
        session=session,
        user_id=100,
        chat_id=100,
        task_id="task-1",
        sku_id="sku-1",
        price=10.0,
        is_free=False,
        is_admin_user=False,
        correlation_id="corr-1",
        model_id="model-1",
    )

    assert calls["subtract"] == 1


@pytest.mark.asyncio
async def test_duplicate_callback_idempotent_free(monkeypatch):
    calls = {"consume": 0}

    async def fake_consume(user_id, sku_id, correlation_id=None, source=None):
        calls["consume"] += 1
        return {"status": "ok", "used_today": 1, "remaining": 4, "limit_per_day": 5}

    monkeypatch.setattr(bot_kie, "consume_free_generation", fake_consume)

    session = {}
    await bot_kie._commit_post_delivery_charge(
        session=session,
        user_id=101,
        chat_id=101,
        task_id="task-free",
        sku_id="sku-free",
        price=0.0,
        is_free=True,
        is_admin_user=False,
        correlation_id="corr-free",
        model_id="model-free",
    )
    await bot_kie._commit_post_delivery_charge(
        session=session,
        user_id=101,
        chat_id=101,
        task_id="task-free",
        sku_id="sku-free",
        price=0.0,
        is_free=True,
        is_admin_user=False,
        correlation_id="corr-free",
        model_id="model-free",
    )

    assert calls["consume"] == 1


@pytest.mark.asyncio
async def test_send_fail_no_charge(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    user_id = 777
    calls = {"subtract": 0}
    try:
        async def fake_get_balance(_user_id):
            return 100.0

        async def fake_subtract(_user_id, _amount):
            calls["subtract"] += 1
            return True

        async def fake_run_generation(*_args, **_kwargs):
            return JobResult(
                task_id="task-send-fail",
                state="success",
                media_type="image",
                urls=["https://example.com/result.png"],
                text=None,
                raw={"elapsed": 0.1},
            )

        async def fake_deliver_result(*_args, **_kwargs):
            return False

        async def fake_check_available(_user_id, _sku_id, correlation_id=None):
            return {"status": "not_free_sku"}

        monkeypatch.setattr(bot_kie, "get_user_balance_async", fake_get_balance)
        monkeypatch.setattr(bot_kie, "subtract_user_balance_async", fake_subtract)
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
            "sku_id": "sku-test",
        }

        update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
        context = SimpleNamespace(bot=harness.application.bot, user_data={})

        await bot_kie.confirm_generation(update, context)

        assert calls["subtract"] == 0
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()


@pytest.mark.asyncio
async def test_kie_fail_no_charge(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    user_id = 778
    calls = {"subtract": 0}
    try:
        async def fake_get_balance(_user_id):
            return 100.0

        async def fake_subtract(_user_id, _amount):
            calls["subtract"] += 1
            return True

        async def fake_run_generation(*_args, **_kwargs):
            raise KIERequestFailed("boom", status=500, error_code="KIE_FAIL")

        async def fake_check_available(_user_id, _sku_id, correlation_id=None):
            return {"status": "not_free_sku"}

        monkeypatch.setattr(bot_kie, "get_user_balance_async", fake_get_balance)
        monkeypatch.setattr(bot_kie, "subtract_user_balance_async", fake_subtract)
        monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
        monkeypatch.setattr(bot_kie, "_update_price_quote", lambda *_args, **_kwargs: {"price_rub": "1.0"})
        monkeypatch.setattr(bot_kie, "is_dry_run", lambda: False)
        monkeypatch.setattr(bot_kie, "allow_real_generation", lambda: True)
        monkeypatch.setattr(bot_kie, "_kie_readiness_state", lambda: (True, "ready"))
        monkeypatch.setattr("kie_input_adapter.normalize_for_generation", lambda _model_id, params: (params, []))
        monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)
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
            "sku_id": "sku-test",
        }

        update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
        context = SimpleNamespace(bot=harness.application.bot, user_data={})

        await bot_kie.confirm_generation(update, context)

        assert calls["subtract"] == 0
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
