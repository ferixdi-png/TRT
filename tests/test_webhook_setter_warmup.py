import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import telegram

import bot_kie
from app.bot_mode import ensure_webhook_mode


class _HangingBot:
    last_instance = None

    def __init__(self, token: str, **kwargs) -> None:
        self.token = token
        self.cancelled = False
        _HangingBot.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_webhook_info(self, **kwargs):
        return SimpleNamespace(url="", pending_update_count=0)

    async def set_webhook(self, **kwargs):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return True


@pytest.mark.asyncio
async def test_webhook_setter_hard_timeout(monkeypatch):
    monkeypatch.setenv("AUTO_SET_WEBHOOK", "1")
    monkeypatch.setenv("WEBHOOK_SET_CYCLE_TIMEOUT_SECONDS", "2.8")
    monkeypatch.setenv("WEBHOOK_SET_CONNECT_TIMEOUT_SECONDS", "2.8")
    monkeypatch.setenv("WEBHOOK_SET_READ_TIMEOUT_SECONDS", "2.8")
    monkeypatch.setenv("WEBHOOK_SET_WRITE_TIMEOUT_SECONDS", "2.8")
    monkeypatch.setenv("WEBHOOK_SET_POOL_TIMEOUT_SECONDS", "2.8")
    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setattr(telegram, "Bot", _HangingBot)

    result = await bot_kie._run_webhook_setter_cycle(
        "https://example.com/webhook",
        attempt_cycle=1,
        cycle_timeout_s=2.8,
    )

    assert result["ok"] is False
    assert result["error_type"] == "TimeoutError"
    assert result["duration_ms"] < 3000
    assert _HangingBot.last_instance is not None
    assert _HangingBot.last_instance.cancelled is True


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
