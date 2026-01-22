import asyncio

import asyncpg

from app.storage.postgres_storage import PostgresStorage


class _FakeConn:
    def __init__(self, loop_id: int) -> None:
        self._loop_id = loop_id

    async def execute(self, *args, **kwargs):
        return None

    async def fetchrow(self, *args, **kwargs):
        return None


class _AcquireContext:
    def __init__(self, loop_id: int) -> None:
        self._loop_id = loop_id
        self._conn = _FakeConn(loop_id)

    async def __aenter__(self):
        current_loop_id = id(asyncio.get_running_loop())
        if current_loop_id != self._loop_id:
            raise RuntimeError("got Future attached to a different loop")
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, loop_id: int) -> None:
        self.loop_id = loop_id
        self.closed = False

    def acquire(self):
        return _AcquireContext(self.loop_id)

    async def close(self):
        self.closed = True


def _run_in_new_loop(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_postgres_storage_uses_pool_per_loop(monkeypatch):
    created_pools: list[_FakePool] = []

    async def _fake_create_pool(*args, **kwargs):
        loop_id = id(asyncio.get_running_loop())
        pool = _FakePool(loop_id)
        created_pools.append(pool)
        return pool

    monkeypatch.setattr(asyncpg, "create_pool", _fake_create_pool)
    storage = PostgresStorage("postgresql://example", partner_id="test")

    _run_in_new_loop(storage.read_json_file("sample.json", {}))
    _run_in_new_loop(storage.read_json_file("sample.json", {}))
    _run_in_new_loop(storage.close())

    assert len(created_pools) == 2
    assert created_pools[0].loop_id != created_pools[1].loop_id
