import asyncio
import time
import types
import sys

import pytest

from app.utils import singleton_lock


class FakeRedisAsync:
    def __init__(self):
        self.set_calls = []
        self.eval_calls = []
        self.closed = False

    async def set(self, key, value, nx=True, ex=None):
        self.set_calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        return True

    async def eval(self, script, numkeys, key, value, ttl):
        self.eval_calls.append({"key": key, "value": value, "ttl": ttl})
        return 1

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_redis_lock_renews_ttl(monkeypatch):
    fake_redis = FakeRedisAsync()

    async def _from_url(url, decode_responses=True):
        return fake_redis

    fake_asyncio_module = types.SimpleNamespace(from_url=_from_url)
    redis_package = types.SimpleNamespace(asyncio=fake_asyncio_module)

    singleton_lock._redis_client = None
    singleton_lock._redis_lock_key = None
    singleton_lock._redis_lock_value = None
    singleton_lock._redis_renew_task = None
    singleton_lock._redis_renew_stop = None
    singleton_lock._redis_renew_loop = None
    singleton_lock._redis_renew_thread = None
    singleton_lock._lock_acquired = False
    singleton_lock._lock_mode = "none"

    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("REDIS_LOCK_TTL_SECONDS", "6")
    monkeypatch.setenv("REDIS_LOCK_RENEW_INTERVAL_SECONDS", "1")
    monkeypatch.setitem(sys.modules, "redis", redis_package)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio_module)

    acquired = await singleton_lock.acquire_singleton_lock()
    assert acquired is True

    start = time.monotonic()
    while time.monotonic() - start < 2:
        if fake_redis.eval_calls:
            break
        await asyncio.sleep(0.05)

    await singleton_lock.release_singleton_lock()

    assert fake_redis.set_calls
    assert fake_redis.eval_calls
    assert fake_redis.eval_calls[0]["ttl"] == 6
