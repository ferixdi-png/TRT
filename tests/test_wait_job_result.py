import pytest

from app.generations.universal_engine import wait_job_result, KIEResultError
from app.generations.request_tracker import RequestTracker, build_request_key


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    async def get_task_status(self, task_id, correlation_id=None):
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


class FakeStorage:
    def __init__(self):
        self.updates = []

    async def update_job_status(self, job_id, status, result_urls=None, error_message=None, error_code=None, result_url=None):
        self.updates.append(
            {
                "job_id": job_id,
                "status": status,
                "result_urls": result_urls,
                "error_message": error_message,
                "error_code": error_code,
                "result_url": result_url,
            }
        )


@pytest.mark.asyncio
async def test_wait_job_result_success_valid_url():
    client = FakeClient(
        [
            {"ok": True, "state": "success", "resultUrls": ["http://example.com/result.png"]},
        ]
    )
    validated = []

    async def validate(urls, **kwargs):
        validated.append(urls)

    record = await wait_job_result(
        "task-1",
        "qwen/text-to-image",
        client=client,
        timeout=5,
        max_attempts=3,
        base_delay=0.01,
        max_delay=0.05,
        correlation_id=None,
        request_id="req-1",
        user_id=1,
        prompt_hash="abc",
        job_id="job-1",
        validate_result_fn=validate,
        storage=FakeStorage(),
    )

    assert record["state"] == "success"
    assert validated == [["http://example.com/result.png"]]


@pytest.mark.asyncio
async def test_wait_job_result_success_empty_url_is_error():
    client = FakeClient(
        [
            {"ok": True, "state": "success", "resultUrls": []},
        ]
    )

    async def validate(urls, **kwargs):
        if not urls:
            raise KIEResultError("empty", error_code="KIE_RESULT_EMPTY", fix_hint="empty")

    with pytest.raises(KIEResultError):
        await wait_job_result(
            "task-2",
            "qwen/text-to-image",
            client=client,
            timeout=5,
            max_attempts=2,
            base_delay=0.01,
            max_delay=0.05,
            correlation_id=None,
            request_id="req-2",
            user_id=1,
            prompt_hash="def",
            job_id="job-2",
            validate_result_fn=validate,
            storage=FakeStorage(),
        )


@pytest.mark.asyncio
async def test_wait_job_result_retries_on_5xx_then_success():
    client = FakeClient(
        [
            {"ok": False, "status": 500, "error": "server"},
            {"ok": True, "state": "success", "resultUrls": ["http://example.com/result.png"]},
        ]
    )

    async def validate(urls, **kwargs):
        return None

    record = await wait_job_result(
        "task-3",
        "qwen/text-to-image",
        client=client,
        timeout=5,
        max_attempts=5,
        base_delay=0.01,
        max_delay=0.05,
        correlation_id=None,
        request_id="req-3",
        user_id=1,
        prompt_hash="ghi",
        job_id="job-3",
        validate_result_fn=validate,
        storage=FakeStorage(),
    )

    assert record["state"] == "success"


@pytest.mark.asyncio
async def test_wait_job_result_timeout_updates_storage_and_callback():
    client = FakeClient(
        [
            {"ok": True, "state": "running"},
        ]
    )
    storage = FakeStorage()
    timeout_called = {"ok": False}

    async def on_timeout():
        timeout_called["ok"] = True

    with pytest.raises(TimeoutError):
        await wait_job_result(
            "task-4",
            "qwen/text-to-image",
            client=client,
            timeout=0,
            max_attempts=1,
            base_delay=0.01,
            max_delay=0.05,
            correlation_id=None,
            request_id="req-4",
            user_id=1,
            prompt_hash="jkl",
            job_id="job-4",
            storage=storage,
            on_timeout=on_timeout,
        )

    assert timeout_called["ok"] is True
    assert storage.updates[-1]["status"] == "timeout"


def test_request_tracker_dedupes_within_window():
    current = [0.0]

    def time_fn():
        return current[0]

    tracker = RequestTracker(ttl_seconds=10, time_fn=time_fn)
    key = build_request_key(1, "qwen/text-to-image", "hash1")
    tracker.set(key, "job-1")
    assert tracker.get(key).job_id == "job-1"

    current[0] = 11.0
    assert tracker.get(key) is None
