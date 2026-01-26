import asyncio

import pytest

from app.observability import correlation_store


class FakeStorage:
    def __init__(self) -> None:
        self.calls = []

    async def update_json_file(self, filename, update_fn):
        self.calls.append(filename)
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

    await asyncio.sleep(0.05)
    assert len(storage.calls) == 1
