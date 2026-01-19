#!/usr/bin/env python3
"""Verify the presence of the canonical model registry."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"
LEGACY_ROOT = ROOT / "5656-main"
LEGACY_REGISTRY_PATH = LEGACY_ROOT / "models" / "kie_models.yaml"
LEGACY_PRICING_PATH = LEGACY_ROOT / "app" / "kie_catalog" / "models_pricing.yaml"


def main() -> int:
    if not REGISTRY_PATH.exists():
        print(f"❌ Missing registry: {REGISTRY_PATH}")
        return 1
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict) or not models:
        print("❌ Registry is empty or invalid")
        return 1
    print(f"✅ Registry present: {len(models)} models")
    if LEGACY_ROOT.exists():
        warnings = []
        if LEGACY_REGISTRY_PATH.exists():
            legacy_data = yaml.safe_load(LEGACY_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
            if legacy_data != data:
                warnings.append("⚠️ Legacy 5656-main registry differs from root /models (SSOT)")
        if LEGACY_PRICING_PATH.exists():
            legacy_pricing = yaml.safe_load(LEGACY_PRICING_PATH.read_text(encoding="utf-8")) or {}
            current_pricing_path = ROOT / "app" / "kie_catalog" / "models_pricing.yaml"
            current_pricing = yaml.safe_load(current_pricing_path.read_text(encoding="utf-8")) or {}
            if legacy_pricing != current_pricing:
                warnings.append("⚠️ Legacy 5656-main pricing differs from root /app (SSOT)")
        if warnings:
            print("ℹ️ Runtime SSOT is root /models + /app. 5656-main is deprecated/ignored.")
            for warning in warnings:
                print(warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
