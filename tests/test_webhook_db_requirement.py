import pytest

from app.config import Settings
import app.utils.singleton_lock as singleton_lock


def test_webhook_allows_db_only_storage(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("STORAGE_MODE", "github_json")
    monkeypatch.setenv("GITHUB_ONLY_STORAGE", "true")
    settings = Settings()
    settings.validate()
    assert settings.get_storage_mode() == "db"


@pytest.mark.asyncio
async def test_singleton_lock_uses_file_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("DISABLE_DB_LOCKS", "0")
    monkeypatch.setenv("SINGLETON_LOCK_DIR", str(tmp_path))
    singleton_lock.set_lock_acquired(False)
    result = await singleton_lock.acquire_singleton_lock(require_lock=True)
    assert result is True
    assert singleton_lock.is_lock_acquired() is True
    await singleton_lock.release_singleton_lock()
