import asyncio
import json
import logging
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
