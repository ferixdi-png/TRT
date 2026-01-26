import pytest

from app.main import get_bot_mode


def test_main_bot_mode_defaults_to_web_when_port_and_webhook(monkeypatch):
    monkeypatch.delenv("BOT_MODE", raising=False)
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.com")
    assert get_bot_mode() == "web"


def test_main_bot_mode_invalid_raises(monkeypatch):
    monkeypatch.setenv("BOT_MODE", "auto")
    with pytest.raises(ValueError):
        get_bot_mode()
