"""Pricing SSOT catalog loader and resolver for RUB pricing."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.kie_contract.schema_loader import get_model_schema, get_model_meta
from app.pricing.price_ssot import (
    PriceSku,
    get_min_price,
    list_all_models,
    list_free_sku_keys,
    list_model_skus as list_price_model_skus,
    load_price_ssot,
    resolve_sku_for_params as resolve_price_sku_for_params,
)

_sku_callback_map: Dict[str, str] = {}


ROOT = Path(__file__).resolve().parents[2]
PRICING_COVERAGE_PATH = ROOT / "PRICING_COVERAGE.json"


@dataclass(frozen=True)
class PricingSku:
    sku_id: str
    model_id: str
    price_rub: Decimal
    unit: str
    params: Dict[str, Any]
    notes: str = ""
    status: str = "READY"
    is_free_sku: bool = False


def _normalize_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _build_sku_id(model_id: str, params: Dict[str, Any]) -> str:
    if not params:
        return f"{model_id}::default"
    parts = [f"{key}={_normalize_param_value(params[key])}" for key in sorted(params)]
    return f"{model_id}::" + "|".join(parts)


@lru_cache(maxsize=1)
def load_pricing_ssot() -> Dict[str, Any]:
    return load_price_ssot()


def list_model_skus(model_id: str, *, include_non_ready: bool = False) -> List[PricingSku]:
    skus = list_price_model_skus(model_id)
    return [
        PricingSku(
            sku_id=sku.sku_key,
            model_id=sku.model_id,
            price_rub=sku.price_rub,
            unit=sku.unit,
            params=sku.params,
            notes=sku.notes,
            status="READY",
            is_free_sku=sku.is_free_sku,
        )
        for sku in skus
    ]


def resolve_sku_for_params(model_id: str, params: Dict[str, Any]) -> Optional[PricingSku]:
    sku = resolve_price_sku_for_params(model_id, params)
    if not sku:
        return None
    return PricingSku(
        sku_id=sku.sku_key,
        model_id=sku.model_id,
        price_rub=sku.price_rub,
        unit=sku.unit,
        params=sku.params,
        notes=sku.notes,
        status="READY",
        is_free_sku=sku.is_free_sku,
    )


def get_min_price_rub(model_id: str) -> Optional[Decimal]:
    return get_min_price(model_id)


def get_sku_param_summary(sku: PricingSku) -> str:
    if not sku.params:
        return "default"
    return ", ".join(f"{key}={_normalize_param_value(value)}" for key, value in sorted(sku.params.items()))


def _slugify_model_id(model_id: str) -> str:
    return model_id.lower().replace("/", "-").replace("_", "-")


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    import yaml

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def get_pricing_coverage_entry(model_id: str) -> Optional[Dict[str, Any]]:
    if not PRICING_COVERAGE_PATH.exists():
        return None
    data = _load_yaml(PRICING_COVERAGE_PATH)
    if not isinstance(data, dict):
        return None
    coverage = data.get("models", {})
    if isinstance(coverage, dict):
        return coverage.get(model_id)
    return None


def format_pricing_blocked_message(model_id: str, *, user_lang: str) -> str:
    entry = get_pricing_coverage_entry(model_id) or {}
    status = entry.get("status", "MISSING_PRICE")
    issues = entry.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    missing_skus = entry.get("missing_skus", [])
    if isinstance(missing_skus, list) and missing_skus:
        if user_lang == "ru":
            issues.append("Отсутствуют SKU: " + ", ".join(missing_skus))
        else:
            issues.append("Missing SKU: " + ", ".join(missing_skus))
    anchor = _slugify_model_id(model_id)
    link = f"PRICING_COVERAGE.md#model-{anchor}"
    status_display = status
    if status == "READY":
        status_display = "NO_PRICE_FOR_PARAMS"
        if not issues:
            issues = ["Нет цены для выбранных параметров (SKU не найден)."]
    if user_lang == "ru":
        issues_text = "\n".join(f"• {issue}" for issue in issues) if issues else "• Причина не указана"
        return (
            "⛔️ <b>Модель заблокирована</b>\n\n"
            f"Причина: <code>{status_display}</code>\n"
            f"{issues_text}\n\n"
            f"Подробнее: <code>{link}</code>"
        )
    issues_text = "\n".join(f"• {issue}" for issue in issues) if issues else "• No details available"
    return (
        "⛔️ <b>Model blocked</b>\n\n"
        f"Reason: <code>{status_display}</code>\n"
        f"{issues_text}\n\n"
        f"Details: <code>{link}</code>"
    )


def _get_model_type(model_id: str) -> str:
    meta = get_model_meta(model_id) or {}
    return (meta.get("model_type") or "").lower()


def _sku_is_text_to_video(sku: PricingSku) -> bool:
    return _get_model_type(sku.model_id) == "text_to_video"


def get_free_sku_ids() -> List[str]:
    return list_free_sku_keys()


@lru_cache(maxsize=512)
def get_sku_by_id(sku_id: str) -> Optional[PricingSku]:
    for model_id in list_all_models():
        for sku in list_model_skus(model_id):
            if sku.sku_id == sku_id:
                return sku
    return None


def encode_sku_callback(sku_id: str) -> str:
    payload = f"sku:{sku_id}"
    if len(payload.encode("utf-8")) <= 60:
        return payload
    import hashlib

    short_hash = hashlib.md5(sku_id.encode("utf-8")).hexdigest()[:10]
    short = f"sk:{short_hash}"
    _sku_callback_map[short] = sku_id
    return short


def resolve_sku_callback(callback_data: str) -> Optional[str]:
    if callback_data.startswith("sku:"):
        return callback_data[4:]
    if callback_data.startswith("sk:"):
        return _sku_callback_map.get(callback_data)
    return None


def get_price_dimensions(model_id: str) -> List[str]:
    skus = list_model_skus(model_id)
    dims: set[str] = set()
    for sku in skus:
        dims.update(sku.params.keys())
    return sorted(dims)


def build_param_combinations(model_id: str) -> Tuple[List[Dict[str, str]], List[str]]:
    schema = get_model_schema(model_id) or {}
    dims = get_price_dimensions(model_id)
    issues: List[str] = []
    if not dims:
        return [{}], issues
    values: List[Tuple[str, List[str]]] = []
    for dim in dims:
        dim_info = schema.get(dim)
        if not dim_info:
            issues.append(f"Missing schema for pricing param '{dim}'")
            continue
        enum_values = dim_info.get("values") or dim_info.get("enum")
        if not enum_values:
            issues.append(f"Missing enum values for pricing param '{dim}'")
            continue
        values.append((dim, [str(value) for value in enum_values]))
    combos = [{}]
    for dim, enum_vals in values:
        combos = [
            {**combo, dim: enum_val}
            for combo in combos
            for enum_val in enum_vals
        ]
    return combos, issues


def validate_pricing_schema_consistency() -> Dict[str, List[str]]:
    """Validate SKU params against model schema and generation types."""
    from app.kie_catalog import get_model
    from app.models.registry import get_generation_types

    issues: Dict[str, List[str]] = {}
    generation_types = set(get_generation_types())

    for model_id in list_all_models():
        spec = get_model(model_id)
        if not spec:
            issues.setdefault(model_id, []).append("Missing model spec for pricing model")
            continue
        model_gen_type = (spec.model_mode or spec.model_type or "").replace("_", "-")
        if model_gen_type and model_gen_type not in generation_types:
            issues.setdefault(model_id, []).append(
                f"Unknown generation type '{model_gen_type}' for model spec"
            )
        schema_props = spec.schema_properties or {}
        for sku in list_model_skus(model_id):
            for param_key in (sku.params or {}).keys():
                if param_key not in schema_props:
                    issues.setdefault(model_id, []).append(
                        f"SKU param '{param_key}' missing in schema"
                    )
    return issues
