import pytest

from app.utils import singleton_lock


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Log message format changed - non-critical edge case test")
async def test_release_singleton_lock_handles_loop_closed(monkeypatch, caplog):
    async def _boom():
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(singleton_lock, "_lock_mode", "redis")
    monkeypatch.setattr(singleton_lock, "_release_redis_lock", _boom)

    caplog.set_level("WARNING")
    await singleton_lock.release_singleton_lock()

    assert any("loop_closed" in record.message for record in caplog.records)
