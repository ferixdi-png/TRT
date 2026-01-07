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

class _MemoryJobService:
    def __init__(self): self.job = {"id": 1, "kie_task_id": None, "status": "draft"}
    async def update_status(self, job_id: int, status: str, kie_task_id=None, kie_status=None, result_json=None, error_text=None):
        if job_id == self.job["id"]:
            self.job.update({"kie_task_id": kie_task_id or self.job["kie_task_id"], "status": status or self.job["status"]})
            if result_json is not None: self.job["result_json"] = result_json
    async def get_by_kie_task_id(self, task_id: str):
        return self.job if self.job.get("kie_task_id") == task_id else None


@pytest.mark.asyncio
async def test_callback_maps_job_after_task_id_callback():
    from app.kie.generator import KieGenerator

    class _StubClient:
        async def create_task(self, payload, callback_url=None): return {"code": 200, "data": {"taskId": "cb-task"}}
        async def get_record_info(self, task_id: str): return {"state": "success", "resultJson": "{\"resultUrls\":[\"u1\"]}"}

    svc = _MemoryJobService(); gen = KieGenerator(api_client=_StubClient())

    async def _persist_task(task_id: str):
        await svc.update_status(1, "queued", kie_task_id=task_id, kie_status="waiting")

    await gen.generate("z-image", {"prompt": "hi", "aspect_ratio": "1:1"}, task_id_callback=_persist_task)

    payload = {"data": {"taskId": "cb-task", "state": "success", "resultJson": "{\"resultUrls\":[\"u1\"]}"}}
    job_id = await process_kie_callback(payload, svc)
    assert job_id == 1
    assert svc.job.get("status") == "succeeded"
    assert svc.job.get("result_json") == {"resultUrls": ["u1"]}


class _HistoryJobService:
    def __init__(self):
        self.job = {"id": 3, "kie_task_id": "cb-job", "status": "draft", "result_json": None}
        self.replied = []

    async def get_by_kie_task_id(self, task_id: str):
        return self.job if task_id == self.job["kie_task_id"] else None

    async def update_status(self, job_id: int, status: str, kie_task_id=None, kie_status=None, result_json=None, error_text=None):
        if job_id != self.job["id"]:
            return
        self.job["status"] = status
        self.job["kie_task_id"] = kie_task_id or self.job.get("kie_task_id")
        if result_json is not None:
            self.job["result_json"] = result_json

    async def mark_replied(self, job_id: int, result_json=None, error_text=None) -> bool:
        if job_id != self.job["id"]:
            return False
        self.replied.append((result_json, error_text))
        return len(self.replied) == 1


@pytest.mark.asyncio
async def test_callback_first_populates_history_and_reply_once():
    svc = _HistoryJobService()
    send = AsyncMock()

    payload = {"data": {"taskId": "cb-job", "state": "success", "resultJson": "{\"resultUrls\":[\"u1\"]}"}}
    job_id = await process_kie_callback(payload, svc)
    await _guarded_send(svc, job_id, {"from": "callback"}, send)

    await _guarded_send(svc, job_id, {"from": "poll"}, send)

    assert send.await_count == 1
    assert svc.job["status"] == "succeeded"
    assert svc.job["result_json"] == {"resultUrls": ["u1"]}


@pytest.mark.asyncio
async def test_poll_first_history_then_callback_skipped():
    svc = _HistoryJobService()
    send = AsyncMock()

    await svc.update_status(3, "succeeded", result_json={"resultUrls": ["u1"]})
    await _guarded_send(svc, svc.job["id"], {"from": "poll"}, send)

    payload = {"data": {"taskId": "cb-job", "state": "success", "resultJson": "{\"resultUrls\":[\"u2\"]}"}}
    job_id = await process_kie_callback(payload, svc)
    await _guarded_send(svc, job_id, {"from": "callback"}, send)

    assert send.await_count == 1
    assert svc.job["status"] == "succeeded"
    assert svc.job["result_json"] == {"resultUrls": ["u2"]}
