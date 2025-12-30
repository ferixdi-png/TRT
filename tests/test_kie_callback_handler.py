import pytest
from app.kie.callback_handler import process_kie_callback


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
