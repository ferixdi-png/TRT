#!/usr/bin/env python3
"""
Minimal e2e smoke checks for Render-like webhook mode.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp
from telegram import Bot

from app.utils.healthcheck import start_health_server, stop_health_server


class DummyApplication:
    def __init__(self, token: str) -> None:
        self.bot = Bot(token=token)

    async def process_update(self, _update) -> None:
        return None


async def main() -> None:
    port = int(os.getenv("PORT", "8081"))
    token = os.getenv("TELEGRAM_BOT_TOKEN", "123456:TEST")
    secret_path = os.getenv("WEBHOOK_SECRET_PATH", "test")
    secret_token = os.getenv("WEBHOOK_SECRET_TOKEN", "")

    application = DummyApplication(token=token)
    await start_health_server(
        port=port,
        application=application,
        webhook_secret_path=secret_path,
        webhook_secret_token=secret_token,
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.status == 200
        async with session.head(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
        async with session.get(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": 1, "type": "private"},
                "text": "ping",
            },
        }
        headers = {"Content-Type": "application/json"}
        if secret_token:
            headers["X-Telegram-Bot-Api-Secret-Token"] = secret_token
        async with session.post(
            f"http://127.0.0.1:{port}/webhook/{secret_path}",
            json=payload,
            headers=headers,
        ) as resp:
            assert resp.status == 200

    await stop_health_server()


if __name__ == "__main__":
    asyncio.run(main())
