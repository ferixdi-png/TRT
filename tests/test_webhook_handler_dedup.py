import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

import main_render


def _build_request(payload):
    request = MagicMock(spec=web.Request)
    request.headers = {"X-Request-ID": "corr-webhook-dedup"}
    request.method = "POST"
    request.path = "/webhook"
    raw_body = json.dumps(payload).encode("utf-8")
    request.content_length = len(raw_body)
    request.read = AsyncMock(return_value=raw_body)
    request.json = AsyncMock(return_value=payload)
    return request


async def test_webhook_handler_deduplicates_update(harness, monkeypatch):
    main_render._app_ready_event.set()
    monkeypatch.setattr(main_render, "_handler_ready", True)

    process_update = AsyncMock()
    harness.application.bot_data["process_update_override"] = process_update
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 10,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }

    response_first = await handler(_build_request(payload))
    response_second = await handler(_build_request(payload))
    await asyncio.sleep(0)

    assert response_first.status == 200
    assert response_second.status == 200
    assert process_update.call_count == 1
