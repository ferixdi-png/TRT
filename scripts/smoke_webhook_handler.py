#!/usr/bin/env python3
"""Smoke script to emulate a Telegram webhook update locally."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO_ROOT))

import main_render
from tests.ptb_harness import PTBHarness


def _build_request(payload):
    request = MagicMock(spec=web.Request)
    request.headers = {"X-Request-ID": "corr-webhook-smoke"}
    request.method = "POST"
    request.path = "/webhook"
    request.content_length = len(json.dumps(payload))
    request.json = AsyncMock(return_value=payload)
    return request


async def main() -> None:
    harness = PTBHarness()
    await harness.setup()

    main_render._app_ready_event.set()
    handler = main_render.build_webhook_handler(harness.application, MagicMock())

    payload = {
        "update_id": 900001,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 900001, "type": "private"},
            "from": {"id": 900001, "is_bot": False, "first_name": "Smoke"},
            "text": "/start",
        },
    }

    response = await handler(_build_request(payload))
    print(f"Webhook smoke response: status={response.status}")

    await harness.teardown()


if __name__ == "__main__":
    asyncio.run(main())
