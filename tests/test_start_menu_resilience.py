import asyncio

import pytest
from telegram import InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, CommandHandler

import bot_kie
from bot_kie import (
    filter_visible_models,
    start,
    warm_generation_type_menu_cache,
)
from app.models.registry import get_models_sync
from app.pricing.coverage_guard import DisabledModelInfo


@pytest.mark.asyncio
async def test_start_falls_back_to_minimal_menu_on_timeout(harness, monkeypatch):
    async def slow_keyboard(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return [[InlineKeyboardButton("X", callback_data="back_to_menu")]]

    monkeypatch.setattr("bot_kie.build_main_menu_keyboard", slow_keyboard)
    monkeypatch.setattr("bot_kie.MAIN_MENU_TOTAL_TIMEOUT_SECONDS", 0.05)

    harness.application.add_handler(CommandHandler("start", start))
    result = await harness.process_command("/start", user_id=90001)

    assert result["success"]
    assert harness.outbox.messages
    assert harness.outbox.messages[-1]["text"] == bot_kie.MINIMAL_MENU_TEXT


@pytest.mark.asyncio
async def test_gen_type_menu_warmup_timeout_sets_degraded(monkeypatch):
    async def slow_warmup():
        await asyncio.sleep(0.05)
        return {"text-to-image": {"count": 0}}

    monkeypatch.setattr("bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED", False)

    await warm_generation_type_menu_cache(timeout_s=0.01, warmup_fn=slow_warmup)

    assert bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED is True


def test_disabled_models_hidden_from_menu(monkeypatch):
    models = get_models_sync()
    assert models
    target_id = models[0]["id"]

    def fake_disabled(model_id):
        if model_id == target_id:
            return DisabledModelInfo(
                model_id=target_id,
                reason="NO_PRICE_FOR_PARAMS",
                issues=["no price"],
            )
        return None

    monkeypatch.setattr("app.pricing.coverage_guard.get_disabled_model_info", fake_disabled)
    monkeypatch.setattr("bot_kie._VISIBLE_MODEL_IDS_CACHE", None)

    filtered = filter_visible_models(models)
    assert target_id not in {model["id"] for model in filtered}


@pytest.mark.asyncio
async def test_disabled_model_selection_returns_controlled_message(harness, monkeypatch):
    models = get_models_sync()
    target_id = models[0]["id"]

    def fake_disabled(model_id):
        if model_id == target_id:
            return DisabledModelInfo(
                model_id=target_id,
                reason="NO_PRICE_FOR_PARAMS",
                issues=["no price"],
            )
        return None

    monkeypatch.setattr("app.pricing.coverage_guard.get_disabled_model_info", fake_disabled)

    harness.application.add_handler(CallbackQueryHandler(bot_kie.button_callback))
    result = await harness.process_callback(f"select_model:{target_id}", user_id=90002)

    assert result["success"]
    assert harness.outbox.messages
    assert "Модель временно отключена" in harness.outbox.messages[-1]["text"]


@pytest.mark.asyncio
async def test_pricing_preflight_degraded_returns_controlled_message(harness, monkeypatch):
    models = get_models_sync()
    target_id = models[0]["id"]

    monkeypatch.setattr(
        "app.pricing.coverage_guard.get_pricing_preflight_status",
        lambda: {"ready": False, "degraded": True, "error": "timeout", "updated_at": None},
    )

    harness.application.add_handler(CallbackQueryHandler(bot_kie.button_callback))
    result = await harness.process_callback(f"select_model:{target_id}", user_id=90003)

    assert result["success"]
    assert harness.outbox.messages
    assert "Прайс временно недоступен" in harness.outbox.messages[-1]["text"]
