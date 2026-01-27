import asyncio

import app.utils.singleton_lock as singleton_lock
from app.utils.singleton_lock import (
    acquire_singleton_lock,
    get_lock_mode,
    release_singleton_lock,
    set_lock_acquired,
)


async def test_singleton_lock_file_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DISABLE_DB_LOCKS", "0")
    monkeypatch.setenv("SINGLETON_LOCK_DIR", str(tmp_path))

    set_lock_acquired(False)
    lock_acquired = await acquire_singleton_lock(require_lock=True)
    assert lock_acquired is True
    assert get_lock_mode() == "file"

    await release_singleton_lock()


async def test_singleton_lock_disabled_is_explicit(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DISABLE_DB_LOCKS", "1")
    monkeypatch.setenv("SINGLETON_LOCK_DIR", str(tmp_path))

    set_lock_acquired(False)
    lock_acquired = await acquire_singleton_lock(require_lock=True)
    assert lock_acquired is True
    assert get_lock_mode() == "disabled"


async def test_singleton_lock_fallback_to_postgres(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("DISABLE_DB_LOCKS", "0")
    monkeypatch.setenv("SINGLETON_LOCK_ALLOW_FILE_FALLBACK", "0")
    monkeypatch.setenv("ENV", "production")

    async def fake_redis_lock(*args, **kwargs):
        return False

    async def fake_postgres_lock(*args, **kwargs):
        return True

    singleton_lock._lock_mode = "none"
    singleton_lock._lock_degraded = False
    singleton_lock._lock_degraded_reason = None
    set_lock_acquired(False)
    monkeypatch.setattr(singleton_lock, "_acquire_redis_lock", fake_redis_lock)
    monkeypatch.setattr(singleton_lock, "_acquire_postgres_lock", fake_postgres_lock)

    lock_acquired = await acquire_singleton_lock(require_lock=True)
    assert lock_acquired is True
    assert get_lock_mode() == "postgres"
    await release_singleton_lock()


async def test_singleton_lock_parallel_instances(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("DISABLE_DB_LOCKS", "0")
    monkeypatch.setenv("SINGLETON_LOCK_ALLOW_FILE_FALLBACK", "0")
    monkeypatch.setenv("ENV", "production")

    async def fake_redis_lock(*args, **kwargs):
        return False

    counter = {"count": 0}

    async def fake_postgres_lock(*args, **kwargs):
        await asyncio.sleep(0)
        counter["count"] += 1
        return counter["count"] == 1

    singleton_lock._lock_mode = "none"
    singleton_lock._lock_degraded = False
    singleton_lock._lock_degraded_reason = None
    set_lock_acquired(False)
    monkeypatch.setattr(singleton_lock, "_acquire_redis_lock", fake_redis_lock)
    monkeypatch.setattr(singleton_lock, "_acquire_postgres_lock", fake_postgres_lock)

    results = await asyncio.gather(
        acquire_singleton_lock(require_lock=True),
        acquire_singleton_lock(require_lock=True),
    )
    assert results.count(True) == 1
    assert results.count(False) == 1
    await release_singleton_lock()
