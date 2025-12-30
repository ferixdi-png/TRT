import json

import pytest

from app.kie.builder import build_payload


@pytest.fixture(scope="module")
def source_of_truth_snapshot() -> dict:
    with open("models/KIE_SOURCE_OF_TRUTH.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    # Keep only the target model to reduce fixture size
    return {"models": {"z-image": data["models"]["z-image"]}}


@pytest.fixture(scope="module")
def google_free_snapshot() -> dict:
    """Minimal snapshot for a second FREE model to guard wrapping logic."""
    with open("models/KIE_SOURCE_OF_TRUTH.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"models": {"google/imagen4-fast": data["models"]["google/imagen4-fast"]}}


@pytest.fixture(scope="module")
def google_imagen4_snapshot() -> dict:
    """Snapshot for full Imagen4 (free-tier contract guard)."""
    with open("models/KIE_SOURCE_OF_TRUTH.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"models": {"google/imagen4": data["models"]["google/imagen4"]}}


@pytest.fixture(scope="module")
def recraft_snapshot() -> dict:
    """Guard payload wrapping for the background remover (free tier)."""
    with open("models/KIE_SOURCE_OF_TRUTH.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"models": {"recraft/remove-background": data["models"]["recraft/remove-background"]}}


def test_z_image_payload_is_wrapped(source_of_truth_snapshot):
    payload = build_payload("z-image", {"prompt": "котик"}, source_of_truth_snapshot)

    assert payload["model"] == "z-image"
    assert "input" in payload
    assert payload["input"].get("prompt") == "котик"
    # Regression: prompt must not leak to the payload root even for payload_format=direct
    assert "prompt" not in payload


def test_google_imagen4_fast_payload_is_wrapped(google_free_snapshot):
    payload = build_payload("google/imagen4-fast", {"prompt": "котик"}, google_free_snapshot)

    assert payload["model"] == "google/imagen4-fast"
    assert "input" in payload
    assert payload["input"].get("prompt") == "котик"
    assert "prompt" not in payload


def test_google_imagen4_payload_is_wrapped(google_imagen4_snapshot):
    payload = build_payload("google/imagen4", {"prompt": "котик"}, google_imagen4_snapshot)

    assert payload["model"] == "google/imagen4"
    assert "input" in payload
    assert payload["input"].get("prompt") == "котик"
    assert "prompt" not in payload


def test_recraft_remove_background_payload_is_wrapped(recraft_snapshot):
    payload = build_payload(
        "recraft/remove-background",
        {"image": "https://example.com/cat.png"},
        recraft_snapshot,
    )

    assert payload["model"] == "recraft/remove-background"
    assert payload["input"]["image"] == "https://example.com/cat.png"
    # Keep image_url for schema compatibility while preferring image for Kie contract
    assert payload["input"]["image_url"] == "https://example.com/cat.png"
    assert "image" not in payload


def test_infinitalk_from_audio_payload_includes_all_required_fields():
    payload = build_payload(
        "infinitalk/from-audio",
        {
            "image_url": "https://example.com/face.png",
            "audio_url": "https://example.com/voice.mp3",
            "prompt": "держи камеру статично",
        },
    )

    assert payload["model"] == "infinitalk/from-audio"
    assert payload["input"]["image_url"] == "https://example.com/face.png"
    assert payload["input"]["audio_url"] == "https://example.com/voice.mp3"
    assert payload["input"]["prompt"] == "держи камеру статично"
    assert "image_url" not in payload
