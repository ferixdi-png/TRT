import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

import bot_kie
import main_render


def _build_request(payload, *, request_id="corr-early-1"):
    request = MagicMock(spec=web.Request)
    request.headers = {"X-Request-ID": request_id}
    request.method = "POST"
    request.path = "/webhook"
    request.content_length = len(json.dumps(payload))
    request.json = AsyncMock(return_value=payload)
    return request


async def test_webhook_handler_returns_503_until_ready(caplog, harness):
    main_render._app_ready_event.clear()
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 42,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }

    caplog.set_level(logging.WARNING)
    response = await handler(_build_request(payload, request_id="corr-early-42"))
    await asyncio.sleep(0)

    assert response.status == 503
    assert response.headers.get("Retry-After")
    assert any("action=WEBHOOK_EARLY_UPDATE" in message for message in caplog.messages)


async def test_webhook_handler_processes_update_when_ready(harness):
    main_render._app_ready_event.set()
    process_update = AsyncMock()
    object.__setattr__(harness.application, "process_update", process_update)
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 55,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }

    response = await handler(_build_request(payload, request_id="corr-ready-55"))
    await asyncio.sleep(0)

    assert response.status == 200
    assert process_update.call_count == 1


async def test_bot_kie_webhook_handler_rejects_early_update(harness, monkeypatch):
    main_render._app_ready_event.set()
    bot_kie._webhook_app_ready_event.clear()
    monkeypatch.setattr(bot_kie, "_application_for_webhook", harness.application)

    handler = await bot_kie.create_webhook_handler()

    payload = {
        "update_id": 99,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }
    request = _build_request(payload, request_id="corr-early-bot-kie")
    response = await handler(request)

    assert response.status == 503
    assert response.headers.get("Retry-After")
