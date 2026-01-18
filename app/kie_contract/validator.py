"""KIE contract validator for model input payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.kie_contract.normalizer import normalize_payload
from app.kie_contract.schema_loader import get_model_schema
from app.ux.form_engine import build_form_fields


def validate_payload(model_id: str, payload: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Validate and normalize payload for a model.

    Returns:
        ok, errors, normalized_payload
    """
    schema = get_model_schema(model_id)
    if not schema:
        return False, [f"No schema available for model '{model_id}'"], {}

    normalized = normalize_payload(model_id, payload)
    errors: List[str] = []

    fields = build_form_fields(model_id)
    field_names = {field.name for field in fields}
    required = {field.name for field in fields if field.required}

    missing = required - set(normalized.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    extra = set(normalized.keys()) - field_names
    if extra:
        errors.append(f"Unexpected fields: {sorted(extra)}")

    return not errors, errors, normalized
