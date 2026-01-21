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
    min_items: Optional[int] = None
    max_items: Optional[int] = None


class FormSpecError(ValueError):
    """Raised when a model schema is missing or invalid."""


def build_form_fields(model_id: str) -> List[FieldSpec]:
    """Build field specs from the registry schema."""
    schema = get_model_schema(model_id)
    if not schema:
        raise FormSpecError(f"No schema available for model '{model_id}'")
    fields: List[FieldSpec] = []
    for field_name, field_data in schema.items():
        enum_values = field_data.get("enum")
        if enum_values is None:
            enum_values = field_data.get("values")
        if isinstance(enum_values, str):
            enum_values = [enum_values]
        fields.append(
            FieldSpec(
                name=field_name,
                field_type=field_data.get("type", "string"),
                required=bool(field_data.get("required", False)),
                enum=enum_values,
                item_type=field_data.get("item_type"),
                min_value=field_data.get("min"),
                max_value=field_data.get("max"),
                min_items=field_data.get("min_items"),
                max_items=field_data.get("max_items"),
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
        if field.min_value is not None and len(value) < int(field.min_value):
            return f"{field.name} must be at least {field.min_value} characters"
        if field.max_value is not None and len(value) > int(field.max_value):
            return f"{field.name} exceeds max length {field.max_value}"
    elif field_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{field.name} must be an integer"
        if field.min_value is not None and value < field.min_value:
            return f"{field.name} must be >= {field.min_value}"
        if field.max_value is not None and value > field.max_value:
            return f"{field.name} must be <= {field.max_value}"
    elif field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{field.name} must be a number"
        if field.min_value is not None and value < field.min_value:
            return f"{field.name} must be >= {field.min_value}"
        if field.max_value is not None and value > field.max_value:
            return f"{field.name} must be <= {field.max_value}"
    elif field_type == "boolean":
        if not isinstance(value, bool):
            return f"{field.name} must be a boolean"
    elif field_type == "enum":
        if field.enum:
            candidate = str(value)
            allowed = {str(option) for option in field.enum}
            if candidate not in allowed:
                return f"{field.name} must be one of {field.enum}"
    elif field_type == "array":
        if not isinstance(value, list):
            return f"{field.name} must be an array"
        if field.min_items is not None and len(value) < field.min_items:
            return f"{field.name} must contain at least {field.min_items} items"
        if field.max_items is not None and len(value) > field.max_items:
            return f"{field.name} must contain at most {field.max_items} items"
        if field.item_type:
            for idx, item in enumerate(value):
                if field.item_type == "string" and not isinstance(item, str):
                    return f"{field.name}[{idx}] must be a string"
                if field.item_type == "number" and (isinstance(item, bool) or not isinstance(item, (int, float))):
                    return f"{field.name}[{idx}] must be a number"
                if field.item_type == "integer" and (isinstance(item, bool) or not isinstance(item, int)):
                    return f"{field.name}[{idx}] must be an integer"
                if field.item_type == "boolean" and not isinstance(item, bool):
                    return f"{field.name}[{idx}] must be a boolean"
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

    def _is_empty_required(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, list):
            return len(value) == 0
        return False

    for field in fields:
        if field.required and (field.name not in payload or _is_empty_required(payload.get(field.name))):
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
