"""Model visibility rules based on model registry and pricing SSOT."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.kie_contract.schema_loader import get_model_schema
from app.models.registry_validator import get_invalid_model_ids, get_model_issues
from app.pricing.coverage_guard import get_disabled_model_info
from app.pricing.price_ssot import list_model_skus


STATUS_READY_VISIBLE = "READY_VISIBLE"
STATUS_HIDDEN_NO_INSTRUCTIONS = "HIDDEN_NO_INSTRUCTIONS"
STATUS_BLOCKED_NO_PRICE = "BLOCKED_NO_PRICE"
STATUS_BLOCKED_REQUIRED_MISSING = "BLOCKED_REQUIRED_MISSING"
STATUS_BLOCKED_INVALID_REGISTRY = "BLOCKED_INVALID_REGISTRY"
STATUS_BLOCKED_UNSUPPORTED = "BLOCKED_UNSUPPORTED"


DEFAULT_UNSUPPORTED_MODELS = {
    # KIE currently rejects this model id with 422 validation_error.
    "openai/4o-image",
}


def _parse_env_models(value: str) -> Iterable[str]:
    for raw in value.split(","):
        model_id = raw.strip()
        if model_id:
            yield model_id


@lru_cache(maxsize=1)
def _unsupported_models() -> set[str]:
    env_value = os.getenv("KIE_UNSUPPORTED_MODELS", "")
    env_models = set(_parse_env_models(env_value)) if env_value else set()
    return set(DEFAULT_UNSUPPORTED_MODELS) | env_models


@dataclass(frozen=True)
class ModelVisibilityResult:
    model_id: str
    status: str
    issues: List[str]
    required_fields: List[str]
    optional_fields: List[str]
    defaults: Dict[str, Any]


def _extract_schema_fields(schema: Dict[str, Any]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    required: List[str] = []
    optional: List[str] = []
    defaults: Dict[str, Any] = {}
    for name, spec in (schema or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("required"):
            required.append(name)
        else:
            optional.append(name)
        if "default" in spec:
            defaults[name] = spec.get("default")
    return sorted(required), sorted(optional), defaults


def _enum_values(spec: Dict[str, Any]) -> List[str]:
    values = spec.get("values")
    if values is None:
        values = spec.get("enum")
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values]


def evaluate_model_visibility(model_id: str) -> ModelVisibilityResult:
    if model_id in _unsupported_models():
        return ModelVisibilityResult(
            model_id=model_id,
            status=STATUS_BLOCKED_UNSUPPORTED,
            issues=["Модель временно не поддерживается KIE API."],
            required_fields=[],
            optional_fields=[],
            defaults={},
        )

    invalid_ids = get_invalid_model_ids()
    if model_id in invalid_ids:
        issues = get_model_issues(model_id) or ["Registry validation failed for model."]
        return ModelVisibilityResult(
            model_id=model_id,
            status=STATUS_BLOCKED_INVALID_REGISTRY,
            issues=issues,
            required_fields=[],
            optional_fields=[],
            defaults={},
        )

    disabled_info = get_disabled_model_info(model_id)
    if disabled_info:
        return ModelVisibilityResult(
            model_id=model_id,
            status=STATUS_BLOCKED_NO_PRICE,
            issues=disabled_info.issues or ["Нет цены для выбранных параметров."],
            required_fields=[],
            optional_fields=[],
            defaults={},
        )

    schema = get_model_schema(model_id)
    skus = list_model_skus(model_id)
    issues: List[str] = []

    if not schema:
        status = STATUS_HIDDEN_NO_INSTRUCTIONS if skus else STATUS_HIDDEN_NO_INSTRUCTIONS
        return ModelVisibilityResult(
            model_id=model_id,
            status=status,
            issues=["Нет инструкций модели в registry."],
            required_fields=[],
            optional_fields=[],
            defaults={},
        )

    required_fields, optional_fields, defaults = _extract_schema_fields(schema)

    missing_required_fields = [
        name
        for name in required_fields
        if not _enum_values(schema.get(name, {})) and (schema.get(name, {}).get("type") == "enum")
    ]
    if missing_required_fields:
        issues.append(f"Нет вариантов для обязательных полей: {', '.join(sorted(missing_required_fields))}")
        return ModelVisibilityResult(
            model_id=model_id,
            status=STATUS_BLOCKED_REQUIRED_MISSING,
            issues=issues,
            required_fields=required_fields,
            optional_fields=optional_fields,
            defaults=defaults,
        )

    if not skus:
        return ModelVisibilityResult(
            model_id=model_id,
            status=STATUS_BLOCKED_NO_PRICE,
            issues=["Нет ценовых SKU в прайс-SSOT."],
            required_fields=required_fields,
            optional_fields=optional_fields,
            defaults=defaults,
        )

    sku_values_by_param: Dict[str, set[str]] = {}
    for sku in skus:
        for param_name, param_value in sku.params.items():
            sku_values_by_param.setdefault(param_name, set()).add(str(param_value))

    missing_variants: List[str] = []
    for param_name, spec in schema.items():
        if not isinstance(spec, dict):
            continue
        enum_vals = _enum_values(spec)
        if not enum_vals:
            continue
        sku_values = sku_values_by_param.get(param_name)
        if not sku_values:
            continue
        missing = [value for value in enum_vals if str(value) not in sku_values]
        if missing:
            missing_variants.append(f"{param_name}: {', '.join(missing)}")

    if missing_variants:
        issues.append("Нет цены для вариантов: " + "; ".join(missing_variants))
        return ModelVisibilityResult(
            model_id=model_id,
            status=STATUS_BLOCKED_NO_PRICE,
            issues=issues,
            required_fields=required_fields,
            optional_fields=optional_fields,
            defaults=defaults,
        )

    return ModelVisibilityResult(
        model_id=model_id,
        status=STATUS_READY_VISIBLE,
        issues=[],
        required_fields=required_fields,
        optional_fields=optional_fields,
        defaults=defaults,
    )


def is_model_visible(model_id: str) -> bool:
    return evaluate_model_visibility(model_id).status == STATUS_READY_VISIBLE
