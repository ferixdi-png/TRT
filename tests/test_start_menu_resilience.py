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
@pytest.mark.xfail(reason="Flaky: passes alone, fails in group due to test isolation")
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
@pytest.mark.xfail(reason="Test isolation issue: passes alone, fails in group")
async def test_start_menu_timeout_schedules_retry_without_unhandled(harness, monkeypatch, caplog):
    async def slow_keyboard(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return [[InlineKeyboardButton("X", callback_data="back_to_menu")]]

    async def slow_sections(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return "Header", "Details"

    monkeypatch.setattr("bot_kie.build_main_menu_keyboard", slow_keyboard)
    monkeypatch.setattr("bot_kie._build_main_menu_sections", slow_sections)
    monkeypatch.setattr("bot_kie.MAIN_MENU_TOTAL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("bot_kie.MAIN_MENU_BACKGROUND_TIMEOUT_SECONDS", 0.05)

    caplog.set_level("ERROR")
    harness.application.add_handler(CommandHandler("start", start))
    result = await harness.process_command("/start", user_id=90011)

    assert result["success"]
    assert harness.outbox.messages
    assert harness.outbox.messages[-1]["text"] == bot_kie.MINIMAL_MENU_TEXT

    await asyncio.sleep(0.1)
    assert not any("Task exception was never retrieved" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_gen_type_menu_warmup_timeout_sets_degraded(monkeypatch):
    async def slow_warmup():
        await asyncio.sleep(0.05)
        return {"text-to-image": {"count": 0}}

    monkeypatch.setattr("bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED", False)

    await warm_generation_type_menu_cache(timeout_s=0.01, warmup_fn=slow_warmup)

    assert bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED is True


@pytest.mark.asyncio
async def test_start_ack_sent_on_inflight_dedup(harness, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_menu(update, context, *, source, correlation_id, edit_message_id=None):
        started.set()
        await release.wait()
        return {
            "correlation_id": correlation_id,
            "user_id": update.effective_user.id if update.effective_user else None,
            "chat_id": update.effective_chat.id if update.effective_chat else None,
            "update_id": update.update_id,
            "ui_context_before": None,
            "ui_context_after": bot_kie.UI_CONTEXT_MAIN_MENU,
            "used_edit": False,
            "fallback_send": False,
            "message_id": edit_message_id,
        }

    monkeypatch.setattr("bot_kie._start_menu_with_fallback", slow_menu)
    harness.application.add_handler(CommandHandler("start", start))

    update_primary = harness.create_mock_update_command("/start", user_id=90101, update_id=1)
    harness._attach_bot(update_primary)
    update_secondary = harness.create_mock_update_command("/start", user_id=90101, update_id=2)
    harness._attach_bot(update_secondary)

    task_primary = asyncio.create_task(harness.application.process_update(update_primary))
    await started.wait()

    await harness.application.process_update(update_secondary)

    assert harness.outbox.messages
    assert any("Готовлю меню" in msg["text"] or "Preparing the menu" in msg["text"] for msg in harness.outbox.messages)

    release.set()
    await task_primary


@pytest.mark.asyncio
async def test_start_ack_latency_under_dependency_degradation(harness, monkeypatch):
    async def slow_keyboard(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return [[InlineKeyboardButton("X", callback_data="back_to_menu")]]

    async def slow_sections(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return "Header", "Details"

    monkeypatch.setenv("START_SKIP_ACK", "0")  # Enable start ack for this test
    monkeypatch.setattr("bot_kie.build_main_menu_keyboard", slow_keyboard)
    monkeypatch.setattr("bot_kie._build_main_menu_sections", slow_sections)
    monkeypatch.setattr("bot_kie.START_FALLBACK_MAX_MS", 40)
    monkeypatch.setattr("bot_kie.START_HANDLER_BUDGET_MS", 80)
    monkeypatch.setattr("bot_kie.MAIN_MENU_TOTAL_TIMEOUT_SECONDS", 0.05)

    harness.application.add_handler(CommandHandler("start", start))
    started = asyncio.get_event_loop().time()
    result = await harness.process_command("/start", user_id=90111)
    elapsed = asyncio.get_event_loop().time() - started

    assert result["success"]
    assert harness.outbox.messages
    # Accept either start ack placeholder or fallback menu
    first_text = harness.outbox.messages[0]["text"]
    assert any(x in first_text for x in ["Готовлю меню", "Preparing the menu", "Главное меню", "Временный сбой"])
    assert elapsed < 0.3


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
    payloads = harness.outbox.messages or harness.outbox.edited_messages
    assert payloads
    assert "Модель временно отключена" in payloads[-1]["text"]


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
    payloads = harness.outbox.messages or harness.outbox.edited_messages
    assert payloads
    assert "Прайс временно недоступен" in payloads[-1]["text"]
