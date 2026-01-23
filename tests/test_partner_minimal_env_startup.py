import pytest

from app.bootstrap import DependencyContainer
from app.config import Settings, reset_settings
from app.storage.factory import reset_storage


@pytest.mark.asyncio
async def test_bot_starts_with_minimal_partner_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_ID", "12345")
    monkeypatch.setenv("BOT_INSTANCE_ID", "partner-minimal")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.com")
    monkeypatch.delenv("KIE_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STORAGE_MODE", raising=False)
    reset_settings()
    reset_storage()

    deps = DependencyContainer()
    await deps.initialize(Settings())

    assert deps.storage is not None
