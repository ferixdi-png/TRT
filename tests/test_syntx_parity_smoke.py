import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.webhook_server import _default_secret


@pytest.mark.asyncio
async def test_health_and_masked_webhook_logs(caplog, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_PATH", "")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://example.com")

    from app.webhook_server import start_webhook_server

    bot = MagicMock()
    bot.token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    bot.set_webhook = AsyncMock()
    bot.get_me = AsyncMock()
    bot.get_webhook_info = AsyncMock()

    dp = MagicMock()

    captured = {}

    class DummyRunner:
        def __init__(self, app, **kwargs):
            captured["app"] = app

        async def setup(self):
            return None

        async def cleanup(self):
            return None

    class DummySite:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            return None

    with patch("app.webhook_server.web.AppRunner", DummyRunner), \
         patch("app.webhook_server.web.TCPSite", DummySite), \
         patch("app.webhook_server.setup_application"), \
         patch("app.webhook_server._detect_base_url", return_value="https://example.com"):
        await start_webhook_server(dp, bot, "0.0.0.0", 8080)

    app = captured["app"]
    async with TestServer(app) as server, TestClient(server) as client:
        resp = await client.get("/health")
        assert resp.status == 200

    secret = _default_secret(bot.token)
    assert secret not in caplog.text
    assert "****" in caplog.text
