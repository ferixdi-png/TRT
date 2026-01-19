#!/usr/bin/env python3
"""Verify every registry model has a valid input spec."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Any, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"


def _load_registry() -> Dict[str, Any]:
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
        if not model_data.get("model_type"):
            errors.append(f"{model_id}: missing model_type")
        schema = model_data.get("input")
        if not isinstance(schema, dict) or not schema:
            errors.append(f"{model_id}: missing input schema")
            continue
        model_type = str(model_data.get("model_type") or "").lower()
        required_media = [
            name for name, info in schema.items()
            if isinstance(info, dict) and info.get("required", False) and any(
                key in name.lower() for key in ["image", "mask", "video", "audio", "voice"]
            )
        ]
        if model_type in {"text_to_image", "text_to_video", "text_to_audio", "text_to_speech", "text"} and required_media:
            warnings.append(
                f"{model_id}: SSOT_CONFLICT_TEXT_MODEL_REQUIRES_IMAGE ({', '.join(required_media)})"
            )
        if model_type in {"image_edit", "image_to_image", "image_to_video", "outpaint", "upscale", "video_upscale"}:
            if not required_media:
                warnings.append(
                    f"{model_id}: SSOT_CONFLICT_IMAGE_MODEL_MISSING_IMAGE_INPUT"
                )
        for field_name, field_spec in schema.items():
            if not isinstance(field_spec, dict):
                errors.append(f"{model_id}.{field_name}: field spec must be dict")
                continue
            field_type = field_spec.get("type")
            if not field_type:
                errors.append(f"{model_id}.{field_name}: missing type")
            if field_type == "enum" and not field_spec.get("values"):
                errors.append(f"{model_id}.{field_name}: enum missing values")
            if field_type == "array" and not field_spec.get("item_type"):
                errors.append(f"{model_id}.{field_name}: array missing item_type")

    if warnings:
        print("⚠️ SSOT consistency warnings:")
        for warning in warnings[:20]:
            print(f"- {warning}")
        if len(warnings) > 20:
            print(f"... and {len(warnings) - 20} more")

    if errors:
        print("❌ Model specs verification failed:")
        for error in errors[:20]:
            print(f"- {error}")
        if len(errors) > 20:
            print(f"... and {len(errors) - 20} more")
        return 1

    print(f"✅ Model specs verified for {len(models)} models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
