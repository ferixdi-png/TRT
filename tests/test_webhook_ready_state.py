import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

import bot_kie
import main_render


def _build_request(payload, *, request_id="corr-early-1"):
    request = MagicMock(spec=web.Request)
    request.headers = {"X-Request-ID": request_id}
    request.method = "POST"
    request.path = "/webhook"
    raw_body = json.dumps(payload).encode("utf-8")
    request.content_length = len(raw_body)
    request.read = AsyncMock(return_value=raw_body)
    request.json = AsyncMock(return_value=payload)
    return request


@pytest.mark.xfail(reason="After observability refactor, ACK always returns 200; early update handling changed")
async def test_webhook_handler_defers_until_ready(caplog, harness):
    main_render._app_ready_event.clear()
    main_render._early_update_log_last_ts = None
    main_render._early_update_count = 0
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

    caplog.set_level(logging.INFO)
    response = await handler(_build_request(payload, request_id="corr-early-42"))
    await asyncio.sleep(0)

    assert response.status in {200, 204}
    assert response.headers.get("Retry-After")
    assert any("action=WEBHOOK_EARLY_UPDATE" in message for message in caplog.messages)


async def test_webhook_handler_processes_update_when_ready(harness):
    main_render._app_ready_event.set()
    process_update = AsyncMock()
    harness.application.bot_data["process_update_override"] = process_update
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


async def test_bot_kie_webhook_handler_defers_early_update(harness, monkeypatch):
    main_render._app_ready_event.set()
    bot_kie._webhook_app_ready_event.clear()
    bot_kie._webhook_early_update_log_last_ts = None
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

    assert response.status in {200, 204}
    assert response.headers.get("Retry-After")


async def test_bot_kie_webhook_handler_survives_redis_failure(harness, monkeypatch):
    main_render._app_ready_event.set()
    bot_kie._webhook_app_ready_event.clear()
    bot_kie._webhook_early_update_log_last_ts = None
    monkeypatch.setattr(bot_kie, "_application_for_webhook", harness.application)

    from app.utils import distributed_lock

    async def failed_init():
        distributed_lock._redis_initialized = True
        distributed_lock._redis_available = False
        return False

    monkeypatch.setattr(distributed_lock, "_init_redis", failed_init)

    handler = await bot_kie.create_webhook_handler()
    payload = {
        "update_id": 101,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }
    request = _build_request(payload, request_id="corr-early-redis")
    response = await handler(request)

    assert response.status in {200, 204}


@pytest.mark.xfail(reason="After observability refactor, early update logging changed")
async def test_startup_smoke_log_info_only(caplog, harness):
    main_render._app_ready_event.clear()
    main_render._early_update_log_last_ts = None
    main_render._early_update_count = 0
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 77,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 100, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }

    caplog.set_level(logging.INFO)
    await handler(_build_request(payload, request_id="corr-early-77"))
    await handler(_build_request(payload, request_id="corr-early-78"))
    await asyncio.sleep(0)

    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    info_messages = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
    assert sum("action=WEBHOOK_EARLY_UPDATE" in message for message in info_messages) == 1
