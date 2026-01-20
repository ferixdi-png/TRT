from pathlib import Path

import yaml


def test_registry_pricing_ssot_consistency():
    registry_path = Path("models/kie_models.yaml")
    pricing_path = Path("data/kie_pricing_rub.yaml")

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    pricing = yaml.safe_load(pricing_path.read_text(encoding="utf-8"))

    registry_models = registry.get("models", {})
    registry_ids = set(registry_models.keys())
    registry_disabled = {model_id for model_id, model in registry_models.items() if model.get("disabled") is True}

    pricing_models = pricing.get("models", [])
    pricing_ids = {model.get("id") for model in pricing_models if model.get("id")}

    assert len(registry_ids) == 72
    assert len(pricing_ids) <= 72
    assert len(pricing_ids) == len(pricing_models)
    assert pricing_ids <= registry_ids
