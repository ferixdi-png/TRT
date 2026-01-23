import pytest

import bot_kie
from app.admin.auth import reset_admin_ids_cache
from app.pricing.price_resolver import resolve_price_quote
from app.services.free_tools_service import get_free_counter_snapshot


def test_admin_price_quote_zero(monkeypatch):
    monkeypatch.setenv("ADMIN_ID", "123")
    reset_admin_ids_cache()
    quote = resolve_price_quote(
        model_id="nano-banana-pro",
        mode_index=0,
        gen_type=None,
        selected_params={"resolution": "1K"},
        is_admin=True,
    )
    assert quote is not None
    assert float(quote.price_rub) == 0.0


@pytest.mark.asyncio
async def test_admin_free_counter_snapshot(monkeypatch):
    monkeypatch.setenv("ADMIN_ID", "123")
    reset_admin_ids_cache()

    def _should_not_call():
        raise AssertionError("storage should not be accessed for admin snapshot")

    monkeypatch.setattr("app.services.free_tools_service.get_storage", _should_not_call)
    snapshot = await get_free_counter_snapshot(123)
    assert snapshot["used_today"] == 0
    assert snapshot["is_admin"] is True


@pytest.mark.asyncio
async def test_admin_charge_skipped(monkeypatch):
    calls = {"subtract": 0, "consume": 0}

    async def fake_subtract(_user_id, _amount):
        calls["subtract"] += 1
        return True

    async def fake_consume(_user_id, _sku_id, correlation_id=None, source=None, task_id=None):
        calls["consume"] += 1
        return {"status": "ok"}

    monkeypatch.setattr(bot_kie, "subtract_user_balance_async", fake_subtract)
    monkeypatch.setattr(bot_kie, "consume_free_generation", fake_consume)

    session = {}
    await bot_kie._commit_post_delivery_charge(
        session=session,
        user_id=123,
        chat_id=123,
        task_id="task-admin",
        sku_id="sku-admin",
        price=50.0,
        is_free=True,
        is_admin_user=True,
        correlation_id="corr-admin",
        model_id="model-admin",
    )

    assert calls["subtract"] == 0
    assert calls["consume"] == 0
