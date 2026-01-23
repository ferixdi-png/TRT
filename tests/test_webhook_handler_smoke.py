import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

import main_render


def _build_request(payload):
    request = MagicMock(spec=web.Request)
    request.headers = {"X-Request-ID": "corr-webhook-123"}
    request.method = "POST"
    request.path = "/webhook"
    request.content_length = len(json.dumps(payload))
    request.json = AsyncMock(return_value=payload)
    return request


async def test_webhook_handler_smoke_context(caplog, harness, monkeypatch):
    main_render._app_ready_event.set()
    monkeypatch.setattr(main_render, "_handler_ready", True)

    async def process_update(update):
        assert not hasattr(update, "correlation_id")

    object.__setattr__(harness.application, "process_update", AsyncMock(side_effect=process_update))
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

    caplog.set_level(logging.INFO)
    response = await handler(_build_request(payload))
    await asyncio.sleep(0)

    assert response.status == 200
    assert any("correlation_id=corr-webhook-123" in message for message in caplog.messages)


async def test_webhook_handler_sends_fallback_on_error(harness, monkeypatch):
    main_render._app_ready_event.set()
    monkeypatch.setattr(main_render, "_handler_ready", True)

    object.__setattr__(
        harness.application,
        "process_update",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 2,
        "message": {
            "message_id": 2,
            "date": 0,
            "chat": {"id": 200, "type": "private"},
            "from": {"id": 200, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }

    response = await handler(_build_request(payload))
    await asyncio.sleep(0)

    assert response.status == 200
    assert harness.outbox.messages
    assert "Ошибка обработки" in harness.outbox.messages[-1]["text"]
