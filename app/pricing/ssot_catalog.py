"""Pricing SSOT catalog loader and resolver for RUB pricing."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from app.kie_contract.schema_loader import get_model_schema, get_model_meta

_sku_callback_map: Dict[str, str] = {}


ROOT = Path(__file__).resolve().parents[2]
PRICING_SSOT_PATH = ROOT / "data" / "kie_pricing_rub.yaml"
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


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_pricing_ssot() -> Dict[str, Any]:
    return _load_yaml(PRICING_SSOT_PATH)


def _iter_skus(model_data: Dict[str, Any], model_id: str) -> Iterable[PricingSku]:
    for sku_data in model_data.get("skus", []) or []:
        params = sku_data.get("params") or {}
        price = Decimal(str(sku_data.get("price_rub", "0")))
        unit = str(sku_data.get("unit", "request"))
        notes = str(sku_data.get("notes", "")) if sku_data.get("notes") else ""
        status = str(sku_data.get("status", "READY")).upper()
        sku_id = _build_sku_id(model_id, params)
        yield PricingSku(
            sku_id=sku_id,
            model_id=model_id,
            price_rub=price,
            unit=unit,
            params=params,
            notes=notes,
            status=status,
        )


def list_model_skus(model_id: str, *, include_non_ready: bool = False) -> List[PricingSku]:
    ssot = load_pricing_ssot()
    models = ssot.get("models", [])
    if not isinstance(models, list):
        return []
    for model in models:
        if not isinstance(model, dict):
            continue
        if model.get("id") != model_id:
            continue
        skus = list(_iter_skus(model, model_id))
        if include_non_ready:
            return skus
        return [sku for sku in skus if sku.status == "READY"]
    return []


def resolve_sku_for_params(model_id: str, params: Dict[str, Any]) -> Optional[PricingSku]:
    skus = list_model_skus(model_id)
    if not skus:
        return None
    normalized = {k: _normalize_param_value(v) for k, v in (params or {}).items()}
    matches: List[PricingSku] = []
    for sku in skus:
        sku_params = {k: _normalize_param_value(v) for k, v in sku.params.items()}
        if any(normalized.get(k) != v for k, v in sku_params.items()):
            continue
        matches.append(sku)
    if len(matches) == 1:
        return matches[0]
    return None


def get_min_price_rub(model_id: str) -> Optional[Decimal]:
    skus = list_model_skus(model_id)
    if not skus:
        return None
    return min((sku.price_rub for sku in skus), default=None)


def get_sku_param_summary(sku: PricingSku) -> str:
    if not sku.params:
        return "default"
    return ", ".join(f"{key}={_normalize_param_value(value)}" for key, value in sorted(sku.params.items()))


def _slugify_model_id(model_id: str) -> str:
    return model_id.lower().replace("/", "-").replace("_", "-")


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
    anchor = _slugify_model_id(model_id)
    link = f"PRICING_COVERAGE.md#model-{anchor}"
    if user_lang == "ru":
        issues_text = "\n".join(f"• {issue}" for issue in issues) if issues else "• Причина не указана"
        return (
            "⛔️ <b>Модель заблокирована</b>\n\n"
            f"Причина: <code>{status}</code>\n"
            f"{issues_text}\n\n"
            f"Подробнее: <code>{link}</code>"
        )
    issues_text = "\n".join(f"• {issue}" for issue in issues) if issues else "• No details available"
    return (
        "⛔️ <b>Model blocked</b>\n\n"
        f"Reason: <code>{status}</code>\n"
        f"{issues_text}\n\n"
        f"Details: <code>{link}</code>"
    )


def _get_model_type(model_id: str) -> str:
    meta = get_model_meta(model_id) or {}
    return (meta.get("model_type") or "").lower()


def _sku_is_text_to_video(sku: PricingSku) -> bool:
    return _get_model_type(sku.model_id) == "text_to_video"


def get_free_sku_ids() -> List[str]:
    ssot = load_pricing_ssot()
    models = ssot.get("models", [])
    if not isinstance(models, list):
        return []
    cheapest_per_model: List[PricingSku] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if not model_id:
            continue
        skus = [sku for sku in _iter_skus(model, model_id) if sku.status == "READY"]
        if not skus:
            continue
        cheapest_per_model.append(min(skus, key=lambda sku: sku.price_rub))
    cheapest_per_model.sort(key=lambda sku: (sku.price_rub, sku.model_id))
    selected = cheapest_per_model[:5]
    if selected and not any(_sku_is_text_to_video(sku) for sku in selected):
        t2v_candidates = [sku for sku in cheapest_per_model if _sku_is_text_to_video(sku)]
        if t2v_candidates:
            replacement = min(t2v_candidates, key=lambda sku: sku.price_rub)
            if selected:
                selected[-1] = replacement
    return [sku.sku_id for sku in selected]


@lru_cache(maxsize=512)
def get_sku_by_id(sku_id: str) -> Optional[PricingSku]:
    ssot = load_pricing_ssot()
    models = ssot.get("models", [])
    if not isinstance(models, list):
        return None
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if not model_id:
            continue
        for sku in _iter_skus(model, model_id):
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
