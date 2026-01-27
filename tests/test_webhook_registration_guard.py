import logging
from types import SimpleNamespace

import pytest
import telegram

import bot_kie


class _FakeBot:
    def __init__(self, token: str, *, info: SimpleNamespace) -> None:
        self.token = token
        self._info = info
        self.set_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_webhook_info(self, **kwargs):
        return self._info

    async def set_webhook(self, **kwargs):
        self.set_calls.append(kwargs)
        return True


@pytest.mark.asyncio
async def test_webhook_setter_cycle_sets_webhook_once(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("WEBHOOK_SET_CYCLE_TIMEOUT_SECONDS", "2.5")
    webhook_info = SimpleNamespace(
        url="",
        pending_update_count=0,
        last_error_date=None,
        last_error_message=None,
    )
    created = {}

    def _build_bot(token: str, **kwargs):
        created["bot"] = _FakeBot(token, info=webhook_info)
        return created["bot"]

    monkeypatch.setattr(telegram, "Bot", _build_bot)

    result = await bot_kie._run_webhook_setter_cycle(
        "https://example.com/webhook",
        attempt_cycle=1,
        cycle_timeout_s=2.5,
    )

    assert result["ok"] is True
    assert created["bot"].set_calls
    assert created["bot"].set_calls[0]["url"] == "https://example.com/webhook"


@pytest.mark.asyncio
async def test_webhook_fail_fast_logs_how_to_fix(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    webhook_info = SimpleNamespace(
        url="",
        pending_update_count=0,
        last_error_date=None,
        last_error_message=None,
    )
    bot = _FakeBot("test-token", info=webhook_info)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc:
            await bot_kie._fail_fast_if_webhook_missing(bot, "https://example.com/webhook")

    assert exc.value.code == 1
    assert any("HOW_TO_FIX curl" in record.message for record in caplog.records)
