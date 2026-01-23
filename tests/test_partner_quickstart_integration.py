import os

import pytest
from app.storage.postgres_storage import PostgresStorage
from app.utils.distributed_lock import build_redis_lock_key, distributed_lock


async def _clear_partner_rows(storage: PostgresStorage, partner_id: str) -> None:
    pool = await storage._get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM storage_json WHERE partner_id=$1", partner_id)


@pytest.mark.asyncio
async def test_postgres_tenant_isolation_and_restart():
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL not set")

    storage_a = PostgresStorage(dsn, partner_id="tenant-a")
    storage_b = PostgresStorage(dsn, partner_id="tenant-b")

    try:
        await _clear_partner_rows(storage_a, "tenant-a")
        await _clear_partner_rows(storage_b, "tenant-b")

        await storage_a.set_user_balance(1001, 50.0)
        await storage_a.increment_free_generations(1001)
        await storage_a.add_generation_to_history(
            1001,
            model_id="demo-model",
            model_name="Demo",
            params={"prompt": "hello"},
            result_urls=["https://example.com/result"],
            price=10.0,
        )
        payment_id = await storage_a.add_payment(1001, 15.0, "test")

        assert await storage_b.get_user_balance(1001) == 0.0
        assert await storage_b.get_user_free_generations_today(1001) == 0
        assert await storage_b.get_user_generations_history(1001) == []
        assert await storage_b.get_payment(payment_id) is None

        await storage_a.close()
        storage_restart = PostgresStorage(dsn, partner_id="tenant-a")
        try:
            assert await storage_restart.get_user_balance(1001) == 50.0
            history = await storage_restart.get_user_generations_history(1001)
            assert history
        finally:
            await storage_restart.close()
    finally:
        await _clear_partner_rows(storage_a, "tenant-a")
        await _clear_partner_rows(storage_b, "tenant-b")
        await storage_a.close()
        await storage_b.close()


@pytest.mark.asyncio
async def test_redis_lock_tenant_scoped(monkeypatch):
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        pytest.skip("REDIS_URL not set")
    try:
        import redis.asyncio as redis
    except Exception:
        pytest.skip("redis client not available")

    client = redis.from_url(redis_url, decode_responses=True)
    try:
        monkeypatch.setenv("BOT_INSTANCE_ID", "tenant-alpha")
        async with distributed_lock("balance:1", ttl_seconds=10, wait_seconds=1) as acquired:
            assert acquired
            key = build_redis_lock_key("balance:1")
            assert await client.get(key) is not None

        monkeypatch.setenv("BOT_INSTANCE_ID", "tenant-beta")
        async with distributed_lock("balance:1", ttl_seconds=10, wait_seconds=1) as acquired:
            assert acquired
            key = build_redis_lock_key("balance:1")
            assert await client.get(key) is not None
    finally:
        await client.close()
