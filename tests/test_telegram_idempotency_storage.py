import asyncio

import bot_kie

from app.storage.factory import get_storage, reset_storage


async def test_telegram_send_idempotency_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("STORAGE_MODE", "json")
    reset_storage()

    storage = get_storage()
    bot_kie.storage = storage
    bot_kie._telegram_idempotency_cache.clear()
    bot_kie._telegram_idempotency_inflight.clear()

    calls = {"count": 0}

    async def request_fn():
        await asyncio.sleep(0)
        calls["count"] += 1
        return {"ok": True}

    result, timeout_seen = await bot_kie._run_telegram_request(
        "test_send",
        correlation_id="corr-test",
        timeout_s=0.5,
        retry_attempts=1,
        retry_backoff_s=0.01,
        request_fn=request_fn,
        update_id=42,
        chat_id=99,
        message_id=7,
    )
    assert result is not None
    assert timeout_seen is False
    assert calls["count"] == 1

    result_second, timeout_seen_second = await bot_kie._run_telegram_request(
        "test_send",
        correlation_id="corr-test",
        timeout_s=0.5,
        retry_attempts=1,
        retry_backoff_s=0.01,
        request_fn=request_fn,
        update_id=42,
        chat_id=99,
        message_id=7,
    )
    assert result_second is None
    assert timeout_seen_second is False
    assert calls["count"] == 1
