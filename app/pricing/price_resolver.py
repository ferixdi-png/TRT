"""
Single price resolver for KIE models.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
import re
from typing import Any, Dict, Optional

from app.config import Settings, get_settings
from app.kie_catalog import get_model
from app.models.canonical import canonicalize_model_id
from app.pricing.price_ssot import list_model_skus, resolve_sku_for_params

logger = logging.getLogger(__name__)
_pricing_ok_logged: set[str] = set()


PRICE_QUANT = Decimal("0.01")
PRICING_DEFAULT_PARAMS: Dict[str, Dict[str, Any]] = {
    "sora-2-text-to-video": {"n_frames": "10"},
    "sora-2-image-to-video": {"n_frames": "10"},
    "sora-2-pro-text-to-video": {"n_frames": "10", "size": "standard"},
    "sora-2-pro-image-to-video": {"n_frames": "10", "size": "standard"},
}


@dataclass(frozen=True)
class PriceQuote:
    price_rub: Decimal
    currency: str
    breakdown: Dict[str, Any]
    sku_id: str


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _normalize_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _quantize_price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def format_price_rub(value: Decimal | float | str) -> str:
    """Format a RUB value with 2 decimal places."""
    return f"{_quantize_price(_to_decimal(value)):.2f}"


def _parse_resolution_from_notes(notes: Optional[str]) -> Optional[str]:
    if not notes:
        return None
    match = re.search(r"(\d+p|\d+k)", notes, re.IGNORECASE)
    if not match:
        return None
    raw_value = match.group(1)
    if raw_value.lower().endswith("k"):
        return raw_value[:-1] + "K"
    return raw_value.lower()


def _parse_duration_from_notes(notes: Optional[str]) -> Optional[str]:
    if not notes:
        return None
    match = re.search(r"(\d+\.?\d*)s", notes, re.IGNORECASE)
    if not match:
        return None
    raw_value = match.group(1)
    try:
        numeric = float(raw_value)
    except ValueError:
        return raw_value
    if numeric.is_integer():
        return str(int(numeric))
    return raw_value


def _apply_mode_defaults(model_id: str, mode_index: Optional[int], normalized: Dict[str, Any]) -> None:
    model_spec = get_model(model_id)
    if not model_spec or not model_spec.modes:
        return
    resolved_mode_index = mode_index
    if resolved_mode_index is None:
        if len(model_spec.modes) != 1:
            return
        resolved_mode_index = 0
    if resolved_mode_index < 0 or resolved_mode_index >= len(model_spec.modes):
        return
    mode = model_spec.modes[resolved_mode_index]
    notes = getattr(mode, "notes", None)
    if not notes:
        return
    if "resolution" not in normalized or normalized.get("resolution") in (None, ""):
        resolution = _parse_resolution_from_notes(notes)
        if resolution:
            normalized["resolution"] = resolution
    if "duration" not in normalized or normalized.get("duration") in (None, ""):
        duration = _parse_duration_from_notes(notes)
        if duration:
            normalized["duration"] = duration


def _backfill_from_cheapest_sku(model_id: str, normalized: Dict[str, Any]) -> None:
    skus = list_model_skus(model_id)
    if not skus:
        return
    sku_param_keys: set[str] = set()
    for sku in skus:
        sku_param_keys.update((sku.params or {}).keys())
    missing_keys = [
        key
        for key in sku_param_keys
        if key not in normalized or normalized.get(key) in (None, "")
    ]
    if not missing_keys:
        return

    consistent_skus = []
    for sku in skus:
        sku_params = sku.params or {}
        if any(
            _normalize_param_value(normalized.get(key)) != _normalize_param_value(value)
            for key, value in sku_params.items()
            if key in normalized
        ):
            continue
        consistent_skus.append(sku)
    if not consistent_skus:
        return

    default_sku = min(consistent_skus, key=lambda sku: sku.price_rub)
    for key, value in (default_sku.params or {}).items():
        if key not in normalized or normalized.get(key) in (None, ""):
            normalized[key] = value


def _apply_pricing_defaults(model_id: str, selected_params: Dict[str, Any], mode_index: Optional[int]) -> Dict[str, Any]:
    normalized = dict(selected_params or {})
    _apply_mode_defaults(model_id, mode_index, normalized)
    default_params = PRICING_DEFAULT_PARAMS.get(model_id, {})
    for key, value in default_params.items():
        if key not in normalized or normalized.get(key) in (None, ""):
            normalized[key] = value

    skus = list_model_skus(model_id)
    if skus:
        param_values: Dict[str, Dict[str, Any]] = {}
        for sku in skus:
            for param_key, param_value in (sku.params or {}).items():
                norm_value = _normalize_param_value(param_value)
                param_values.setdefault(param_key, {})[norm_value] = param_value
        for param_key, values_map in param_values.items():
            if param_key in normalized:
                current_norm = _normalize_param_value(normalized.get(param_key))
                if current_norm in values_map:
                    normalized[param_key] = values_map[current_norm]
                    continue
                current_lower = current_norm.lower()
                for norm_value, raw_value in values_map.items():
                    if current_lower == norm_value.lower():
                        normalized[param_key] = raw_value
                        break
                continue
            if len(values_map) == 1:
                normalized[param_key] = next(iter(values_map.values()))
    _backfill_from_cheapest_sku(model_id, normalized)
    return normalized


def resolve_price_quote(
    model_id: str,
    mode_index: int,
    gen_type: Optional[str],
    selected_params: Dict[str, Any],
    *,
    settings: Optional[Settings] = None,
    is_admin: bool = False,
) -> Optional[PriceQuote]:
    """
    Resolve a price quote for a model/mode using SSOT catalog.

    Returns None when price rules are missing.
    """
    settings = settings or get_settings()
    canonical_model_id = canonicalize_model_id(model_id)
    effective_params = _apply_pricing_defaults(canonical_model_id, selected_params or {}, mode_index)
    sku = resolve_sku_for_params(canonical_model_id, effective_params)
    if not sku:
        return None

    if is_admin or sku.is_free_sku:
        price_rub = Decimal("0")
    else:
        price_rub = _quantize_price(_to_decimal(sku.price_rub))
    if sku.sku_key not in _pricing_ok_logged:
        _pricing_ok_logged.add(sku.sku_key)
        logger.info(
            "PRICING_COVERAGE_OK model_id=%s sku_id=%s price_rub=%s",
            canonical_model_id,
            sku.sku_key,
            price_rub,
        )
    breakdown = {
        "model_id": canonical_model_id,
        "mode_index": mode_index,
        "gen_type": gen_type,
        "params": dict(effective_params or {}),
        "sku_id": sku.sku_key,
        "unit": sku.unit,
        "free_sku": sku.is_free_sku,
        "admin_free": is_admin,
    }
    return PriceQuote(price_rub=price_rub, currency="RUB", breakdown=breakdown, sku_id=sku.sku_key)
