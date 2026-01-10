#!/usr/bin/env python3
"""
Start a lightweight healthcheck + webhook server for smoke tests.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram import Bot

from app.utils.healthcheck import start_health_server, stop_health_server


class DummyApplication:
    def __init__(self, token: str) -> None:
        self.bot = Bot(token=token)

    async def process_update(self, _update) -> None:
        return None


async def main() -> None:
    port = int(os.getenv("PORT", "8080"))
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

    stop_event = asyncio.Event()

    def _shutdown() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await stop_event.wait()
    await stop_health_server()


if __name__ == "__main__":
    asyncio.run(main())
