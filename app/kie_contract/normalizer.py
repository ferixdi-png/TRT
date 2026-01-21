"""KIE contract normalizer for model payloads."""
from __future__ import annotations

from typing import Any, Dict

from app.kie_contract.schema_loader import get_model_schema


def _coerce_value(field_type: str, value: Any) -> Any:
    if value is None:
        return value
    if field_type in {"number", "integer"}:
        if isinstance(value, str) and value.strip():
            try:
                numeric_value = float(value) if field_type == "number" else int(value)
            except ValueError:
                try:
                    numeric_value = float(value)
                except ValueError:
                    return value
            if field_type == "integer":
                if isinstance(numeric_value, float) and numeric_value.is_integer():
                    return int(numeric_value)
                return numeric_value if isinstance(numeric_value, int) else value
            if isinstance(numeric_value, float) and numeric_value.is_integer():
                return int(numeric_value)
            return numeric_value
        if field_type == "integer" and isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    if field_type == "boolean":
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
    if field_type == "array":
        if isinstance(value, str):
            return [value]
    return value


def normalize_payload(model_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize payload values based on the registry schema."""
    schema = get_model_schema(model_id)
    if not schema:
        return dict(payload)

    normalized: Dict[str, Any] = dict(payload)
    for field_name, field_spec in schema.items():
        if field_name not in payload:
            continue
        field_type = field_spec.get("type", "string")
        value = payload[field_name]
        normalized[field_name] = _coerce_value(field_type, value)
    return normalized
