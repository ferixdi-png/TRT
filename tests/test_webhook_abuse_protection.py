import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

import main_render


def _build_request(payload, *, headers=None, content_length=None, remote="203.0.113.10"):
    request = MagicMock(spec=web.Request)
    request.headers = headers or {}
    request.method = "POST"
    request.path = "/webhook"
    request.content_length = content_length if content_length is not None else len(json.dumps(payload))
    request.json = AsyncMock(return_value=payload)
    request.remote = remote
    return request


async def test_webhook_rejects_oversized_payload(harness, monkeypatch):
    main_render._app_ready_event.set()
    main_render._seen_update_ids.clear()
    monkeypatch.setenv("WEBHOOK_MAX_PAYLOAD_BYTES", "10")

    process_update = AsyncMock()
    object.__setattr__(harness.application, "process_update", process_update)
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 15,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }

    response = await handler(_build_request(payload, content_length=2048))
    await asyncio.sleep(0)

    assert response.status == 413
    assert process_update.call_count == 0


async def test_webhook_rate_limits_by_ip(harness, monkeypatch):
    main_render._app_ready_event.set()
    main_render._seen_update_ids.clear()
    monkeypatch.setenv("WEBHOOK_IP_RATE_LIMIT_PER_SEC", "1")
    monkeypatch.setenv("WEBHOOK_IP_RATE_LIMIT_BURST", "1")

    process_update = AsyncMock()
    object.__setattr__(harness.application, "process_update", process_update)
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload_first = {
        "update_id": 21,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 110, "type": "private"},
            "from": {"id": 110, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }
    payload_second = {
        "update_id": 22,
        "message": {
            "message_id": 2,
            "date": 0,
            "chat": {"id": 110, "type": "private"},
            "from": {"id": 110, "is_bot": False, "first_name": "Tester"},
            "text": "/help",
        },
    }
    headers = {"X-Forwarded-For": "198.51.100.42"}

    response_first = await handler(_build_request(payload_first, headers=headers))
    response_second = await handler(_build_request(payload_second, headers=headers))
    await asyncio.sleep(0)

    assert response_first.status == 200
    assert response_second.status == 429
