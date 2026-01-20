from app.kie_catalog import get_free_tools_model_ids
from app.pricing.ssot_catalog import get_sku_by_id
from app.kie_contract.schema_loader import get_model_meta


def test_free_menu_has_five_skus_with_text_to_video():
    sku_ids = get_free_tools_model_ids()
    assert len(sku_ids) == 5
    assert all("::" in sku_id for sku_id in sku_ids)

    skus = [get_sku_by_id(sku_id) for sku_id in sku_ids]
    assert all(sku is not None for sku in skus)
    assert any((get_model_meta(sku.model_id) or {}).get("model_type") == "text_to_video" for sku in skus)
