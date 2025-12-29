import pytest


def test_z_image_payload_is_wrapped_in_input():
    """Regression: Kie createTask requires `input` wrapper.

    When a model is marked as payload_format=direct in SOURCE_OF_TRUTH,
    we still must send fields inside payload['input'] (not on payload root),
    otherwise Kie returns generic "This field is required" errors.
    """
    from app.kie.builder import build_payload, load_source_of_truth
    from app.kie.validator import validate_payload_before_create_task

    sot = load_source_of_truth()
    model_schema = sot["models"].get("z-image")
    assert model_schema is not None

    payload = build_payload("z-image", {"prompt": "котик"}, source_of_truth=sot)

    assert payload.get("model") == "z-image"
    assert isinstance(payload.get("input"), dict)
    assert payload["input"].get("prompt") == "котик"
    assert "prompt" not in payload, "prompt must NOT be placed on payload root"

    # Should not raise
    validate_payload_before_create_task("z-image", payload, model_schema)
