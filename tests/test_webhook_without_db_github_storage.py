import json
import socket

import aiohttp
import pytest

import main_render
from app.config import Settings, reset_settings
from app.utils.healthcheck import get_health_status, start_health_server, stop_health_server


@pytest.mark.asyncio
async def test_webhook_without_db_github_storage_registers_route(harness, monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("STORAGE_MODE", "github_json")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")

    reset_settings()
    settings = Settings()
    settings.validate()

    webhook_handler = main_render.build_webhook_handler(harness.application, settings)
    await start_health_server(port=port, webhook_handler=webhook_handler)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/health") as response:
                payload = json.loads(await response.text())
        health_status = get_health_status()
        assert payload["status"] == "ok"
        assert payload["webhook_route_registered"] is True
        assert health_status.get("webhook_route_registered") is True
    finally:
        await stop_health_server()
