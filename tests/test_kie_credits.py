import asyncio
from unittest.mock import AsyncMock

import helpers
from app.kie.kie_client import KIEClient


def test_credits_uses_chat_credit_endpoint():
    client = KIEClient(api_key="test", base_url="https://api.kie.ai")
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        return {"ok": False, "status": 404, "error": "not found"}

    client._request_json = fake_request  # type: ignore[assignment]

    asyncio.run(client.get_credits())

    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/chat/credit"


async def test_credits_failure_graceful_message(monkeypatch, test_env):
    helpers.set_constants(3, 3, 12345)
    helpers._init_imports()

    kie_client = AsyncMock()
    kie_client.get_credits = AsyncMock(return_value={"ok": False, "status": 503, "correlation_id": "corr"})
    monkeypatch.setattr(helpers, "_get_client", lambda: kie_client)

    balance_info = await helpers.get_balance_info(12345, "ru")
    message = await helpers.format_balance_message(balance_info, "ru")

    assert "KIE credits temporarily unavailable" in message
