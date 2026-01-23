import asyncio
import json

import pytest

from app.generations.universal_engine import WATCHDOG_FILE, run_generation, wait_job_result
from app.kie_catalog import get_model_map


class DummyStorage:
    def __init__(self) -> None:
        self.data = {}
        self.job_status = {}

    async def update_job_status(self, job_id, status, **_kwargs):
        self.job_status[job_id] = status

    async def add_generation_job(self, *args, **_kwargs):
        return "job-1"

    async def update_json_file(self, filename, update_fn):
        current = self.data.get(filename, {})
        self.data[filename] = update_fn(current)
        return self.data[filename]


class WaitingClient:
    def __init__(self, success_after: int = 2) -> None:
        self.calls = 0
        self.success_after = success_after

    async def get_task_status(self, task_id, **_kwargs):
        self.calls += 1
        if self.calls <= self.success_after:
            return {"ok": True, "state": "waiting"}
        return {
            "ok": True,
            "state": "success",
            "resultUrls": ["https://example.com/image.png"],
            "resultJson": json.dumps({"resultUrls": ["https://example.com/image.png"]}),
        }


@pytest.mark.asyncio
async def test_waiting_to_success_updates_watchdog():
    storage = DummyStorage()

    async def validate_result(*_args, **_kwargs):
        return None

    record = await wait_job_result(
        "task-1",
        "model-1",
        client=WaitingClient(success_after=2),
        timeout=2,
        max_attempts=5,
        base_delay=0.01,
        max_delay=0.02,
        correlation_id="corr-1",
        request_id="req-1",
        user_id=1,
        prompt_hash="hash-1",
        job_id="job-1",
        progress_callback=None,
        storage=storage,
        validate_result_fn=validate_result,
        waiting_timeout_s=1,
        progress_interval_s=0.01,
    )

    assert record["state"] == "success"
    assert storage.data[WATCHDOG_FILE]["hash-1"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_waiting_timeout_retry_success():
    storage = DummyStorage()
    client = WaitingClient(success_after=100)
    retry_called = {"count": 0}

    async def validate_result(*_args, **_kwargs):
        return None

    async def on_waiting_timeout(retry_count: int):
        retry_called["count"] = retry_count
        return "task-2"

    async def get_task_status(task_id, **_kwargs):
        if task_id == "task-2":
            return {
                "ok": True,
                "state": "success",
                "resultUrls": ["https://example.com/image.png"],
                "resultJson": json.dumps({"resultUrls": ["https://example.com/image.png"]}),
            }
        return await client.get_task_status(task_id)

    class RetryClient(WaitingClient):
        async def get_task_status(self, task_id, **kwargs):
            return await get_task_status(task_id, **kwargs)

    record = await wait_job_result(
        "task-1",
        "model-1",
        client=RetryClient(success_after=100),
        timeout=2,
        max_attempts=10,
        base_delay=0.01,
        max_delay=0.02,
        correlation_id="corr-1",
        request_id="req-1",
        user_id=1,
        prompt_hash="hash-2",
        job_id="job-2",
        progress_callback=None,
        storage=storage,
        validate_result_fn=validate_result,
        waiting_timeout_s=0.01,
        progress_interval_s=0.01,
        on_waiting_timeout=on_waiting_timeout,
        task_ref={},
    )

    assert record["taskId"] == "task-2"
    assert retry_called["count"] == 1


@pytest.mark.asyncio
async def test_cancel_cleans_watchdog_and_calls_cancel(monkeypatch):
    storage = DummyStorage()

    class CancelClient:
        def __init__(self) -> None:
            self.cancel_called = False

        async def create_task(self, *_args, **_kwargs):
            return {"ok": True, "taskId": "task-cancel"}

        async def get_task_status(self, *_args, **_kwargs):
            return {"ok": True, "state": "waiting"}

        async def cancel_task(self, *_args, **_kwargs):
            self.cancel_called = True
            return {"ok": True}

    client = CancelClient()

    monkeypatch.setattr("app.integrations.kie_stub.get_kie_client_or_stub", lambda: client)
    monkeypatch.setattr(
        "app.generations.universal_engine.build_kie_payload",
        lambda _spec, _params: {"input": {"prompt": "test"}},
    )
    monkeypatch.setattr("app.generations.universal_engine.get_storage", lambda: storage)

    model_spec = next(iter(get_model_map().values()))

    task = asyncio.create_task(
        run_generation(
            1,
            model_spec.id,
            {"prompt": "test"},
            poll_interval=1,
            prompt_hash="hash-cancel",
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.cancel_called is True
    assert "hash-cancel" not in storage.data.get(WATCHDOG_FILE, {})
