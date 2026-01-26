#!/usr/bin/env python3
"""Reproduce webhook timeouts with fault injection delays."""
from __future__ import annotations

import asyncio
import os
import time

from tests.webhook_harness import WebhookHarness


async def main() -> None:
    os.environ.setdefault("TEST_MODE", "1")
    os.environ.setdefault("DRY_RUN", "0")
    os.environ.setdefault("ALLOW_REAL_GENERATION", "1")
    os.environ.setdefault("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    os.environ.setdefault("WEBHOOK_PROCESS_TIMEOUT_SECONDS", "2")
    os.environ.setdefault("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", "5000")
    os.environ.setdefault("TRT_FAULT_INJECT_MENU_SLEEP_MS", "5000")
    os.environ.setdefault("TRT_FAULT_INJECT_CORR_FLUSH_SLEEP_MS", "5000")
    os.environ.setdefault("START_FALLBACK_MAX_MS", "800")

    harness = WebhookHarness()
    await harness.setup()
    try:
        start_ts = time.monotonic()
        response = await harness.send_message(user_id=9001, text="/start", update_id=90001)
        ack_ms = int((time.monotonic() - start_ts) * 1000)
        print(f"[repro] webhook_ack status={response.status} ack_ms={ack_ms}")
        await asyncio.sleep(6)
        if harness.outbox.messages:
            print(f"[repro] first_message_text={harness.outbox.messages[0]['text']}")
        else:
            print("[repro] no_message_sent")
    finally:
        await harness.teardown()


if __name__ == "__main__":
    asyncio.run(main())
