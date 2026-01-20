from app.kie_catalog import get_free_tools_model_ids
from app.pricing.price_ssot import list_free_sku_keys


def test_free_menu_uses_only_free_skus_from_ssot():
    sku_ids = get_free_tools_model_ids()
    assert sku_ids == list_free_sku_keys()
    assert all("::" in sku_id for sku_id in sku_ids)
