import logging

import pytest

from app.kie.generator import KieGenerator
from app.utils.trace import TraceContext, get_request_id


def test_get_request_id_generates_hex_when_missing_context():
    rid = get_request_id()

    assert rid != "-"
    assert len(rid) == 12
    int(rid, 16)

    # Subsequent calls should reuse the same generated id until context changes
    assert get_request_id() == rid


def test_get_request_id_respects_trace_context():
    with TraceContext(request_id="trace-123", user_id=1, model_id="m1"):
        assert get_request_id() == "trace-123"


class _OkClient:
    async def create_task(self, payload, callback_url=None, **kwargs):
        return {"code": 200, "taskId": "task-123", "data": {"taskId": "task-123"}}

    async def get_record_info(self, task_id: str):
        return {"state": "success", "resultJson": "{\"mediaUrl\": \"https://example.com/a.png\"}"}


@pytest.mark.asyncio
async def test_generator_logs_include_request_id(caplog):
    generator = KieGenerator(api_client=_OkClient())
    generator.source_of_truth = {
        "models": [
            {
                "model_id": "z-image",
                "input_schema": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {"prompt": {"type": "string"}},
                },
            }
        ]
    }

    with caplog.at_level(logging.INFO, logger="app.kie.generator"):
        await generator.generate("z-image", {"prompt": "котик"})

    start_records = [r for r in caplog.records if getattr(r, "stage", "") == "start"]
    assert start_records, "expected start log record with stage='start'"
    for record in start_records:
        assert getattr(record, "request_id", None)
        assert record.request_id != "-"
