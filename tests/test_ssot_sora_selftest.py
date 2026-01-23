import json
import sys
from pathlib import Path

import pytest

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.generations.universal_engine import parse_record_info, run_generation
from app.kie_catalog import get_model
from app.kie_contract.payload_builder import build_kie_payload
from app.models.canonical import canonicalize_model_id
from app.pricing.price_ssot import list_all_models
from app.pricing.ssot_catalog import list_model_skus


def _build_required_params(spec, sku_params):
    params = dict(sku_params or {})
    for field in spec.schema_required or []:
        if field in params and params[field] not in (None, ""):
            continue
        schema = spec.schema_properties.get(field, {})
        field_type = schema.get("type", "string")
        enum_vals = schema.get("enum") or schema.get("values") or []
        if isinstance(enum_vals, dict):
            enum_vals = list(enum_vals.values())
        if field_type == "enum" and enum_vals:
            params[field] = enum_vals[0]
        elif field_type == "boolean":
            params[field] = True
        elif field_type in {"number", "integer", "float"}:
            params[field] = 1
        elif field_type == "array":
            params[field] = ["https://example.com/file"]
        else:
            if "image" in field:
                params[field] = "https://example.com/image.png"
            elif "video" in field:
                params[field] = "https://example.com/video.mp4"
            elif "audio" in field:
                params[field] = "https://example.com/audio.mp3"
            else:
                params[field] = "test"
    return params


def test_ssot_payloads_build_for_all_skus():
    for model_id in list_all_models():
        canonical_id = canonicalize_model_id(model_id)
        spec = get_model(canonical_id)
        assert spec is not None, f"Missing spec for {model_id}"
        skus = list_model_skus(model_id)
        if not skus:
            continue
        for sku in skus:
            params = _build_required_params(spec, sku.params)
            payload = build_kie_payload(spec, params)
            assert payload["model"]
            assert payload["input"]


@pytest.mark.asyncio
async def test_kie_mock_flow_sora_text_to_video(monkeypatch):
    class FakeKieClient:
        async def create_task(self, model_id, input_data, correlation_id=None):
            return {"ok": True, "taskId": "task-123"}

        async def get_task_status(self, task_id, correlation_id=None):
            result_json = json.dumps({"resultUrl": ["https://example.com/result.mp4"]})
            return {"ok": True, "state": "success", "resultJson": result_json}

    monkeypatch.setattr(
        "app.integrations.kie_stub.get_kie_client_or_stub",
        lambda: FakeKieClient(),
    )

    job = await run_generation(
        user_id=42,
        model_id="sora-2-text-to-video",
        session_params={"prompt": "hello"},
        timeout=5,
        poll_interval=0.01,
        correlation_id="corr-test",
    )
    assert job.urls
    assert job.media_type == "video"


def test_parse_record_info_result_json():
    record = {
        "taskId": "task-321",
        "state": "success",
        "resultJson": json.dumps({"resultUrl": ["https://example.com/result.png"]}),
    }
    result = parse_record_info(record, media_type="image", model_id="sora-2-text-to-video")
    assert result.urls == ["https://example.com/result.png"]
