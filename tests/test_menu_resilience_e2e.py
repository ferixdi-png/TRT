from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import pytest
from telegram.error import BadRequest as TelegramBadRequest

import bot_kie


@pytest.mark.asyncio
async def test_menu_edit_failure_falls_back_to_send(harness, monkeypatch):
    update = harness.create_mock_update_callback("show_models", user_id=11001)
    harness._attach_bot(update)
    from telegram import CallbackQuery

    monkeypatch.setattr(
        CallbackQuery,
        "edit_message_text",
        AsyncMock(side_effect=TelegramBadRequest("edit failed")),
    )

    context = SimpleNamespace(bot=harness.application.bot, user_data={})
    result = await bot_kie.show_main_menu(update, context, source="test_edit_fail")

    assert result["used_edit"] is False
    assert harness.outbox.messages
    assert harness.outbox.messages[-1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_menu_survives_dependency_timeout(harness, monkeypatch):
    async def slow_lang(_user_id):
        await asyncio.sleep(0.05)
        return "ru"

    monkeypatch.setattr("app.services.user_service.get_user_language", slow_lang)
    monkeypatch.setattr("bot_kie.MAIN_MENU_DEP_TIMEOUT_SECONDS", 0.01)

    update = harness.create_mock_update_command("/start", user_id=11002)
    harness._attach_bot(update)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    result = await bot_kie.show_main_menu(update, context, source="test_dep_timeout")

    assert result["chat_id"] is not None
    assert harness.outbox.messages
    assert harness.outbox.messages[-1]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_warmup_cancelled_is_not_degraded(monkeypatch):
    async def cancelled():
        raise asyncio.CancelledError()

    monkeypatch.setattr("bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED", False)
    await bot_kie.warm_generation_type_menu_cache(timeout_s=0.1, warmup_fn=cancelled)
    assert bot_kie.GEN_TYPE_MENU_WARMUP_DEGRADED is False


@pytest.mark.asyncio
async def test_load_start_and_callbacks_no_menu_timeouts(harness, caplog, monkeypatch):
    async def fast_lang(_user_id):
        return "ru"

    monkeypatch.setattr("app.services.user_service.get_user_language", fast_lang)
    monkeypatch.setattr("bot_kie.MAIN_MENU_BUILD_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr("bot_kie.MAIN_MENU_TOTAL_TIMEOUT_SECONDS", 1.0)

    caplog.set_level("WARNING")
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    for idx in range(100):
        update = harness.create_mock_update_command("/start", user_id=12000 + idx, update_id=idx + 1)
        harness._attach_bot(update)
        await bot_kie.show_main_menu(update, context, source="/start-load")

    for idx in range(200):
        update = harness.create_mock_update_callback("back_to_menu", user_id=13000 + idx, update_id=200 + idx + 1)
        harness._attach_bot(update)
        await bot_kie.show_main_menu(update, context, source="callback-load")

    timeout_logs = [
        record
        for record in caplog.records
        if "MENU_DEP_TIMEOUT" in record.message or "MAIN_MENU_BUILD_TIMEOUT" in record.message
    ]
    assert not timeout_logs
