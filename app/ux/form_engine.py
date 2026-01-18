"""UX form engine for spec-driven model inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.kie_contract.schema_loader import get_model_schema


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: str
    required: bool
    enum: Optional[List[Any]] = None
    item_type: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class FormSpecError(ValueError):
    """Raised when a model schema is missing or invalid."""


def build_form_fields(model_id: str) -> List[FieldSpec]:
    """Build field specs from the registry schema."""
    schema = get_model_schema(model_id)
    if not schema:
        raise FormSpecError(f"No schema available for model '{model_id}'")
    fields: List[FieldSpec] = []
    for field_name, field_data in schema.items():
        fields.append(
            FieldSpec(
                name=field_name,
                field_type=field_data.get("type", "string"),
                required=bool(field_data.get("required", False)),
                enum=field_data.get("values"),
                item_type=field_data.get("item_type"),
                min_value=field_data.get("min"),
                max_value=field_data.get("max"),
            )
        )
    return fields


def _validate_type(field: FieldSpec, value: Any) -> Optional[str]:
    if value is None:
        return None
    field_type = field.field_type
    if field_type == "string":
        if not isinstance(value, str):
            return f"{field.name} must be a string"
        if field.max_value is not None and len(value) > int(field.max_value):
            return f"{field.name} exceeds max length {field.max_value}"
    elif field_type == "number":
        if not isinstance(value, (int, float)):
            return f"{field.name} must be a number"
        if field.min_value is not None and value < field.min_value:
            return f"{field.name} must be >= {field.min_value}"
        if field.max_value is not None and value > field.max_value:
            return f"{field.name} must be <= {field.max_value}"
    elif field_type == "boolean":
        if not isinstance(value, bool):
            return f"{field.name} must be a boolean"
    elif field_type == "enum":
        if field.enum and value not in field.enum:
            return f"{field.name} must be one of {field.enum}"
    elif field_type == "array":
        if not isinstance(value, list):
            return f"{field.name} must be an array"
        if field.item_type:
            for idx, item in enumerate(value):
                if field.item_type == "string" and not isinstance(item, str):
                    return f"{field.name}[{idx}] must be a string"
    return None


def validate_payload(
    model_id: str,
    payload: Dict[str, Any],
    *,
    ignore_unknown: bool = False,
) -> Tuple[bool, List[str]]:
    """Validate payload against registry schema for a model."""
    try:
        fields = build_form_fields(model_id)
    except FormSpecError as exc:
        return False, [str(exc)]

    errors: List[str] = []
    field_map = {field.name: field for field in fields}

    for field in fields:
        if field.required and field.name not in payload:
            errors.append(f"{field.name} is required")

    for key, value in payload.items():
        field = field_map.get(key)
        if not field:
            if not ignore_unknown:
                errors.append(f"{key} is not allowed for this model")
            continue
        error = _validate_type(field, value)
        if error:
            errors.append(error)

    return not errors, errors


def summarize_required_fields(model_id: str) -> List[str]:
    """Return a list of required field names for model UX cards."""
    try:
        fields = build_form_fields(model_id)
    except FormSpecError:
        return []
    return [field.name for field in fields if field.required]
