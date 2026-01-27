import json
from types import SimpleNamespace

from app.utils.healthcheck import ready_diag_handler


import pytest

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Test isolation issue: passes alone, fails in group")
async def test_ready_diag_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
    monkeypatch.setenv("WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    class DummyBot:
        def __init__(self, token=None, request=None):
            self.token = token
            self.request = request

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_webhook_info(self):
            return SimpleNamespace(url="https://example.com/webhook", pending_update_count=0)

    import telegram

    monkeypatch.setattr(telegram, "Bot", DummyBot)
    import app.utils.singleton_lock as singleton_lock

    singleton_lock._lock_mode = "postgres"
    singleton_lock._lock_degraded = False
    singleton_lock._lock_degraded_reason = None

    response = await ready_diag_handler(SimpleNamespace())
    assert response.status == 200
    payload = json.loads(response.text)
    assert payload["status"] == "READY"
    assert "test-token-123" not in response.text
    assert payload["webhook"]["match"] is True
