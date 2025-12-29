"""KIE overlay loader.

We support multiple historical overlay formats:
1) {"overrides": {"model_id": {...}}}
2) {"models": {"model_id": {...}}}
3) {"model_id": {...}} (raw dict)

Goal: one consistent source of truth for UI + payload builder.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict


logger = logging.getLogger(__name__)


def _extract_overrides(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}

    # Preferred: {overrides: {...}}
    if isinstance(raw.get("overrides"), dict):
        return {k: v for k, v in raw["overrides"].items() if isinstance(k, str) and isinstance(v, dict)}

    # Legacy: {models: {...}}
    if isinstance(raw.get("models"), dict):
        return {k: v for k, v in raw["models"].items() if isinstance(k, str) and isinstance(v, dict)}

    # Raw dict keyed by model_id (heuristic: must contain at least one known override key)
    known_keys = {"category", "output_type", "input_schema", "ui", "spec", "pricing", "display_name", "description"}
    overrides: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if not (isinstance(k, str) and isinstance(v, dict)):
            continue
        if known_keys.intersection(v.keys()):
            overrides[k] = v
    return overrides


def load_kie_overlay(path: str | Path = "models/KIE_OVERLAY.json") -> Dict[str, Dict[str, Any]]:
    """Load per-model overlay overrides.

    Returns:
        Dict[model_id, override_dict]
    """
    p = Path(path)
    if not p.exists():
        return {}

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("⚠️ Failed to read KIE overlay %s: %s", str(p), e)
        return {}

    overrides = _extract_overrides(raw)
    if overrides:
        logger.info("✅ Loaded KIE overlay overrides: %d", len(overrides))
    else:
        logger.debug("KIE overlay exists but no overrides found (format mismatch)")
    return overrides
