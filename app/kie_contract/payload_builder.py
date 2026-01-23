"""Universal payload builder for KIE models based on SSOT."""
from __future__ import annotations

from typing import Any, Dict, List

from app.kie_catalog import ModelSpec
from app.models.canonical import canonicalize_kie_model
from app.kie_contract.image_adapter import adapt_image_input
from app.kie_contract.normalizer import _coerce_value


class PayloadBuildError(ValueError):
    """Raised when payload cannot be built from params."""


def _apply_defaults(schema: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(params)
    for field_name, field_spec in schema.items():
        if field_name not in updated and field_spec.get("default") is not None:
            updated[field_name] = field_spec.get("default")
    return updated


def _normalize_params(schema: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for field_name, field_spec in schema.items():
        if field_name not in params:
            continue
        field_type = field_spec.get("type", "string")
        normalized[field_name] = _coerce_value(field_type, params[field_name])
    return normalized


def _validate_required(required: List[str], params: Dict[str, Any]) -> List[str]:
    missing = []
    for field in required:
        if field not in params or params[field] in (None, ""):
            missing.append(field)
    return missing


def build_kie_payload(model_spec: ModelSpec, session_params: Dict[str, Any]) -> Dict[str, Any]:
    """Build KIE payload using schema-defined fields only."""
    schema = model_spec.schema_properties or {}
    required = model_spec.schema_required or []
    params_with_defaults = _apply_defaults(schema, session_params)
    normalized = _normalize_params(schema, params_with_defaults)

    missing = _validate_required(required, normalized)
    if missing:
        raise PayloadBuildError(f"Missing required fields: {', '.join(missing)}")

    adapted = adapt_image_input(model_spec.id, normalized)
    return {"model": canonicalize_kie_model(model_spec.kie_model), "input": adapted}
