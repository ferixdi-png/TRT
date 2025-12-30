import pytest

from app.kie.builder import load_source_of_truth
from app.ui.input_spec import get_input_spec, InputType


@pytest.fixture(scope="module")
def source_of_truth():
    sot = load_source_of_truth()
    if not sot or "models" not in sot:
        pytest.skip("source of truth unavailable")
    return sot


def test_text2image_optional_fields_exposed(source_of_truth):
    cfg = source_of_truth["models"].get("google/imagen4-fast")
    assert cfg, "imagen4-fast config missing"

    spec = get_input_spec(cfg)
    names = {f.name for f in spec.fields}

    # Optional schema fields must be available to the user (advanced settings)
    for expected in {"aspect_ratio", "num_images", "seed", "negative_prompt"}:
        assert expected in names, f"{expected} should be exposed in UI schema"

    aspect = spec.get_field("aspect_ratio")
    assert aspect and aspect.type == InputType.ENUM


def test_audio_to_video_optional_and_required_fields(source_of_truth):
    cfg = source_of_truth["models"].get("infinitalk/from-audio")
    assert cfg, "infinitalk/from-audio config missing"

    spec = get_input_spec(cfg)

    required = {f.name for f in spec.fields if f.required}
    assert {"image_url", "audio_url", "prompt"}.issubset(required)

    resolution = spec.get_field("resolution")
    seed = spec.get_field("seed")
    assert resolution and resolution.type == InputType.ENUM and not resolution.required
    assert seed and seed.type == InputType.NUMBER and not seed.required
