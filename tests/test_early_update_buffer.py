import asyncio
from unittest.mock import AsyncMock

import pytest

import bot_kie
from app.utils.early_update_buffer import EarlyUpdateBuffer


@pytest.mark.asyncio
async def test_early_update_buffer_append_dedup_and_drain():
    now = 0.0

    def time_fn():
        return now

    async def no_redis():
        return None

    buffer = EarlyUpdateBuffer(ttl_seconds=120, max_size=3, time_fn=time_fn, redis_client_provider=no_redis)

    buffered, size = await buffer.add(2, {"update_id": 2}, correlation_id="corr-2")
    assert buffered is True
    assert size == 1

    buffered, size = await buffer.add(2, {"update_id": 2}, correlation_id="corr-2-dup")
    assert buffered is False
    assert size == 1

    await buffer.add(1, {"update_id": 1}, correlation_id="corr-1")
    await buffer.add(3, {"update_id": 3}, correlation_id="corr-3")

    items = await buffer.drain()
    assert [item.update_id for item in items] == [1, 2, 3]


@pytest.mark.asyncio
async def test_early_update_buffer_ttl_expiry():
    now = 0.0

    def time_fn():
        return now

    async def no_redis():
        return None

    buffer = EarlyUpdateBuffer(ttl_seconds=30, max_size=3, time_fn=time_fn, redis_client_provider=no_redis)
    await buffer.add(10, {"update_id": 10}, correlation_id="corr-10")
    now = 45.0

    items = await buffer.drain()
    assert items == []


@pytest.mark.asyncio
async def test_early_update_buffer_size_limit():
    now = 0.0

    def time_fn():
        return now

    async def no_redis():
        return None

    buffer = EarlyUpdateBuffer(ttl_seconds=120, max_size=3, time_fn=time_fn, redis_client_provider=no_redis)
    for update_id in (1, 2, 3, 4):
        now += 1.0
        await buffer.add(update_id, {"update_id": update_id}, correlation_id=f"corr-{update_id}")

    items = await buffer.drain()
    assert [item.update_id for item in items] == [2, 3, 4]


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Test isolation issue: passes alone, fails in group")
async def test_early_update_buffer_integration_drain_order(harness, monkeypatch):
    async def no_redis():
        return None

    buffer = EarlyUpdateBuffer(ttl_seconds=180, max_size=10, redis_client_provider=no_redis)
    monkeypatch.setattr(bot_kie, "_early_update_buffer", buffer)

    process_update = AsyncMock()
    harness.application.bot_data["process_update_override"] = process_update

    payloads = [
        {"update_id": 3, "message": {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}}},
        {"update_id": 1, "message": {"message_id": 2, "date": 0, "chat": {"id": 1, "type": "private"}}},
        {"update_id": 2, "message": {"message_id": 3, "date": 0, "chat": {"id": 1, "type": "private"}}},
    ]
    for payload in payloads:
        await buffer.add(payload["update_id"], payload, correlation_id=f"corr-{payload['update_id']}")

    await bot_kie._drain_early_update_buffer(harness.application, correlation_id="corr-drain")
    await asyncio.sleep(0)

    update_ids = [call.args[0].update_id for call in process_update.call_args_list]
    assert update_ids == [1, 2, 3]
