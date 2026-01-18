#!/usr/bin/env python3
"""Verify the presence of the canonical model registry."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
