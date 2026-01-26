import json
import socket

import aiohttp
from aiohttp import web
import pytest

import main_render
from app.config import Settings, reset_settings
from app.utils.healthcheck import get_health_status, start_health_server, stop_health_server


@pytest.mark.asyncio
async def test_webhook_db_only_registers_route(harness, monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.setenv("STORAGE_MODE", "db")
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


@pytest.mark.asyncio
async def test_health_server_idempotent_start(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def webhook_handler(request):
        return web.Response(text="ok")

    try:
        first = await start_health_server(port=port, webhook_handler=webhook_handler)
        second = await start_health_server(port=port, webhook_handler=webhook_handler)
        status = get_health_status()
        assert first is True
        assert second is True
        assert status.get("health_server_running") is True
    finally:
        await stop_health_server()


@pytest.mark.asyncio
async def test_health_server_double_start_stop(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def webhook_handler(request):
        return web.Response(text="ok")

    started = await start_health_server(port=port, webhook_handler=webhook_handler)
    restarted = await start_health_server(port=port, webhook_handler=webhook_handler)
    assert started is True
    assert restarted is True

    await stop_health_server()
    await stop_health_server()
    status = get_health_status()
    assert status.get("health_server_running") is False
