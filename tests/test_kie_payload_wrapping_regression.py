import json

import pytest

from app.kie.builder import build_payload


@pytest.fixture(scope="module")
def source_of_truth_snapshot() -> dict:
    with open("models/KIE_SOURCE_OF_TRUTH.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    # Keep only the target model to reduce fixture size
    return {"models": {"z-image": data["models"]["z-image"]}}


def test_z_image_payload_is_wrapped(source_of_truth_snapshot):
    payload = build_payload("z-image", {"prompt": "котик"}, source_of_truth_snapshot)

    assert payload["model"] == "z-image"
    assert "input" in payload
    assert payload["input"].get("prompt") == "котик"
    # Regression: prompt must not leak to the payload root even for payload_format=direct
    assert "prompt" not in payload
