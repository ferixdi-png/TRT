import pytest

from app.kie.kie_client import KIEClient


@pytest.mark.asyncio
async def test_cancel_task_uses_payload_argument(monkeypatch):
    client = KIEClient(api_key="test-key", base_url="https://example.com", circuit_breaker_enabled=False)
    captured_kwargs = {}

    async def fake_request_json(method, path, **kwargs):
        captured_kwargs.update(kwargs)
        return {"ok": True, "taskId": kwargs.get("payload", {}).get("taskId")}

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = await client.cancel_task("task-123", correlation_id="corr-1")

    assert result["ok"] is True
    assert captured_kwargs.get("payload") == {"taskId": "task-123"}
    assert "json" not in captured_kwargs
