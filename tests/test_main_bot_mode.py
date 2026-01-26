import pytest

from app.main import get_bot_mode, main


def test_main_bot_mode_defaults_to_web_when_port_and_webhook(monkeypatch):
    monkeypatch.delenv("BOT_MODE", raising=False)
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.com")
    assert get_bot_mode() == "web"


def test_main_bot_mode_invalid_raises(monkeypatch):
    monkeypatch.setenv("BOT_MODE", "auto")
    with pytest.raises(ValueError):
        get_bot_mode()


@pytest.mark.asyncio
async def test_main_webhook_mode_exits(monkeypatch):
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("KIE_API_KEY", "kie")
    monkeypatch.delenv("WEBHOOK_BASE_URL", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    async def _stub_boot(*_args, **_kwargs):
        return {"result": "OK", "meta": {}, "summary": {}}

    async def _stub_init_storage():
        return True

    monkeypatch.setattr("app.main.run_boot_diagnostics", _stub_boot)
    monkeypatch.setattr("app.main.log_boot_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.main.initialize_storage", _stub_init_storage)
    monkeypatch.setattr("app.main.validate_config", lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as excinfo:
        await main()
    assert excinfo.value.code == 1
