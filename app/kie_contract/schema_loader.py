"""KIE contract schema loader for model specs."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"


def _load_registry() -> Dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {}
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def list_model_ids() -> List[str]:
    registry = _load_registry()
    models = registry.get("models", {})
    if not isinstance(models, dict):
        return []
    return list(models.keys())


def get_model_schema(model_id: str) -> Optional[Dict[str, Any]]:
    registry = _load_registry()
    models = registry.get("models", {})
    if not isinstance(models, dict):
        return None
    model_data = models.get(model_id)
    if not isinstance(model_data, dict):
        return None
    schema = model_data.get("input")
    return schema if isinstance(schema, dict) else None


def get_model_meta(model_id: str) -> Optional[Dict[str, Any]]:
    registry = _load_registry()
    models = registry.get("models", {})
    if not isinstance(models, dict):
        return None
    model_data = models.get(model_id)
    return model_data if isinstance(model_data, dict) else None
