"""Tests for cancel/job_id handling and debounce window."""

from types import SimpleNamespace

import pytest
from telegram.ext import CallbackQueryHandler

import bot_kie
from bot_kie import button_callback
from app.observability.cancel_metrics import reset_metrics, get_metrics_snapshot


@pytest.mark.asyncio
async def test_parse_cancel_callback_data():
    assert bot_kie._parse_cancel_callback("cancel:job-123") == "job-123"
    assert bot_kie._parse_cancel_callback("cancel:") is None
    assert bot_kie._parse_cancel_callback("cancel") is None


def test_cancel_click_debounce_window():
    user_id = 777
    now_ms = bot_kie._now_ms()
    bot_kie._set_user_ui_action(user_id, "cancel_click", now_ms - 2000)
    assert bot_kie._is_recent_cancel_click(user_id, now_ms)
    bot_kie._set_user_ui_action(user_id, "cancel_click", now_ms - 4000)
    assert not bot_kie._is_recent_cancel_click(user_id, now_ms)


@pytest.mark.asyncio
async def test_request_job_cancel_valid_job(harness):
    reset_metrics()
    user_id = 12345
    job_id = "job-test-123"
    bot_kie._save_jobs_registry({})
    bot_kie._set_user_ui_action(user_id, "cancel_click", bot_kie._now_ms())
    bot_kie._create_job_record(
        job_id=job_id,
        user_id=user_id,
        chat_id=user_id,
        message_id=1,
        model_id="test-model",
        correlation_id="corr-test",
        state="running",
        start_ts_ms=bot_kie._now_ms(),
    )
    session = bot_kie.user_sessions.ensure(user_id)
    session["job_id"] = job_id
    session["job_state"] = "running"

    harness.add_handler(CallbackQueryHandler(button_callback))
    update = harness.create_mock_update_callback(f"cancel:{job_id}", user_id=user_id)
    harness._attach_bot(update)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    accepted = await bot_kie._request_job_cancel(
        update=update,
        context=context,
        job_id=job_id,
        user_id=user_id,
        user_lang="ru",
        callback_data=f"cancel:{job_id}",
        query=update.callback_query,
        correlation_id="corr-test",
        state_source="callback",
    )
    assert accepted
    job_record = bot_kie._get_job_record(job_id)
    assert job_record["state"] == "cancel_requested"


@pytest.mark.asyncio
async def test_request_job_cancel_rejects_missing_job(harness):
    reset_metrics()
    user_id = 54321
    update = harness.create_mock_update_callback("cancel:missing", user_id=user_id)
    harness._attach_bot(update)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    accepted = await bot_kie._request_job_cancel(
        update=update,
        context=context,
        job_id=None,
        user_id=user_id,
        user_lang="ru",
        callback_data="cancel:missing",
        query=update.callback_query,
        correlation_id="corr-test",
        state_source="callback",
    )
    assert not accepted
    metrics = get_metrics_snapshot()
    assert metrics["cancel_without_job_total"] >= 1
