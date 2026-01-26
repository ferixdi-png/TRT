import asyncio
import time

import pytest

from tests.webhook_harness import WebhookHarness


@pytest.mark.asyncio
async def test_webhook_ack_fast_on_telegram_timeout(monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("TRT_FAULT_INJECT_TELEGRAM_CONNECT_TIMEOUT", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")

    harness = WebhookHarness()
    await harness.setup()
    try:
        start_ts = time.monotonic()
        response = await harness.send_message(user_id=9002, text="/start", update_id=90002)
        ack_ms = int((time.monotonic() - start_ts) * 1000)

        assert response.status in {200, 204}
        assert ack_ms < 500
        await asyncio.sleep(0)
        assert not harness.outbox.messages
    finally:
        await harness.teardown()
