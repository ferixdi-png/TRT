import pytest

from app.kie.builder import build_payload
from app.kie.validator import ModelContractError


@pytest.fixture
def fake_source_of_truth():
    return {
        "models": {
            "direct-model": {
                "model_id": "direct-model",
                "api_endpoint": "direct-model",
                "payload_format": "direct",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "required": True},
                        "style": {"type": "string", "required": False},
                    },
                    "required": ["prompt"],
                },
                "pricing": {"rub_per_gen": 1.0, "usd_per_gen": 0.02},
                "enabled": True,
            },
            "empty-input": {
                "model_id": "empty-input",
                "api_endpoint": "empty-input",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                "pricing": {"rub_per_gen": 1.0, "usd_per_gen": 0.02},
                "enabled": True,
            },
        }
    }


def test_direct_payload_is_wrapped(fake_source_of_truth):
    payload = build_payload(
        "direct-model",
        {"prompt": "hello world"},
        fake_source_of_truth,
    )

    assert payload["model"] == "direct-model"
    assert "input" in payload
    assert payload["input"].get("prompt") == "hello world"
    # No user fields should leak to the root (prevents 422 input cannot be null)
    assert set(payload.keys()) >= {"model", "input"}
    assert "prompt" not in payload


def test_empty_input_rejected(fake_source_of_truth):
    with pytest.raises(ModelContractError):
        build_payload("empty-input", {}, fake_source_of_truth)
