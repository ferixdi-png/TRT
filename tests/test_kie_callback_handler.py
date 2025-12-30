import pytest
from app.kie.callback_handler import process_kie_callback
from unittest.mock import AsyncMock


class _FakeJobService:
    def __init__(self):
        self.updated = {}

    async def get_by_kie_task_id(self, task_id: str):
        return {"id": 1, "kie_task_id": task_id}

    async def update_status(self, **kwargs):
        self.updated = kwargs


@pytest.mark.asyncio
async def test_process_kie_callback_persists_job():
    svc = _FakeJobService()
    payload = {"data": {"taskId": "t-123", "state": "success", "resultJson": "{\"resultUrls\":[\"u1\"]}"}}

    job_id = await process_kie_callback(payload, svc)

    assert job_id == 1
    assert svc.updated["status"] == "succeeded"
    assert svc.updated["result_json"] == {"resultUrls": ["u1"]}


class _GuardJobService:
    def __init__(self):
        self.calls = []

    async def mark_replied(self, job_id: int, result_json=None, error_text=None) -> bool:
        self.calls.append((job_id, result_json, error_text))
        return len(self.calls) == 1


async def _guarded_send(service: _GuardJobService, job_id: int, payload, send):
    if await service.mark_replied(job_id, result_json=payload):
        await send()


@pytest.mark.asyncio
async def test_reply_once_poll_then_callback():
    svc = _GuardJobService()
    send = AsyncMock()

    await _guarded_send(svc, 1, {"from": "poll"}, send)
    await _guarded_send(svc, 1, {"from": "callback"}, send)

    assert send.await_count == 1
    assert svc.calls[0][1] == {"from": "poll"}


@pytest.mark.asyncio
async def test_reply_once_callback_then_poll():
    svc = _GuardJobService()
    send = AsyncMock()

    await _guarded_send(svc, 2, {"from": "callback"}, send)
    await _guarded_send(svc, 2, {"from": "poll"}, send)

    assert send.await_count == 1
    assert svc.calls[0][1] == {"from": "callback"}
