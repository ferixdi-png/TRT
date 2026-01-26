"""Balance formatting helpers."""

from __future__ import annotations

from app.pricing.price_resolver import format_price_rub


def format_rub_amount(value: float) -> str:
    """Format RUB amount with 2 decimals (ROUND_HALF_UP)."""
    formatted = format_price_rub(value)
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{formatted} ₽"
