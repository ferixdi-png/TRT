import sys
from pathlib import Path

import pytest

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.kie_catalog import get_model
from app.kie_contract.payload_builder import build_kie_payload
from app.models.registry import get_generation_types
from app.pricing.price_ssot import list_all_models
from app.pricing.ssot_catalog import encode_sku_callback, list_model_skus, resolve_sku_callback


def _build_params_for_sku(spec, sku):
    params = dict(sku.params or {})
    for field in spec.schema_required or []:
        if field in params and params[field] not in (None, ""):
            continue
        schema = spec.schema_properties.get(field, {})
        param_type = schema.get("type", "string")
        enum_values = schema.get("enum") or schema.get("values") or []
        if isinstance(enum_values, dict):
            enum_values = list(enum_values.values())
        if param_type == "enum" and enum_values:
            params[field] = enum_values[0]
        elif param_type == "boolean":
            params[field] = True
        elif param_type in {"number", "integer", "float"}:
            params[field] = 1
        elif param_type == "array":
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


def test_all_skus_have_model_and_payload():
    generation_types = set(get_generation_types())
    for model_id in list_all_models():
        spec = get_model(model_id)
        assert spec is not None, f"Missing model spec for {model_id}"
        model_gen_type = (spec.model_mode or spec.model_type or "").replace("_", "-")
        assert model_gen_type in generation_types, f"Invalid generation type for {model_id}"

        skus = list_model_skus(model_id)
        if not skus:
            continue
        for sku in skus:
            callback = encode_sku_callback(sku.sku_id)
            assert resolve_sku_callback(callback) == sku.sku_id
            assert sku.price_rub is not None
            params = _build_params_for_sku(spec, sku)
            payload = build_kie_payload(spec, params)
            assert payload.get("model")
            assert payload.get("input") is not None
