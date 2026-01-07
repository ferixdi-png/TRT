"""Legacy-compatible Kie client shim for tests and old handlers.

This wraps the existing stub semantics used by KieGenerator so callers that
patch `app.kie.client.KieClient` get a predictable async client without hitting
real network calls.
"""
import json
from typing import Any, Dict


class KieClient:
    """Stub client mirroring the minimal interface expected by legacy tests."""

    def __init__(self):
        self._poll_counts: Dict[str, int] = {}

    async def create_task(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        model = kwargs.get("model_id") or "unknown"

        if len(args) == 1 and isinstance(args[0], dict):
            payload = args[0]
            model = payload.get("model") or payload.get("model_id") or model
        elif len(args) >= 2:
            model = args[0] if args[0] is not None else model
            payload = args[1] if isinstance(args[1], dict) else payload
        elif isinstance(kwargs.get("payload"), dict):
            payload = kwargs["payload"]
            model = payload.get("model") or payload.get("model_id") or model

        task_id = f"stub_task_{model}"
        self._poll_counts[task_id] = 0

        return {
            "code": 200,
            "taskId": task_id,
            "data": {"taskId": task_id, "status": "waiting", "payload": payload},
        }

    async def poll_task(self, task_id: str, *_, **__) -> Dict[str, Any]:
        count = self._poll_counts.get(task_id, 0)
        if count == 0:
            self._poll_counts[task_id] = 1
            return {"data": {"state": "running"}}

        self._poll_counts[task_id] = count + 1
        url = f"https://example.com/{task_id}.png"
        return {
            "data": {
                "state": "success",
                "outputs": [{"url": url}],
                "resultJson": json.dumps({"mediaUrl": url}),
            }
        }

    # Backward alias used by some tests
    get_record_info = poll_task
