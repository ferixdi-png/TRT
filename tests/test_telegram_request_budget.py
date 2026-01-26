from __future__ import annotations

import time

from telegram.error import RetryAfter

from bot_kie import _run_telegram_request


async def test_telegram_retry_after_non_blocking_returns_fast():
    start_ts = time.monotonic()

    async def _raise_retry_after():
        raise RetryAfter(5)

    result = await _run_telegram_request(
        "test_retry_after",
        correlation_id="test",
        timeout_s=1.0,
        retry_attempts=1,
        retry_backoff_s=0.1,
        deadline_ms=200,
        non_blocking=True,
        request_fn=_raise_retry_after,
    )

    elapsed_ms = (time.monotonic() - start_ts) * 1000

    assert result is None
    assert elapsed_ms < 200


async def test_telegram_request_skips_when_deadline_exhausted():
    start_ts = time.monotonic()

    async def _noop():
        return "ok"

    result = await _run_telegram_request(
        "test_deadline",
        correlation_id="test",
        timeout_s=1.0,
        retry_attempts=1,
        retry_backoff_s=0.1,
        deadline_ms=0,
        non_blocking=True,
        request_fn=_noop,
    )

    elapsed_ms = (time.monotonic() - start_ts) * 1000

    assert result is None
    assert elapsed_ms < 50
