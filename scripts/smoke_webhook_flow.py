#!/usr/bin/env python3
"""Smoke webhook flow using PTBHarness."""
from __future__ import annotations

import asyncio
import logging
from typing import List

from pathlib import Path
from telegram.ext import CommandHandler

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO_ROOT))

import bot_kie
from tests.ptb_harness import PTBHarness


class LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def _run_webhook_update(harness: PTBHarness, text: str, user_id: int = 90001) -> None:
    if not harness.application:
        await harness.setup()
    harness.outbox.clear()
    await harness.process_command(text, user_id=user_id)


async def main() -> None:
    harness = PTBHarness()
    await harness.setup()
    harness.application.add_handler(CommandHandler("start", bot_kie.start))

    bot_kie._application_for_webhook = harness.application
    bot_kie._webhook_app_ready_event.clear()

    boot_task = bot_kie.start_boot_warmups(correlation_id="SMOKE_BOOT")
    bot_kie._webhook_app_ready_event.set()
    await boot_task

    capture = LogCapture()
    logging.getLogger().addHandler(capture)
    logging.getLogger().setLevel(logging.INFO)

    await _run_webhook_update(harness, "/start", user_id=90010)
    timeout_logs = [r for r in capture.records if "WEBHOOK_TIMEOUT" in r.message]
    if timeout_logs:
        raise RuntimeError("WEBHOOK_TIMEOUT found during normal /start")

    async def slow_sections(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return "Header", "Details"

    async def slow_keyboard(*_args, **_kwargs):
        await asyncio.sleep(0.2)
        return []

    bot_kie._build_main_menu_sections = slow_sections
    bot_kie.build_main_menu_keyboard = slow_keyboard
    bot_kie.MAIN_MENU_TOTAL_TIMEOUT_SECONDS = 0.05
    bot_kie.MAIN_MENU_BACKGROUND_TIMEOUT_SECONDS = 0.05

    await _run_webhook_update(harness, "/start", user_id=90011)
    if not harness.outbox.messages or harness.outbox.messages[-1]["text"] != bot_kie.MINIMAL_MENU_TEXT:
        raise RuntimeError("Minimal menu was not sent during timeout degradation")

    logging.getLogger().removeHandler(capture)
    await harness.teardown()


if __name__ == "__main__":
    asyncio.run(main())
