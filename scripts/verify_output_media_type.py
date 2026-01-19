#!/usr/bin/env python3
"""Validate SSOT output_media_type compatibility and allowed values."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"

ALLOWED_MEDIA_TYPES = {"image", "video", "audio", "text", "document"}
MODEL_TYPE_TO_MEDIA = {
    "text_to_image": "image",
    "image_to_image": "image",
    "image_edit": "image",
    "outpaint": "image",
    "upscale": "image",
    "text_to_video": "video",
    "image_to_video": "video",
    "video_upscale": "video",
    "speech_to_video": "video",
    "text_to_speech": "audio",
    "audio_to_audio": "audio",
    "speech_to_text": "text",
}


def _load_registry() -> Dict[str, Any]:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Missing registry file: {REGISTRY_PATH}")
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    registry = _load_registry()
    models = registry.get("models", {})
    if not isinstance(models, dict) or not models:
        print("❌ Registry has no models")
        return 1

    errors: List[str] = []
    warnings: List[str] = []

    for model_id, model_data in models.items():
        if not isinstance(model_data, dict):
            errors.append(f"{model_id}: model entry is not a dict")
            continue
        model_type = str(model_data.get("model_type") or "").lower()
        output_media_type = model_data.get("output_media_type")
        if output_media_type:
            output_media_type = str(output_media_type).lower()
        expected = MODEL_TYPE_TO_MEDIA.get(model_type)
        resolved = output_media_type or expected
        if not resolved:
            errors.append(f"{model_id}: missing output_media_type and no mapping for model_type={model_type}")
            continue
        if resolved not in ALLOWED_MEDIA_TYPES:
            errors.append(f"{model_id}: invalid output_media_type={resolved}")
            continue
        if expected and resolved != expected:
            errors.append(
                f"{model_id}: output_media_type={resolved} incompatible with model_type={model_type} (expected {expected})"
            )
        if not output_media_type:
            warnings.append(f"{model_id}: output_media_type missing, resolved to {resolved}")

    if warnings:
        print("⚠️ output_media_type warnings:")
        for warning in warnings[:20]:
            print(f"- {warning}")
        if len(warnings) > 20:
            print(f"... and {len(warnings) - 20} more")

    if errors:
        print("❌ output_media_type validation failed:")
        for error in errors[:20]:
            print(f"- {error}")
        if len(errors) > 20:
            print(f"... and {len(errors) - 20} more")
        return 1

    print(f"✅ output_media_type validated for {len(models)} models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
