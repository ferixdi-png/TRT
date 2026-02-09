"""
Model UX Descriptions - Single Source of Truth
Used by Bot and Mini App for Model Intro Cards
"""

import os
from typing import Any, Dict, Optional
from functools import lru_cache

import yaml


_DESCRIPTIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "model_descriptions.yaml"
)


@lru_cache(maxsize=1)
def _load_descriptions() -> Dict[str, Any]:
    """Load model descriptions from YAML file."""
    try:
        with open(_DESCRIPTIONS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception:
        return {"models": {}, "default": {}}


def get_model_description(model_id: str, lang: str = "ru") -> Dict[str, Any]:
    """
    Get UX description for a model.
    
    Args:
        model_id: Model identifier (e.g., 'sora-2-text-to-video')
        lang: Language code ('ru' or 'en')
    
    Returns:
        Dictionary with localized description fields
    """
    data = _load_descriptions()
    models = data.get("models", {})
    default = data.get("default", {})
    
    # Try exact match first
    desc = models.get(model_id, {})
    
    # Fallback to default if not found
    if not desc:
        desc = default
    
    # Build localized response
    suffix = f"_{lang}" if lang in ("ru", "en") else "_ru"
    fallback_suffix = "_en" if suffix == "_ru" else "_ru"
    
    def get_field(field_name: str) -> Any:
        """Get field with language fallback."""
        value = desc.get(f"{field_name}{suffix}")
        if value is None:
            value = desc.get(f"{field_name}{fallback_suffix}")
        if value is None:
            value = default.get(f"{field_name}{suffix}")
        if value is None:
            value = default.get(f"{field_name}{fallback_suffix}")
        return value
    
    return {
        "title": get_field("title"),
        "one_liner": get_field("one_liner"),
        "best_for": get_field("best_for") or [],
        "you_need": get_field("you_need"),
        "you_get": get_field("you_get"),
        "price_hint": get_field("price_hint"),
    }


def format_intro_card(
    model_id: str,
    lang: str = "ru",
    price_rub: Optional[float] = None,
    unit: Optional[str] = None,
) -> str:
    """
    Format Model Intro Card as HTML text for Telegram.
    
    Args:
        model_id: Model identifier
        lang: Language code
        price_rub: Price in RUB (optional)
        unit: Price unit (optional)
    
    Returns:
        HTML formatted intro card text
    """
    desc = get_model_description(model_id, lang)
    
    title = desc.get("title") or model_id
    one_liner = desc.get("one_liner") or ""
    best_for = desc.get("best_for") or []
    you_need = desc.get("you_need") or ""
    you_get = desc.get("you_get") or ""
    price_hint = desc.get("price_hint") or ""
    
    # Build card
    lines = []
    lines.append(f"<b>{title}</b>")
    
    if one_liner:
        lines.append(f"<i>{one_liner}</i>")
    
    lines.append("")
    
    if best_for:
        if lang == "ru":
            lines.append("📌 <b>Подходит для:</b>")
        else:
            lines.append("📌 <b>Best for:</b>")
        for item in best_for[:3]:
            lines.append(f"  • {item}")
    
    if you_need:
        lines.append("")
        if lang == "ru":
            lines.append(f"📥 <b>Нужно:</b> {you_need}")
        else:
            lines.append(f"📥 <b>You need:</b> {you_need}")
    
    if you_get:
        if lang == "ru":
            lines.append(f"📤 <b>Получите:</b> {you_get}")
        else:
            lines.append(f"📤 <b>You get:</b> {you_get}")
    
    # Price section
    lines.append("")
    if price_rub is not None and price_rub > 0:
        unit_label = unit or ("ед." if lang == "ru" else "unit")
        if lang == "ru":
            lines.append(f"💰 <b>Цена:</b> от {price_rub:.2f} ₽/{unit_label}")
        else:
            lines.append(f"💰 <b>Price:</b> from {price_rub:.2f} ₽/{unit_label}")
    elif price_hint:
        if lang == "ru":
            lines.append(f"💰 {price_hint}")
        else:
            lines.append(f"💰 {price_hint}")
    
    lines.append("")
    lines.append("─" * 20)
    
    return "\n".join(lines)


def get_intro_card_data(
    model_id: str,
    lang: str = "ru",
    price_rub: Optional[float] = None,
    unit: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get Model Intro Card data as dictionary for Mini App.
    
    Args:
        model_id: Model identifier
        lang: Language code
        price_rub: Price in RUB (optional)
        unit: Price unit (optional)
    
    Returns:
        Dictionary with all card fields
    """
    desc = get_model_description(model_id, lang)
    
    result = {
        "model_id": model_id,
        "lang": lang,
        "title": desc.get("title") or model_id,
        "one_liner": desc.get("one_liner") or "",
        "best_for": desc.get("best_for") or [],
        "you_need": desc.get("you_need") or "",
        "you_get": desc.get("you_get") or "",
        "price_hint": desc.get("price_hint") or "",
    }
    
    if price_rub is not None and price_rub > 0:
        result["price_rub"] = price_rub
        result["unit"] = unit or "unit"
    
    return result


def clear_cache() -> None:
    """Clear the description cache (for hot reload)."""
    _load_descriptions.cache_clear()
