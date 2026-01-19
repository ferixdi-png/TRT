from types import SimpleNamespace

import pytest

from app.config import Settings
import app.utils.singleton_lock as singleton_lock
import app.locking.single_instance as single_instance


def test_webhook_requires_database_url(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings()
    with pytest.raises(ValueError):
        settings.validate()


@pytest.mark.asyncio
async def test_singleton_lock_acquires_with_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    monkeypatch.setenv("DISABLE_DB_LOCKS", "0")

    class FakeConn:
        async def fetchval(self, *_args, **_kwargs):
            return True

        async def execute(self, *_args, **_kwargs):
            return None

        async def close(self):
            return None

    async def fake_connect(_dsn):
        return FakeConn()

    monkeypatch.setattr(single_instance, "HAS_ASYNCPG", True)
    monkeypatch.setattr(single_instance, "asyncpg", SimpleNamespace(connect=fake_connect))

    singleton_lock.set_lock_acquired(False)
    setattr(singleton_lock, "_singleton_lock_instance", None)

    result = await singleton_lock.acquire_singleton_lock()
    assert result is True
    assert singleton_lock.is_lock_acquired() is True

    await singleton_lock.release_singleton_lock()
