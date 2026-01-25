import json
import re

import pytest
from telegram.ext import CallbackQueryHandler

from app.observability.error_buffer import get_error_summary
from app.telegram_error_handler import ensure_error_handler_registered
from tests.ptb_harness import PTBHarness
from app.buttons.fallback import fallback_callback_handler


@pytest.mark.asyncio
async def test_router_exception_boundary_callback(caplog, monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    ensure_error_handler_registered(harness.application)

    async def boom(update, context):
        raise RuntimeError("router boom")

    async def ok(update, context):
        await update.callback_query.answer("ok", show_alert=False)

    harness.add_handler(CallbackQueryHandler(boom, pattern="^boom$"))
    harness.add_handler(CallbackQueryHandler(ok, pattern="^ok$"))

    caplog.set_level("INFO")
    update = harness.create_mock_update_callback("boom")
    harness._attach_bot(update)
    await harness.application.process_update(update)

    assert harness.outbox.callback_answers
    assert any(
        "⚠️ Техническая ошибка" in answer.get("text", "")
        for answer in harness.outbox.callback_answers
    )
    assert harness.outbox.messages
    error_message = next(
        (msg for msg in harness.outbox.messages if "⚠️ Временный сбой" in msg["text"]),
        None,
    )
    assert error_message is not None

    log_line = next((r.message for r in caplog.records if "ROUTER_FAIL" in r.message), None)
    assert log_line is not None
    payload = json.loads(log_line.split("ROUTER_FAIL", 1)[1].strip())
    assert payload["update_type"] == "callback_query"
    assert payload["stage"] == "router"

    corr_match = re.search(r"(corr-[\w-]+)", error_message["text"])
    assert corr_match
    summary = get_error_summary(corr_match.group(1))
    assert summary is not None

    ok_update = harness.create_mock_update_callback("ok")
    harness._attach_bot(ok_update)
    await harness.application.process_update(ok_update)

    await harness.teardown()


@pytest.mark.asyncio
async def test_unknown_callback_fallback_answers_and_menu(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    ensure_error_handler_registered(harness.application)

    async def fake_menu(*args, **kwargs):
        return None

    monkeypatch.setattr("bot_kie.ensure_main_menu", fake_menu)

    async def unknown(update, context):
        await fallback_callback_handler(
            update.callback_query.data,
            update,
            context,
            user_id=update.callback_query.from_user.id,
            user_lang="ru",
        )

    harness.add_handler(CallbackQueryHandler(unknown, pattern="^unknown$"))

    update = harness.create_mock_update_callback("unknown")
    harness._attach_bot(update)
    await harness.application.process_update(update)

    assert harness.outbox.callback_answers
    assert harness.outbox.messages
    assert "Кнопка устарела" in harness.outbox.messages[-1]["text"]

    await harness.teardown()
