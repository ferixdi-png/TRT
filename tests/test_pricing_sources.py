from app.kie_catalog.catalog import get_catalog_source_info
from pricing.engine import get_settings_source_info


def test_pricing_source_is_explicit_not_unknown():
    catalog_info = get_catalog_source_info()
    settings_info = get_settings_source_info()

    assert catalog_info["path"] != "unknown"
    assert catalog_info["count"] > 0
    assert settings_info["path"] != "unknown"
    assert "usd_to_rub" in settings_info["settings"]
    assert "markup_multiplier" in settings_info["settings"]
