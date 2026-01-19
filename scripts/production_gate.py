#!/usr/bin/env python3
"""Production Readiness Gate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=ROOT)


def _check_ssot() -> bool:
    registry_path = ROOT / "models" / "kie_models.yaml"
    pricing_path = ROOT / "app" / "kie_catalog" / "models_pricing.yaml"

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    pricing = yaml.safe_load(pricing_path.read_text(encoding="utf-8")) or {}
    models_count = len((registry.get("models") or {}))
    pricing_count = len((pricing.get("models") or []))
    ok = models_count == 72 and pricing_count == 72
    if not ok:
        print(
            f"SSOT validation failed: models={models_count} pricing={pricing_count} (expected 72)"
        )
    return ok


def main() -> int:
    if not _check_ssot():
        return 1

    if _run([sys.executable, "scripts/smoke_all_models_offline.py"]) != 0:
        return 1

    if _run([sys.executable, "-m", "pytest", "-q"]) != 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
