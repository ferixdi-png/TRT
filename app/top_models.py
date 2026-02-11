"""
Top Models - Single Source of Truth for Bot and Mini App
Provides access to curated list of 24 top models with SKU selection
"""

import logging
import os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_TOP_MODELS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "top_models.yaml"
)

_top_models_cache: Optional[Dict[str, Any]] = None


def _load_top_models() -> Dict[str, Any]:
    """Load top models catalog from YAML file. Only caches successful loads."""
    global _top_models_cache
    if _top_models_cache is not None:
        return _top_models_cache
    try:
        with open(_TOP_MODELS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        model_count = len(data.get("models", []))
        logger.info("Top models loaded: %d models from %s", model_count, _TOP_MODELS_PATH)
        if model_count > 0:
            _top_models_cache = data
        return data
    except Exception as e:
        logger.error("Failed to load top_models.yaml: %s (path=%s)", e, _TOP_MODELS_PATH)
        return {"categories": [], "models": []}


def get_categories(lang: str = "ru") -> List[Dict[str, Any]]:
    """Get list of categories for top models."""
    data = _load_top_models()
    categories = data.get("categories", [])
    
    result = []
    for cat in categories:
        label_key = f"label_{lang}" if lang in ("ru", "en") else "label_ru"
        result.append({
            "id": cat.get("id"),
            "label": cat.get(label_key, cat.get("label_ru", cat.get("id"))),
            "order": cat.get("order", 0),
        })
    
    return sorted(result, key=lambda x: x.get("order", 0))


def get_top_models(lang: str = "ru", category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get list of top models with localized data.
    
    Args:
        lang: Language code ('ru' or 'en')
        category: Optional category filter
    
    Returns:
        List of top model cards
    """
    data = _load_top_models()
    models = data.get("models", [])
    
    result = []
    for model in models:
        if category and model.get("category") != category:
            continue
        
        suffix = f"_{lang}" if lang in ("ru", "en") else "_ru"
        fallback = "_en" if suffix == "_ru" else "_ru"
        
        def get_field(name: str) -> Any:
            return model.get(f"{name}{suffix}") or model.get(f"{name}{fallback}")
        
        # Build SKU list with localized labels
        skus = []
        for sku in model.get("skus", []):
            sku_label = sku.get(f"label_{lang}") or sku.get("label_ru") or sku.get("sku_id")
            sku_unit = sku.get(f"unit_{lang}" if lang == "en" else "unit") or sku.get("unit", "")
            
            skus.append({
                "sku_id": sku.get("sku_id"),
                "label": sku_label,
                "mode_key": sku.get("mode_key"),
                "maps_to": sku.get("maps_to", {}),
                "price_ref": sku.get("price_ref"),
                "unit": sku_unit,
            })
        
        result.append({
            "id": model.get("id"),
            "model_id": model.get("model_id"),
            "category": model.get("category"),
            "title": get_field("title"),
            "one_liner": get_field("one_liner"),
            "best_for": get_field("best_for") or [],
            "skus": skus,
        })
    
    return result


def get_top_model_by_id(top_model_id: str, lang: str = "ru") -> Optional[Dict[str, Any]]:
    """Get single top model by its ID."""
    models = get_top_models(lang=lang)
    for model in models:
        if model.get("id") == top_model_id:
            return model
    return None


def get_sku_details(top_model_id: str, sku_id: str, lang: str = "ru") -> Optional[Dict[str, Any]]:
    """
    Get SKU details for routing to parameter screen.
    
    Args:
        top_model_id: Top model ID (e.g., 'top-kling-2-6-motion')
        sku_id: SKU ID (e.g., 'kling-2-6-motion-720p')
        lang: Language code
    
    Returns:
        SKU details with maps_to for routing
    """
    model = get_top_model_by_id(top_model_id, lang)
    if not model:
        return None
    
    for sku in model.get("skus", []):
        if sku.get("sku_id") == sku_id:
            return {
                "top_model_id": top_model_id,
                "top_model_title": model.get("title"),
                "sku_id": sku_id,
                "sku_label": sku.get("label"),
                "model_id": sku.get("maps_to", {}).get("model_id") or model.get("model_id"),
                "params": sku.get("maps_to", {}).get("params", {}),
                "price_ref": sku.get("price_ref"),
                "unit": sku.get("unit"),
            }
    return None


_pricing_cache: Optional[Dict[str, Any]] = None


def _load_pricing() -> Dict[str, Any]:
    """Load pricing catalog, cached after first successful load."""
    global _pricing_cache
    if _pricing_cache is not None:
        return _pricing_cache
    try:
        pricing_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "kie_pricing_rub.yaml"
        )
        with open(pricing_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if data.get("models"):
            _pricing_cache = data
        return data
    except Exception as e:
        logger.error("Failed to load kie_pricing_rub.yaml: %s", e)
        return {"models": []}


def get_sku_price_rub(price_ref: str, mode_key: str) -> Optional[float]:
    """
    Get price in RUB for SKU from pricing catalog.
    
    Args:
        price_ref: Model ID in pricing catalog
        mode_key: Mode/SKU key to match
    
    Returns:
        Price in RUB or None if not found
    """
    try:
        data = _load_pricing()
        
        for model in data.get("models", []):
            if model.get("id") == price_ref:
                for sku in model.get("skus", []):
                    notes = sku.get("notes", "")
                    if notes == mode_key or mode_key in notes:
                        return float(sku.get("price_rub", 0))
                # Return first SKU price as fallback
                skus = model.get("skus", [])
                if skus:
                    return float(skus[0].get("price_rub", 0))
        return None
    except Exception:
        return None


def format_top_model_card(model: Dict[str, Any], lang: str = "ru") -> str:
    """
    Format top model card as HTML text for Telegram.
    
    Args:
        model: Model data from get_top_models
        lang: Language code
    
    Returns:
        HTML formatted card text
    """
    title = model.get("title", model.get("id"))
    one_liner = model.get("one_liner", "")
    best_for = model.get("best_for", [])
    skus = model.get("skus", [])
    
    lines = [f"<b>{title}</b>"]
    
    if one_liner:
        lines.append(f"<i>{one_liner}</i>")
    
    lines.append("")
    
    if best_for:
        header = "📌 <b>Подходит для:</b>" if lang == "ru" else "📌 <b>Best for:</b>"
        lines.append(header)
        for item in best_for[:3]:
            lines.append(f"  • {item}")
    
    lines.append("")
    
    # SKU info
    if skus:
        sku_header = "⚙️ <b>Режимы:</b>" if lang == "ru" else "⚙️ <b>Modes:</b>"
        lines.append(sku_header)
        for sku in skus[:4]:  # Limit to 4 SKUs in preview
            price = get_sku_price_rub(sku.get("price_ref", ""), sku.get("mode_key", ""))
            if price and price > 0:
                price_text = f"{price:.2f} ₽/{sku.get('unit', 'ед.')}"
            else:
                price_text = "TBD" if lang == "en" else "уточняется"
            lines.append(f"  • {sku.get('label')}: {price_text}")
    
    return "\n".join(lines)


def clear_cache() -> None:
    """Clear the top models cache (for hot reload)."""
    _load_top_models.cache_clear()
