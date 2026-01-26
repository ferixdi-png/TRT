import asyncio
import types

import pytest

from app.utils import distributed_lock


class SlowRedis:
    def __init__(self, delay: float):
        self.delay = delay

    async def ping(self):
        await asyncio.sleep(self.delay)


@pytest.mark.asyncio
async def test_distributed_lock_connect_timeout_fast(monkeypatch):
    slow_client = SlowRedis(delay=0.5)

    def from_url(*args, **kwargs):
        return slow_client

    fake_asyncio = types.SimpleNamespace(from_url=from_url)
    monkeypatch.setitem(__import__("sys").modules, "redis.asyncio", fake_asyncio)
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("REDIS_CONNECT_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("REDIS_READ_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("REDIS_CONNECT_DEADLINE_SECONDS", "0.02")

    distributed_lock._redis_initialized = False
    distributed_lock._redis_available = False
    distributed_lock._redis_client = None

    result = await distributed_lock._init_redis()
    assert result is False
    assert distributed_lock.is_redis_available() is False
