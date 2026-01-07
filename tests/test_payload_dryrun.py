"""
Dry-run test: build_payload для всех 42 моделей без падений.

Проверяет что для каждой модели из SOURCE_OF_TRUTH можно собрать
валидный payload с минимальными required inputs.
"""
import pytest
from app.kie.builder import build_payload, load_source_of_truth


@pytest.fixture
def source_of_truth():
    """Load SOURCE_OF_TRUTH once for all tests."""
    return load_source_of_truth()


def get_minimal_inputs(model_id: str, model: dict) -> dict:
    """
    Generate minimal valid user_inputs for model.
    
    Args:
        model_id: Model ID
        model: Model dict from SOURCE_OF_TRUTH
    
    Returns:
        Minimal user_inputs dict that satisfies required fields
    """
    schema = model.get("input_schema", {})
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    inputs = {}
    
    for field in required or properties.keys():
        prop = properties.get(field, {})
        field_type = prop.get("type", "string")
        
        # Handle different field types
        if field in ["prompt", "text", "description", "input", "query"]:
            inputs[field] = "test prompt"
        
        elif field in ["url", "image_url", "video_url", "audio_url", "file_url"]:
            # Use dummy URL for dry-run (no network call)
            inputs[field] = "https://example.com/test.jpg"
        
        elif field in ["file", "image", "video", "audio"]:
            # Use dummy file URL
            inputs[field] = "https://example.com/test_file.dat"
        
        elif field_type == "integer":
            inputs[field] = prop.get("default", 1)
        
        elif field_type == "number":
            inputs[field] = float(prop.get("default", 1.0))
        
        elif field_type == "boolean":
            inputs[field] = prop.get("default", False)
        
        elif field_type == "string":
            # Check for enum
            enum = prop.get("enum")
            if enum and len(enum) > 0:
                inputs[field] = enum[0]
            else:
                inputs[field] = prop.get("default", "test")
        
        else:
            # Generic fallback
            inputs[field] = prop.get("default", "test") or "test"

    # If no required fields were specified at all, still send a prompt to avoid empty payloads
    if not required and not inputs:
        inputs["prompt"] = "test"

    return inputs


def test_all_models_payload_buildable(source_of_truth):
    """Test that build_payload works for all enabled models."""
    models = source_of_truth.get("models", {})
    
    enabled_models = {
        mid: m for mid, m in models.items()
        if m.get("enabled", True) and not mid.endswith("_processor")
    }

    assert len(enabled_models) == 42, f"Expected 42 enabled models, got {len(enabled_models)}"

    failed = []

    for model_id, model in enabled_models.items():
        try:
            user_inputs = get_minimal_inputs(model_id, model)
            payload = build_payload(model_id, user_inputs, source_of_truth)

            # Basic validation
            assert isinstance(payload, dict), f"{model_id}: payload not dict"
            assert "model" in payload or "model_id" in payload, f"{model_id}: no model field"
            assert payload.get("input"), f"{model_id}: empty input payload"
        except Exception as e:
            failed.append((model_id, str(e)))

    if failed:
        print(f"\n❌ Failed models ({len(failed)}):")
        for mid, err in failed:
            print(f"  {mid}: {err}")

    assert not failed, f"Models failed dry-run: {failed}"


def test_specific_model_examples():
    """Test specific models with known inputs."""
    sot = load_source_of_truth()
    
    # Test text-to-image
    if "flux-1-1-pro" in sot["models"]:
        payload = build_payload("flux-1-1-pro", {"prompt": "a cat"}, sot)
        assert "prompt" in payload or ("input" in payload and "prompt" in payload["input"])
    
    # Test text-to-video
    if "kling-v1-5-std" in sot["models"]:
        payload = build_payload("kling-v1-5-std", {"prompt": "flying bird"}, sot)
        assert payload is not None
    
    # Test image-to-video
    if "kling-image-to-video" in sot["models"]:
        payload = build_payload(
            "kling-image-to-video",
            {"image_url": "https://example.com/test.jpg", "prompt": "animate"},
            sot
        )
        assert payload is not None
