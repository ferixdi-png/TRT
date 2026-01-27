from __future__ import annotations

import asyncio
import time

from bot_kie import MINIMAL_MENU_TEXT
from app.utils.singleton_lock import acquire_singleton_lock, release_singleton_lock


async def _wait_for_message(harness, timeout_s: float) -> dict:
    async def _poll() -> dict:
        while not harness.outbox.messages:
            await asyncio.sleep(0.01)
        return harness.outbox.messages[0]

    return await asyncio.wait_for(_poll(), timeout=timeout_s)


async def _send_start(harness, *, user_id: int, update_id: int) -> object:
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
            "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
        },
    }
    return await harness._send_payload(payload, request_id="corr-webhook-test")


async def test_webhook_ack_under_slow_storage(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("WEBHOOK_ACK_MAX_MS", "500")
    monkeypatch.setenv("START_FALLBACK_MAX_MS", "800")
    monkeypatch.setenv("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", "5000")

    start_ts = time.monotonic()
    response = await _send_start(webhook_harness, user_id=101, update_id=5001)
    ack_ms = (time.monotonic() - start_ts) * 1000

    assert response.status == 200
    assert ack_ms < 500

    message = await _wait_for_message(webhook_harness, timeout_s=1.0)
    assert MINIMAL_MENU_TEXT in message["text"]


async def test_correlation_flush_never_blocks_handlers(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("START_FALLBACK_MAX_MS", "800")
    monkeypatch.setenv("TRT_FAULT_INJECT_CORR_FLUSH_SLEEP_MS", "10000")

    start_ts = time.monotonic()
    response = await _send_start(webhook_harness, user_id=102, update_id=5002)
    ack_ms = (time.monotonic() - start_ts) * 1000

    assert response.status == 200
    assert ack_ms < 500

    await _wait_for_message(webhook_harness, timeout_s=1.0)


async def test_menu_build_timeout_degrades_gracefully(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("START_FALLBACK_MAX_MS", "500")
    monkeypatch.setenv("TRT_FAULT_INJECT_MENU_SLEEP_MS", "5000")

    response = await _send_start(webhook_harness, user_id=103, update_id=5003)
    assert response.status == 200

    message = await _wait_for_message(webhook_harness, timeout_s=1.0)
    assert MINIMAL_MENU_TEXT in message["text"]


async def test_webhook_ack_under_telegram_connect_timeout(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("START_FALLBACK_MAX_MS", "800")
    monkeypatch.setenv("TRT_FAULT_INJECT_TELEGRAM_CONNECT_TIMEOUT", "1")

    start_ts = time.monotonic()
    response = await _send_start(webhook_harness, user_id=104, update_id=5004)
    ack_ms = (time.monotonic() - start_ts) * 1000

    assert response.status == 200
    assert ack_ms < 500


async def test_start_placeholder_fast_under_storage_timeout(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("START_PLACEHOLDER_TIMEOUT_SECONDS", "1.0")
    monkeypatch.setenv("START_PLACEHOLDER_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("START_FORCE_PLACEHOLDER", "1")

    async def slow_get_user_language(_user_id: int) -> str:
        await asyncio.sleep(2.0)
        return "ru"

    monkeypatch.setattr(
        "app.services.user_service.get_user_language",
        slow_get_user_language,
    )

    start_ts = time.monotonic()
    response = await _send_start(webhook_harness, user_id=106, update_id=5006)
    ack_ms = (time.monotonic() - start_ts) * 1000

    assert response.status == 200
    assert ack_ms < 500

    message = await _wait_for_message(webhook_harness, timeout_s=1.0)
    assert MINIMAL_MENU_TEXT in message["text"]


async def test_webhook_ack_under_correlation_lock_busy(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("START_FALLBACK_MAX_MS", "800")

    class BusyLockStorage:
        def __init__(self) -> None:
            self.calls = 0

        async def update_json_file(self, *_args, **_kwargs):
            self.calls += 1
            return {}

    busy_storage = BusyLockStorage()

    monkeypatch.setattr(
        "app.observability.correlation_store._resolve_storage",
        lambda _storage=None: busy_storage,
    )

    start_ts = time.monotonic()
    response = await _send_start(webhook_harness, user_id=105, update_id=5005)
    ack_ms = (time.monotonic() - start_ts) * 1000

    assert response.status == 200
    assert ack_ms < 500

async def test_redis_lock_timeout_fallback_fast(monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setenv("REDIS_LOCK_CONNECT_TIMEOUT_MS", "100")
    monkeypatch.setenv("REDIS_LOCK_MAX_WAIT_MS", "200")
    monkeypatch.setenv("SINGLETON_LOCK_ALLOW_FILE_FALLBACK", "1")
    monkeypatch.setenv("SINGLETON_LOCK_DIR", str(tmp_path))

    start_ts = time.monotonic()
    acquired = await acquire_singleton_lock(require_lock=False)
    elapsed_ms = (time.monotonic() - start_ts) * 1000

    await release_singleton_lock()

    assert elapsed_ms < 300
    assert acquired is True
