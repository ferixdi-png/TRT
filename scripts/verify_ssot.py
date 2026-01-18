#!/usr/bin/env python3
"""
Verify SSOT consistency between model registry and pricing catalog.

Fails if:
- pricing references a model not in registry
- registry has a paid model missing pricing
- free model flags are inconsistent between registry and pricing
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Any, Set

import yaml


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"
PRICING_PATH = ROOT / "app" / "kie_catalog" / "models_pricing.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML structure in {path}")
    return data


def _registry_models(data: Dict[str, Any]) -> Dict[str, Any]:
    models = data.get("models", {})
    if not isinstance(models, dict):
        return {}
    return models


def _registry_ids(data: Dict[str, Any]) -> Set[str]:
    return set(_registry_models(data).keys())


def _registry_free_ids(data: Dict[str, Any]) -> Set[str]:
    models = _registry_models(data)
    return {model_id for model_id, model_data in models.items() if model_data.get("free") is True}


def _registry_disabled_ids(data: Dict[str, Any]) -> Set[str]:
    models = _registry_models(data)
    return {model_id for model_id, model_data in models.items() if model_data.get("disabled") is True}


def _pricing_ids(data: Dict[str, Any]) -> Set[str]:
    models = data.get("models", [])
    if not isinstance(models, list):
        return set()
    return {model.get("id") for model in models if model.get("id")}


def _pricing_free_ids(data: Dict[str, Any]) -> Set[str]:
    free_ids: Set[str] = set()
    models = data.get("models", [])
    if not isinstance(models, list):
        return free_ids
    for model in models:
        model_id = model.get("id")
        if not model_id:
            continue
        if model.get("free") is True:
            free_ids.add(model_id)
            continue
        for mode in model.get("modes", []):
            if mode.get("free") is True:
                free_ids.add(model_id)
                break
            if mode.get("credits") == 0 or mode.get("price_rub") == 0 or mode.get("official_usd") == 0:
                free_ids.add(model_id)
                break
    return free_ids


def main() -> int:
    registry_data = _load_yaml(REGISTRY_PATH)
    pricing_data = _load_yaml(PRICING_PATH)

    registry_models = _registry_models(registry_data)
    registry_ids = set(registry_models.keys())
    meta_total = registry_data.get("meta", {}).get("total_models")
    if isinstance(meta_total, bool):
        meta_total = None
    expected_total = meta_total if isinstance(meta_total, int) else None
    pricing_ids = _pricing_ids(pricing_data)
    registry_free = _registry_free_ids(registry_data)
    registry_disabled = _registry_disabled_ids(registry_data)
    pricing_free = _pricing_free_ids(pricing_data)

    errors = []
    if expected_total is None:
        errors.append("Registry meta.total_models is missing or invalid")
    elif len(registry_ids) != expected_total:
        errors.append(
            "Registry meta.total_models mismatch: "
            f"meta={expected_total} actual={len(registry_ids)}"
        )
    if expected_total is not None and len(pricing_ids) > expected_total:
        errors.append(
            f"Pricing model count must be <= {expected_total}, got {len(pricing_ids)}"
        )

    if len(pricing_ids) != len(set(pricing_ids)):
        errors.append("Pricing contains duplicate model_id entries")

    pricing_only = pricing_ids - registry_ids
    if pricing_only:
        errors.append(
            f"Pricing has models missing in registry ({len(pricing_only)}): {sorted(pricing_only)}"
        )

    registry_missing_pricing = registry_ids - pricing_ids - registry_free - registry_disabled
    if registry_missing_pricing:
        errors.append(
            "Registry has paid models missing pricing "
            f"({len(registry_missing_pricing)}): {sorted(registry_missing_pricing)}"
        )

    free_diff = registry_free.symmetric_difference(pricing_free)
    if free_diff:
        errors.append(
            "Free model list mismatch between registry and pricing "
            f"({len(free_diff)}): {sorted(free_diff)}"
        )

    if errors:
        print("❌ SSOT verification failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(
        "✅ SSOT verification passed:",
        f"registry={len(registry_ids)} pricing={len(pricing_ids)} free={len(pricing_free)}",
        f"meta_total={expected_total}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
