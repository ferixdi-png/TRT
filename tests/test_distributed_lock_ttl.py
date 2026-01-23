import asyncio
import time

import pytest

from app.utils import distributed_lock as lock_mod


class FakeRedis:
    def __init__(self):
        self._store = {}

    async def set(self, key, value, nx=False, ex=None):
        now = time.monotonic()
        record = self._store.get(key)
        if record:
            stored_value, expires_at = record
            if expires_at is not None and now >= expires_at:
                self._store.pop(key, None)
                record = None
        if nx and record:
            return None
        expires_at = now + ex if ex is not None else None
        self._store[key] = (value, expires_at)
        return True

    async def get(self, key):
        now = time.monotonic()
        record = self._store.get(key)
        if not record:
            return None
        value, expires_at = record
        if expires_at is not None and now >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def eval(self, _script, _keys, key, value):
        current = await self.get(key)
        if current == value:
            self._store.pop(key, None)
            return 1
        return 0


@pytest.mark.asyncio
async def test_distributed_lock_ttl_expires(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(lock_mod, "_redis_client", fake)
    monkeypatch.setattr(lock_mod, "_redis_available", True)
    monkeypatch.setattr(lock_mod, "_redis_initialized", True)

    lock_key = lock_mod.build_redis_lock_key("gen:test")
    await fake.set(lock_key, "stuck", nx=True, ex=0.2)

    async with lock_mod.distributed_lock("gen:test", ttl_seconds=1, wait_seconds=0.1, max_attempts=1) as result:
        assert not result

    await asyncio.sleep(0.25)

    async with lock_mod.distributed_lock("gen:test", ttl_seconds=1, wait_seconds=0.2, max_attempts=2) as result:
        assert result
