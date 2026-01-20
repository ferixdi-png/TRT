"""
Single price resolver for KIE models.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from app.config import Settings, get_settings
from app.pricing.price_ssot import resolve_sku_for_params


PRICE_QUANT = Decimal("0.01")


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
    sku = resolve_sku_for_params(model_id, selected_params or {})
    if not sku:
        return None

    if sku.is_free_sku:
        price_rub = Decimal("0")
    else:
        price_rub = _quantize_price(_to_decimal(sku.price_rub))
    breakdown = {
        "model_id": model_id,
        "mode_index": mode_index,
        "gen_type": gen_type,
        "params": dict(selected_params or {}),
        "sku_id": sku.sku_key,
        "unit": sku.unit,
        "free_sku": sku.is_free_sku,
    }
    return PriceQuote(price_rub=price_rub, currency="RUB", breakdown=breakdown, sku_id=sku.sku_key)
