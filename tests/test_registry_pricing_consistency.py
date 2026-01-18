from pathlib import Path

import yaml


def test_registry_pricing_ssot_consistency():
    registry_path = Path("models/kie_models.yaml")
    pricing_path = Path("app/kie_catalog/models_pricing.yaml")

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    pricing = yaml.safe_load(pricing_path.read_text(encoding="utf-8"))

    registry_models = registry.get("models", {})
    registry_ids = set(registry_models.keys())
    registry_free = {model_id for model_id, model in registry_models.items() if model.get("free") is True}
    registry_disabled = {model_id for model_id, model in registry_models.items() if model.get("disabled") is True}

    pricing_models = pricing.get("models", [])
    pricing_ids = {model.get("id") for model in pricing_models if model.get("id")}
    pricing_free = set()
    for model in pricing_models:
        model_id = model.get("id")
        if not model_id:
            continue
        if model.get("free") is True:
            pricing_free.add(model_id)
            continue
        for mode in model.get("modes", []):
            if mode.get("free") is True or mode.get("credits") == 0 or mode.get("official_usd") == 0:
                pricing_free.add(model_id)
                break

    assert len(registry_ids) == 72
    assert len(pricing_ids) <= 72
    assert len(pricing_ids) == len(pricing_models)
    assert pricing_ids <= registry_ids
    assert registry_ids - pricing_ids - registry_free - registry_disabled == set()
    assert registry_free == pricing_free
