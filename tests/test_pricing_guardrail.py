import asyncio
import time

import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler

import bot_kie
from app.pricing.coverage_guard import (
    DISABLED_REASON_NO_PRICE,
    refresh_pricing_coverage_guard,
    reset_pricing_coverage_guard,
)
from app.ux.model_visibility import is_model_visible
from tests.ptb_harness import PTBHarness


def _collect_outbox_texts(outbox):
    return [item.get("text") for item in outbox.messages + outbox.edited_messages if item.get("text")]


def test_model_without_price_excluded():
    reset_pricing_coverage_guard()
    bot_kie._VISIBLE_MODEL_IDS_CACHE = None
    disabled = refresh_pricing_coverage_guard()
    info = disabled.get("flux-2/pro-text-to-image")
    assert info is not None
    assert info.reason == DISABLED_REASON_NO_PRICE
    assert is_model_visible("flux-2/pro-text-to-image") is False


@pytest.mark.asyncio
async def test_disabled_model_callback_returns_controlled_message(test_env):
    refresh_pricing_coverage_guard()
    harness = PTBHarness()
    await harness.setup()
    try:
        harness.add_handler(CallbackQueryHandler(bot_kie.button_callback))
        result = await harness.process_callback("select_model:flux-2/pro-text-to-image", user_id=12345)
        assert result["success"] is True
        texts = _collect_outbox_texts(harness.outbox)
        assert any("Модель временно отключена" in text for text in texts)
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_start_returns_menu_on_failure(harness, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("pricing failed")

    monkeypatch.setattr(bot_kie, "show_main_menu", _boom)
    harness.add_handler(CommandHandler("start", bot_kie.start))
    result = await harness.process_command("/start", user_id=12345)
    assert result["success"] is True
    texts = _collect_outbox_texts(harness.outbox)
    assert bot_kie.MINIMAL_MENU_TEXT in texts


@pytest.mark.asyncio
async def test_gen_type_warmup_timeout_sets_degraded():
    bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED = False

    async def slow_warmup():
        await asyncio.sleep(0.2)
        return {}

    start = time.monotonic()
    await bot_kie.warm_generation_type_menu_cache(timeout_s=0.05, warmup_fn=slow_warmup)
    elapsed = time.monotonic() - start
    assert bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED is True
    assert elapsed < 0.2


@pytest.mark.asyncio
async def test_balance_handler_degraded_on_storage_error(harness, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(bot_kie, "get_balance_info", _boom)
    harness.add_handler(CommandHandler("balance", bot_kie.check_balance))
    result = await harness.process_command("/balance", user_id=12345)
    assert result["success"] is True
    texts = _collect_outbox_texts(harness.outbox)
    assert any("Баланс временно недоступен" in text for text in texts)
