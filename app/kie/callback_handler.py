import json
from typing import Dict
from app.database.services import JobService

async def process_kie_callback(payload: Dict, job_service: JobService):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    task_id = data.get("taskId") or data.get("task_id")
    if not task_id:
        return None
    job = await job_service.get_by_kie_task_id(task_id)
    if not job:
        return None

    res = data.get("resultJson") or data.get("result_json")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except Exception:
            pass
    state = (data.get("state") or "").lower()
    status = "succeeded" if state == "success" else "failed" if state == "fail" else "running"
    await job_service.update_status(job_id=job["id"], status=status, kie_task_id=task_id, kie_status=state or None, result_json=res, error_text=data.get("failMsg") or data.get("fail_msg"))
    return job["id"]
