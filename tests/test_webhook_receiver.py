"""Webhook receiver smoke test (no network)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import make_mocked_request

from app.utils.healthcheck import webhook_handler


@pytest.mark.asyncio
async def test_webhook_handler_processes_update():
    app = MagicMock()
    app.bot = MagicMock()
    app.process_update = AsyncMock()

    payload = {"update_id": 1, "message": {"message_id": 1, "text": "hi"}}
    request = make_mocked_request("POST", "/webhook/secret", payload=payload)
    request._match_info = {"secret": "secret"}

    response = await webhook_handler(
        request,
        application=app,
        secret_path="secret",
        secret_token="",
    )

    assert response.status == 200
    app.process_update.assert_awaited_once()
