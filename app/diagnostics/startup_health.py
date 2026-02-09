"""Startup health check - logs system integrity on boot."""
import logging

logger = logging.getLogger(__name__)


def run_startup_health_check() -> dict:
    """Run comprehensive health check and log results.
    
    Returns dict with all metrics for further use.
    """
    results = {
        "catalog_models": 0,
        "catalog_with_title": 0,
        "catalog_with_emoji": 0,
        "catalog_with_price": 0,
        "top_models": 0,
        "top_categories": 0,
        "top_models_with_skus": 0,
        "generation_types": 0,
        "generation_types_models": 0,
        "kie_models": 0,
        "translations_ru": 0,
        "translations_en": 0,
        "issues": [],
    }
    
    # 1. Check catalog
    try:
        from app.kie_catalog import get_model_map
        catalog = get_model_map()
        results["catalog_models"] = len(catalog)
        
        for model_id, spec in catalog.items():
            title = getattr(spec, "title_ru", "") or getattr(spec, "name", "")
            if title:
                results["catalog_with_title"] += 1
                if any(ord(c) > 127 for c in title[:2]):
                    results["catalog_with_emoji"] += 1
    except Exception as e:
        results["issues"].append(f"CATALOG_ERROR: {e}")
    
    # 2. Check top models
    try:
        from app.top_models import get_top_models, get_categories, get_sku_price_rub
        top_models = get_top_models()
        categories = get_categories()
        results["top_models"] = len(top_models)
        results["top_categories"] = len(categories)
        
        for m in top_models:
            skus = m.get("skus", [])
            if skus:
                results["top_models_with_skus"] += 1
                for sku in skus:
                    price_ref = sku.get("price_ref", "")
                    mode_key = sku.get("mode_key", "")
                    if price_ref:
                        price = get_sku_price_rub(price_ref, mode_key)
                        if price and price > 0:
                            results["catalog_with_price"] += 1
                            break
    except Exception as e:
        results["issues"].append(f"TOP_MODELS_ERROR: {e}")
    
    # 3. Check GENERATION_TYPES
    try:
        from kie_models import GENERATION_TYPES
        results["generation_types"] = len(GENERATION_TYPES)
        results["generation_types_models"] = sum(
            len(gt.get("models", [])) for gt in GENERATION_TYPES.values()
        )
    except Exception as e:
        results["issues"].append(f"GENERATION_TYPES_ERROR: {e}")
    
    # 4. Check KIE_MODELS
    try:
        from kie_models import KIE_MODELS
        results["kie_models"] = len(KIE_MODELS)
    except Exception as e:
        results["issues"].append(f"KIE_MODELS_ERROR: {e}")
    
    # 5. Check translations
    try:
        from translations import TRANSLATIONS
        results["translations_ru"] = len(TRANSLATIONS.get("ru", {}))
        results["translations_en"] = len(TRANSLATIONS.get("en", {}))
    except Exception as e:
        results["issues"].append(f"TRANSLATIONS_ERROR: {e}")
    
    # Log summary
    _log_health_summary(results)
    
    return results


def _log_health_summary(results: dict) -> None:
    """Log health check summary in structured format."""
    issues = results.get("issues", [])
    status = "OK" if not issues else "ISSUES"
    
    logger.info(
        "STARTUP_HEALTH_CHECK status=%s "
        "catalog_models=%d catalog_with_title=%d catalog_with_emoji=%d "
        "top_models=%d top_categories=%d top_models_with_skus=%d "
        "generation_types=%d generation_types_models=%d kie_models=%d "
        "translations_ru=%d translations_en=%d issues_count=%d",
        status,
        results["catalog_models"],
        results["catalog_with_title"],
        results["catalog_with_emoji"],
        results["top_models"],
        results["top_categories"],
        results["top_models_with_skus"],
        results["generation_types"],
        results["generation_types_models"],
        results["kie_models"],
        results["translations_ru"],
        results["translations_en"],
        len(issues),
    )
    
    # Log individual issues
    for issue in issues:
        logger.warning("STARTUP_HEALTH_ISSUE %s", issue)
    
    # Log detailed breakdown
    catalog = results["catalog_models"]
    if catalog > 0:
        emoji_pct = (results["catalog_with_emoji"] / catalog) * 100
        title_pct = (results["catalog_with_title"] / catalog) * 100
        logger.info(
            "STARTUP_HEALTH_CATALOG total=%d emoji_pct=%.1f title_pct=%.1f",
            catalog, emoji_pct, title_pct
        )
    
    # Check for mismatches
    gen_models = results["generation_types_models"]
    if catalog > 0 and gen_models < catalog:
        missing = catalog - gen_models
        logger.warning(
            "STARTUP_HEALTH_MISMATCH catalog=%d generation_types=%d missing=%d",
            catalog, gen_models, missing
        )
