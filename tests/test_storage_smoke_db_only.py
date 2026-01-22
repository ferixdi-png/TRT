import json

import pytest
import asyncpg

from app.storage.postgres_storage import PostgresStorage


class _FakeConn:
    def __init__(self, store):
        self._store = store

    async def execute(self, query, *args):
        if "INSERT INTO storage_json" in query:
            partner_id, filename, payload = args
            data = json.loads(payload) if isinstance(payload, str) else payload
            self._store[(partner_id, filename)] = data
        return None

    async def fetchrow(self, query, *args):
        if "SELECT payload FROM storage_json" in query:
            key = (args[0], args[1])
            if key not in self._store:
                return None
            return (self._store[key],)
        if "SELECT count(*) AS c FROM storage_json" in query:
            partner_id = args[0]
            count = sum(1 for (pid, _fname) in self._store.keys() if pid == partner_id)
            return (count,)
        return None


class _AcquireContext:
    def __init__(self, store):
        self._store = store
        self._conn = _FakeConn(store)

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, store):
        self._store = store
        self.closed = False

    def acquire(self):
        return _AcquireContext(self._store)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_postgres_storage_smoke(monkeypatch):
    store = {}

    async def _fake_create_pool(*_args, **_kwargs):
        return _FakePool(store)

    monkeypatch.setattr(asyncpg, "create_pool", _fake_create_pool)

    storage = PostgresStorage("postgresql://example", partner_id="smoke")
    await storage.write_json_file("user_balances.json", {"1": 10})
    payload = await storage.read_json_file("user_balances.json", default={})

    assert payload == {"1": 10}
    await storage.close()
