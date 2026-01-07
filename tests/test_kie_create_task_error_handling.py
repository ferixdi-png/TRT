import pytest

from app.kie.generator import KieGenerator
from app.utils.trace import TraceContext


class ErrorClient:
    async def create_task(self, payload, callback_url=None, **kwargs):
        return {"code": 422, "msg": "This field is required", "data": None}


@pytest.mark.asyncio
async def test_create_task_returns_structured_error_on_422():
    generator = KieGenerator()
    generator.api_client = ErrorClient()
    generator.source_of_truth = {
        "models": [
            {
                "model_id": "z-image",
                "payload_format": "direct",
                "input_schema": {
                    "required": ["prompt"],
                    "optional": [],
                    "properties": {"prompt": {"type": "string"}},
                },
            }
        ]
    }

    with TraceContext(model_id="z-image", request_id="req-test-422"):
        result = await generator.generate("z-image", {"prompt": "котик"})

    assert result["success"] is False
    assert "This field is required" in result["message"]
    assert "req-test-422" in result["message"]
    assert result["error_code"] == "API_ERROR_422"
    assert result["task_id"] is None
    assert result.get("user_friendly_message") == result["message"]
