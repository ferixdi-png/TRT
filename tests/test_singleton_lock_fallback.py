from types import SimpleNamespace

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
