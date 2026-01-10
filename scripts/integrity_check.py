#!/usr/bin/env python3
"""
Integrity checks for core runtime invariants.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiohttp.test_utils import make_mocked_request
from telegram import Bot

from app.utils.healthcheck import health_handler, webhook_handler, set_start_time
from app.utils.startup_validation import REQUIRED_ENV_KEYS


def _assert_required_env_keys() -> None:
    required = set(REQUIRED_ENV_KEYS)
    expected = {
        "ADMIN_ID",
        "BOT_MODE",
        "DATABASE_URL",
        "DB_MAXCONN",
        "KIE_API_KEY",
        "PAYMENT_BANK",
        "PAYMENT_CARD_HOLDER",
        "PAYMENT_PHONE",
        "PORT",
        "SUPPORT_TELEGRAM",
        "SUPPORT_TEXT",
        "TELEGRAM_BOT_TOKEN",
        "WEBHOOK_BASE_URL",
    }
    missing = expected - required
    if missing:
        raise AssertionError(f"Missing required env keys: {sorted(missing)}")


async def _assert_health_endpoints() -> None:
    set_start_time()
    request = make_mocked_request("GET", "/health")
    response = await health_handler(request)
    assert response.status == 200
    request = make_mocked_request("HEAD", "/")
    response = await health_handler(request)
    assert response.status == 200


async def _assert_webhook_handler() -> None:
    class DummyApplication:
        def __init__(self) -> None:
            self.bot = Bot(token="123456:TEST")

        async def process_update(self, _update) -> None:
            return None

    app = DummyApplication()
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

    bad_request = make_mocked_request("POST", "/webhook/bad", payload=payload)
    bad_request._match_info = {"secret": "bad"}
    response = await webhook_handler(
        bad_request,
        application=app,
        secret_path="secret",
        secret_token="",
    )
    assert response.status == 404


async def main() -> None:
    _assert_required_env_keys()
    await _assert_health_endpoints()
    await _assert_webhook_handler()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[INTEGRITY] FAILED: {exc}")
        sys.exit(1)
