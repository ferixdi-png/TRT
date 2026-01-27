import asyncio
import contextlib
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import telegram

import bot_kie
from app.bot_mode import ensure_webhook_mode


class _HangingBot:
    def __init__(self, token: str, *, cancelled_event: asyncio.Event) -> None:
        self.token = token
        self._cancelled_event = cancelled_event

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_webhook_info(self, **kwargs):
        return SimpleNamespace(url="", pending_update_count=0)

    async def set_webhook(self, **kwargs):
        try:
            await asyncio.sleep(10)
            return True
        except asyncio.CancelledError:
            self._cancelled_event.set()
            raise


@pytest.mark.asyncio
async def test_webhook_setter_hard_timeout(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("WEBHOOK_SET_CYCLE_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("WEBHOOK_SET_BACKOFF_BASE_SECONDS", "0.1")
    monkeypatch.setenv("WEBHOOK_SET_BACKOFF_CAP_SECONDS", "0.1")
    monkeypatch.setenv("WEBHOOK_SET_LONG_SLEEP_SECONDS", "1.0")
    monkeypatch.setenv("WEBHOOK_SET_MAX_FAST_RETRIES", "1")
    monkeypatch.setenv("AUTO_SET_WEBHOOK", "1")
    monkeypatch.setenv("TEST_MODE", "1")
    cancelled_event = asyncio.Event()

    def _build_bot(token: str, **kwargs):
        return _HangingBot(token, cancelled_event=cancelled_event)

    monkeypatch.setattr(telegram, "Bot", _build_bot)

    start = time.monotonic()
    with caplog.at_level(logging.WARNING):
        task = asyncio.create_task(bot_kie._run_webhook_setter_loop("https://example.com/webhook"))
        try:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if any("WEBHOOK_SETTER_FAIL" in record.message for record in caplog.records):
                    break
                await asyncio.sleep(0.05)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    elapsed = time.monotonic() - start
    assert elapsed < 3.0
    fail_logs = [record.message for record in caplog.records if "WEBHOOK_SETTER_FAIL" in record.message]
    assert fail_logs
    assert "error_type=Timeout" in fail_logs[0]
    duration_token = "duration_ms="
    duration_ms = None
    for part in fail_logs[0].split():
        if part.startswith(duration_token):
            duration_ms = int(part[len(duration_token):])
            break
    assert duration_ms is not None
    assert duration_ms < 3000
    await asyncio.wait_for(cancelled_event.wait(), timeout=0.5)
    assert "next_retry_s=" in fail_logs[0]


@pytest.mark.asyncio
async def test_webhook_setter_already_set_skips():
    mock_bot = AsyncMock()
    mock_bot.get_webhook_info.return_value = SimpleNamespace(
        url="https://example.com/webhook",
        pending_update_count=0,
    )

    result = await ensure_webhook_mode(mock_bot, "https://example.com/webhook")
    assert result is True
    mock_bot.set_webhook.assert_not_called()


def test_auto_set_webhook_default_on_render(monkeypatch):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.delenv("AUTO_SET_WEBHOOK", raising=False)

    assert bot_kie._auto_set_webhook_enabled() is False

    monkeypatch.setenv("AUTO_SET_WEBHOOK", "1")
    assert bot_kie._auto_set_webhook_enabled() is True

    monkeypatch.setenv("AUTO_SET_WEBHOOK", "0")
    assert bot_kie._auto_set_webhook_enabled() is False


@pytest.mark.asyncio
async def test_warmup_timeout_cancels_task(monkeypatch):
    monkeypatch.setenv("GEN_TYPE_MENU_WARMUP_TIMEOUT_SECONDS", "2.0")
    cancelled = asyncio.Event()

    async def slow_warmup():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    start = time.monotonic()
    await bot_kie.warm_generation_type_menu_cache(
        warmup_fn=slow_warmup,
        timeout_s=2.0,
        retry_attempts=1,
        force=True,
        correlation_id="TEST",
    )
    elapsed = time.monotonic() - start

    assert elapsed < 2.5
    await asyncio.wait_for(cancelled.wait(), timeout=0.5)
    assert bot_kie._GEN_TYPE_MENU_WARMUP_STATE.get("task") is None


@pytest.mark.asyncio
async def test_warmup_hard_timeout_with_blocking_to_thread(monkeypatch):
    monkeypatch.setenv("GEN_TYPE_MENU_WARMUP_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setattr(
        bot_kie,
        "get_models_cached_only",
        lambda: [{"id": "m1", "model_type": "text_to_image"}],
    )

    def _blocking_gen_type_lookup(gen_type: str):
        time.sleep(0.5)
        return [], "miss"

    monkeypatch.setattr(bot_kie, "get_visible_models_by_generation_type_cached", _blocking_gen_type_lookup)

    start = time.monotonic()
    await bot_kie.warm_generation_type_menu_cache(
        timeout_s=0.05,
        retry_attempts=1,
        force=True,
        correlation_id="TEST",
    )
    elapsed = time.monotonic() - start

    assert elapsed < 0.3
    assert bot_kie._GEN_TYPE_MENU_WARMUP_STATE.get("task") is None


@pytest.mark.asyncio
async def test_boot_does_not_block_ready(monkeypatch):
    monkeypatch.setattr(bot_kie, "BOOT_WARMUP_BUDGET_SECONDS", 1.0)

    async def slow_warmup(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(bot_kie, "_warm_models_cache", slow_warmup)
    monkeypatch.setattr(bot_kie, "warm_generation_type_menu_cache", slow_warmup)

    start = time.monotonic()
    await bot_kie._run_boot_warmups(correlation_id="TEST")
    elapsed = time.monotonic() - start

    assert elapsed < 2.0
    assert bot_kie._BOOT_WARMUP_STATE["budget_exceeded"] is True
