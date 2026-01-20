"""Price SSOT loader and helpers for KIE pricing in RUB."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


ROOT = Path(__file__).resolve().parents[2]
PRICING_SSOT_PATH = ROOT / "data" / "kie_pricing_rub.yaml"


@dataclass(frozen=True)
class PriceSku:
    model_id: str
    sku_key: str
    params: Dict[str, Any]
    price_rub: Decimal
    unit: str
    notes: str = ""
    is_free_sku: bool = False


def _normalize_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _build_sku_key(model_id: str, params: Dict[str, Any]) -> str:
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
def load_price_ssot() -> Dict[str, Any]:
    """Load the pricing SSOT data from disk."""
    return _load_yaml(PRICING_SSOT_PATH)


def reset_price_ssot_cache() -> None:
    load_price_ssot.cache_clear()


def _sku_is_free(sku_data: Dict[str, Any]) -> bool:
    if sku_data.get("is_free") is True or sku_data.get("free") is True:
        return True
    price_value = sku_data.get("price_rub")
    try:
        return Decimal(str(price_value)) == Decimal("0")
    except Exception:
        return False


def _iter_skus(model_data: Dict[str, Any], model_id: str) -> Iterable[PriceSku]:
    for sku_data in model_data.get("skus", []) or []:
        params = sku_data.get("params") or {}
        price = Decimal(str(sku_data.get("price_rub", "0")))
        unit = str(sku_data.get("unit", "request"))
        notes = str(sku_data.get("notes", "")) if sku_data.get("notes") else ""
        sku_key = _build_sku_key(model_id, params)
        yield PriceSku(
            model_id=model_id,
            sku_key=sku_key,
            params=params,
            price_rub=price,
            unit=unit,
            notes=notes,
            is_free_sku=_sku_is_free(sku_data),
        )


def list_model_skus(model_id: str) -> List[PriceSku]:
    ssot = load_price_ssot()
    models = ssot.get("models", [])
    if not isinstance(models, list):
        return []
    for model in models:
        if not isinstance(model, dict):
            continue
        if model.get("id") != model_id:
            continue
        return list(_iter_skus(model, model_id))
    return []


def list_all_models() -> List[str]:
    ssot = load_price_ssot()
    models = ssot.get("models", [])
    if not isinstance(models, list):
        return []
    return [model.get("id") for model in models if isinstance(model, dict) and model.get("id")]


def resolve_sku_for_params(model_id: str, params: Dict[str, Any]) -> Optional[PriceSku]:
    skus = list_model_skus(model_id)
    if not skus:
        return None
    normalized = {k: _normalize_param_value(v) for k, v in (params or {}).items()}
    matches: List[PriceSku] = []
    for sku in skus:
        sku_params = {k: _normalize_param_value(v) for k, v in sku.params.items()}
        if any(normalized.get(k) != v for k, v in sku_params.items()):
            continue
        matches.append(sku)
    if len(matches) == 1:
        return matches[0]
    return None


def get_price_for_params(model_id: str, selected_params: Dict[str, Any]) -> Optional[Decimal]:
    sku = resolve_sku_for_params(model_id, selected_params)
    return sku.price_rub if sku else None


def get_min_price(model_id: str) -> Optional[Decimal]:
    skus = list_model_skus(model_id)
    if not skus:
        return None
    return min((sku.price_rub for sku in skus), default=None)


def list_variants_with_prices(
    model_id: str,
    param_name: str,
    current_partial_params: Dict[str, Any],
) -> List[Tuple[str, Decimal]]:
    skus = list_model_skus(model_id)
    if not skus:
        return []
    normalized_partial = {k: _normalize_param_value(v) for k, v in (current_partial_params or {}).items()}
    normalized_partial.pop(param_name, None)
    values: Dict[str, Decimal] = {}
    for sku in skus:
        if param_name not in sku.params:
            continue
        sku_params = {k: _normalize_param_value(v) for k, v in sku.params.items()}
        if any(normalized_partial.get(k) != v for k, v in normalized_partial.items()):
            continue
        value = _normalize_param_value(sku.params.get(param_name))
        current_price = values.get(value)
        if current_price is None or sku.price_rub < current_price:
            values[value] = sku.price_rub
    return sorted(values.items(), key=lambda item: item[0])


def model_has_free_sku(model_id: str) -> bool:
    return any(sku.is_free_sku for sku in list_model_skus(model_id))


def list_free_sku_keys() -> List[str]:
    free_skus: List[str] = []
    for model_id in list_all_models():
        for sku in list_model_skus(model_id):
            if sku.is_free_sku:
                free_skus.append(sku.sku_key)
    return free_skus
