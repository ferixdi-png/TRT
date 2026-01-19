import json

from app.generations.universal_engine import parse_record_info
from app.kie_catalog import get_model_map
from app.kie_contract.payload_builder import build_kie_payload


def test_seedream_contract_payload_and_parse():
    spec = get_model_map().get("bytedance/seedream")
    if not spec:
        raise AssertionError("bytedance/seedream not found in catalog")

    params = {
        "prompt": "Test prompt",
        "image_size": "square",
        "guidance_scale": 5,
        "enable_safety_checker": True,
    }
    payload = build_kie_payload(spec, params)

    assert payload["model"] == spec.kie_model
    assert payload["input"]["prompt"] == "Test prompt"
    assert payload["input"]["image_size"] == "square"
    assert payload["input"]["guidance_scale"] == 5
    assert payload["input"]["enable_safety_checker"] is True

    record = {
        "taskId": "seedream-task",
        "state": "success",
        "resultJson": json.dumps({"resultUrls": ["https://example.com/seedream.png"]}),
    }
    result = parse_record_info(record, spec.output_media_type, spec.id)
    assert result.urls == ["https://example.com/seedream.png"]
