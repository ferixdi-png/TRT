from app.models.registry import get_generation_types, get_models_by_generation_type, get_models_sync
from app.pricing.price_resolver import resolve_price_quote
from app.pricing.price_ssot import list_all_models
from app.pricing.ssot_catalog import list_model_skus


def test_registry_menu_pricing_generation_guard():
    models = get_models_sync()
    assert models

    for gen_type in get_generation_types():
        get_models_by_generation_type(gen_type)

    for model_id in list_all_models():
        skus = list_model_skus(model_id)
        if not skus:
            continue
        quote = resolve_price_quote(model_id, 0, None, {})
        assert quote is not None
