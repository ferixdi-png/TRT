import asyncio
import logging
import time

import pytest

from app.observability import correlation_store


class FakeStorage:
    def __init__(self) -> None:
        self.calls = []

    async def update_json_file(self, filename, update_fn, **_kwargs):
        self.calls.append(filename)
        return update_fn({})


class SlowStorage:
    async def update_json_file(self, filename, update_fn, **_kwargs):
        await asyncio.sleep(0.05)
        return update_fn({})


@pytest.mark.asyncio
async def test_correlation_store_batches_flush(monkeypatch):
    storage = FakeStorage()

    monkeypatch.setattr(correlation_store, "_resolve_storage", lambda *_args, **_kwargs: storage)
    correlation_store._persist_debounce_seconds = 0.01
    correlation_store._flush_interval_seconds = 0.01
    correlation_store._flush_max_records = 10
    correlation_store.reset_correlation_store()

    for index in range(3):
        correlation_store.register_ids(
            correlation_id=f"corr-{index}",
            request_id=f"req-{index}",
            task_id=None,
            job_id=None,
            user_id=123,
            model_id=None,
            source="test",
        )

    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and len(storage.calls) < 1:
        await asyncio.sleep(0.01)
    assert len(storage.calls) == 1


@pytest.mark.asyncio
async def test_correlation_store_flush_timeout_log_throttled(monkeypatch, caplog):
    storage = SlowStorage()

    monkeypatch.setattr(correlation_store, "_resolve_storage", lambda *_args, **_kwargs: storage)
    correlation_store._persist_debounce_seconds = 0.0
    correlation_store._flush_interval_seconds = 0.01
    correlation_store._persist_timeout_seconds = 0.01
    correlation_store._flush_max_records = 10
    correlation_store._flush_timeout_log_interval_seconds = 3600
    correlation_store.reset_correlation_store()

    with caplog.at_level(logging.WARNING):
        correlation_store.register_ids(
            correlation_id="corr-timeout",
            request_id="req-timeout",
            task_id=None,
            job_id=None,
            user_id=123,
            model_id=None,
            source="test",
        )
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if any("correlation_store_flush_timeout" in record.message for record in caplog.records):
                break
            await asyncio.sleep(0.01)

    warnings = [record for record in caplog.records if "correlation_store_flush_timeout" in record.message]
    assert len(warnings) == 1
