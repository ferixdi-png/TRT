from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.kie_catalog import get_model
from app.kie_contract.schema_loader import get_model_schema
from app.pricing.price_ssot import list_all_models, list_model_skus, PriceSku


@dataclass(frozen=True)
class ModelSelection:
    model_id: str
    sku: PriceSku
    schema: Dict[str, dict]


def _schema_is_simple(schema: Dict[str, dict]) -> bool:
    for key, spec in schema.items():
        if not isinstance(spec, dict):
            continue
        if not spec.get("required", False):
            continue
        default = spec.get("default")
        if default is not None:
            continue
        lowered = key.lower()
        if lowered in {"prompt", "text"}:
            continue
        if any(token in lowered for token in ("image", "video", "audio", "mask", "file")):
            return False
        return False
    return True


def _build_params(schema: Dict[str, dict], sku_params: Dict[str, object]) -> Dict[str, object]:
    params: Dict[str, object] = {}
    if "prompt" in schema:
        params["prompt"] = "Test prompt"
    if "text" in schema and "prompt" not in params:
        params["text"] = "Test prompt"
    for key, value in sku_params.items():
        params[key] = value
    for key, spec in schema.items():
        if key in params:
            continue
        default = spec.get("default") if isinstance(spec, dict) else None
        if isinstance(spec, dict) and spec.get("required", False):
            lowered = key.lower()
            if any(token in lowered for token in ("image", "video", "audio", "mask", "file")):
                if default:
                    params[key] = default
                else:
                    params[key] = "test"
                continue
        if default is not None:
            params[key] = default
    return params


def select_paid_model() -> Optional[ModelSelection]:
    for model_id in list_all_models():
        model_spec = get_model(model_id)
        if not model_spec:
            continue
        schema = get_model_schema(model_id) or {}
        if any(
            token in key.lower()
            for key in schema.keys()
            for token in ("image", "video", "audio", "mask", "file")
        ):
            continue
        if not _schema_is_simple(schema):
            continue
        skus = list_model_skus(model_id)
        for sku in skus:
            if float(sku.price_rub) <= 0:
                continue
            return ModelSelection(model_id=model_id, sku=sku, schema=schema)
    return None


def select_free_model() -> Optional[ModelSelection]:
    for model_id in list_all_models():
        model_spec = get_model(model_id)
        if not model_spec:
            continue
        schema = get_model_schema(model_id) or {}
        if any(
            token in key.lower()
            for key in schema.keys()
            for token in ("image", "video", "audio", "mask", "file")
        ):
            continue
        if not _schema_is_simple(schema):
            continue
        skus = list_model_skus(model_id)
        for sku in skus:
            if sku.is_free_sku:
                return ModelSelection(model_id=model_id, sku=sku, schema=schema)
    return None


def build_session_payload(selection: ModelSelection) -> Tuple[dict, dict]:
    schema = selection.schema or {}
    params = _build_params(schema, selection.sku.params or {})
    required_keys = [key for key, spec in schema.items() if isinstance(spec, dict) and spec.get("required", False)]
    model_spec = get_model(selection.model_id)
    model_info = {
        "name": getattr(model_spec, "name", selection.model_id) if model_spec else selection.model_id,
    }
    session = {
        "model_id": selection.model_id,
        "params": params,
        "model_info": model_info,
        "gen_type": getattr(model_spec, "model_type", None) if model_spec else None,
        "properties": schema,
        "required": required_keys,
        "sku_id": selection.sku.sku_key,
    }
    return session, params
