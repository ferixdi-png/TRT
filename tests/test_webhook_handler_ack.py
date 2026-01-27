import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

import main_render


async def test_webhook_handler_acknowledges_update(caplog, harness, monkeypatch):
    main_render._app_ready_event.set()
    monkeypatch.setattr(main_render, "_handler_ready", True)
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }
    request = MagicMock(spec=web.Request)
    request.headers = {}
    request.method = "POST"
    request.path = "/webhook"
    request.content_length = len(json.dumps(payload))
    request.json = AsyncMock(return_value=payload)

    caplog.set_level(logging.INFO)
    response = await handler(request)
    await asyncio.sleep(0)

    assert response.status == 200
    assert any("update_received=true" in message for message in caplog.messages)
    assert any("forwarded_to_ptb=true" in message for message in caplog.messages)


async def test_webhook_ack_burst_under_200ms(webhook_harness, monkeypatch):
    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("WEBHOOK_EARLY_ACK", "1")
    monkeypatch.setenv("WEBHOOK_ACK_MAX_MS", "200")
    processed: list[int] = []

    async def slow_process_update(update):
        await asyncio.sleep(0.15)
        processed.append(getattr(update, "update_id", 0))

    webhook_harness.application.process_update = slow_process_update

    async def _send_burst(idx: int) -> float:
        start_ts = time.monotonic()
        if idx % 2 == 0:
            response = await webhook_harness.send_message(
                user_id=200 + idx,
                text="/start",
                update_id=6000 + idx,
                request_id=f"corr-webhook-burst-{idx}",
            )
        else:
            response = await webhook_harness.send_callback(
                user_id=200 + idx,
                callback_data="show_models",
                update_id=6000 + idx,
                request_id=f"corr-webhook-burst-{idx}",
            )
        elapsed_ms = (time.monotonic() - start_ts) * 1000
        assert response.status == 200
        return elapsed_ms

    durations = await asyncio.gather(*[_send_burst(i) for i in range(20)])
    assert all(duration < 200 for duration in durations)
    await asyncio.sleep(0.2)
    assert len(processed) == 20
