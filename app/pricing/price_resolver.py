"""
Single price resolver for KIE models.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, Optional

from app.config import Settings, get_settings
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


def _quantize_price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def format_price_rub(value: Decimal | float | str) -> str:
    """Format a RUB value with 2 decimal places."""
    return f"{_quantize_price(_to_decimal(value)):.2f}"


def _apply_pricing_defaults(model_id: str, selected_params: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(selected_params or {})
    default_params = PRICING_DEFAULT_PARAMS.get(model_id, {})
    for key, value in default_params.items():
        if key not in normalized or normalized.get(key) in (None, ""):
            normalized[key] = value

    skus = list_model_skus(model_id)
    if skus:
        param_values: Dict[str, set[str]] = {}
        for sku in skus:
            for param_key, param_value in (sku.params or {}).items():
                param_values.setdefault(param_key, set()).add(str(param_value))
        for param_key, values in param_values.items():
            if param_key in normalized:
                continue
            if len(values) == 1:
                normalized[param_key] = next(iter(values))
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
    effective_params = _apply_pricing_defaults(canonical_model_id, selected_params or {})
    sku = resolve_sku_for_params(canonical_model_id, effective_params)
    if not sku:
        return None

    if sku.is_free_sku:
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
    }
    return PriceQuote(price_rub=price_rub, currency="RUB", breakdown=breakdown, sku_id=sku.sku_key)
