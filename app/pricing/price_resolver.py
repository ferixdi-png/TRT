"""
Single price resolver for KIE models.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from app.config import Settings, get_settings
from app.kie_catalog import get_model


PRICE_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class PriceQuote:
    price_rub: Decimal
    currency: str
    breakdown: Dict[str, Any]


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
    model_spec = get_model(model_id)
    if not model_spec or not model_spec.modes:
        return None

    if mode_index < 0 or mode_index >= len(model_spec.modes):
        return None

    mode = model_spec.modes[mode_index]
    base_usd = _to_decimal(mode.official_usd)
    usd_to_rub = _to_decimal(getattr(settings, "usd_to_rub", 77.83))
    multiplier = _to_decimal(1.0 if is_admin else getattr(settings, "price_multiplier", 2.0))

    price_rub = _quantize_price(base_usd * usd_to_rub * multiplier)

    breakdown = {
        "model_id": model_id,
        "mode_index": mode_index,
        "gen_type": gen_type,
        "params": dict(selected_params or {}),
        "base_usd": str(base_usd),
        "usd_to_rub": str(usd_to_rub),
        "multiplier": str(multiplier),
    }
    return PriceQuote(price_rub=price_rub, currency="RUB", breakdown=breakdown)
