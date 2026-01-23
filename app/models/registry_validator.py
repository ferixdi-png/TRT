"""Registry validator for SKU/model consistency."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from app.kie_catalog import get_model_map
from app.models.canonical import (
    canonicalize_kie_model,
    canonicalize_model_id,
    validate_alias_registry,
)
from app.models.yaml_registry import load_yaml_models
from app.pricing.price_ssot import list_all_models

logger = logging.getLogger(__name__)

_INVALID_MODEL_IDS: Set[str] = set()
_MODEL_ISSUES: Dict[str, List[str]] = {}
_VALIDATION_COMPLETE = False


def _record_issue(model_id: str, message: str) -> None:
    _INVALID_MODEL_IDS.add(model_id)
    _MODEL_ISSUES.setdefault(model_id, []).append(message)


def validate_registry_consistency() -> Dict[str, List[str]]:
    """Validate registry vs pricing SSOT and return issues by model_id."""
    global _VALIDATION_COMPLETE
    if _VALIDATION_COMPLETE:
        return _MODEL_ISSUES

    _INVALID_MODEL_IDS.clear()
    _MODEL_ISSUES.clear()

    alias_errors = validate_alias_registry()
    for error in alias_errors:
        logger.error("REGISTRY_ALIAS_CONFLICT error=%s", error)

    registry = load_yaml_models()
    pricing_model_ids = list_all_models()
    catalog = get_model_map()

    for model_id in pricing_model_ids:
        canonical_id = canonicalize_model_id(model_id)
        if canonical_id != model_id:
            _record_issue(model_id, f"model_id alias detected: {model_id} -> {canonical_id}")
            logger.warning(
                "REGISTRY_ALIAS_MODEL model_id=%s canonical=%s stage=registry_validation",
                model_id,
                canonical_id,
            )

        registry_data = registry.get(model_id) or registry.get(canonical_id)
        if not registry_data:
            _record_issue(model_id, "registry entry missing for pricing model")
            logger.warning(
                "REGISTRY_MISSING model_id=%s stage=registry_validation",
                model_id,
            )
            continue

        resolved_kie_model = registry_data.get("kie_model") or canonical_id or model_id
        if not resolved_kie_model:
            _record_issue(model_id, "kie_model missing in registry")
            logger.warning(
                "REGISTRY_KIE_MODEL_MISSING model_id=%s stage=registry_validation",
                model_id,
            )
            continue

        canonical_kie_model = canonicalize_kie_model(resolved_kie_model)
        if canonical_kie_model != resolved_kie_model:
            _record_issue(model_id, f"kie_model alias detected: {resolved_kie_model} -> {canonical_kie_model}")
            logger.warning(
                "REGISTRY_KIE_MODEL_ALIAS model_id=%s kie_model=%s canonical=%s stage=registry_validation",
                model_id,
                resolved_kie_model,
                canonical_kie_model,
            )

        spec = catalog.get(canonical_id) or catalog.get(model_id)
        if not spec:
            _record_issue(model_id, "catalog spec missing")
            logger.warning(
                "REGISTRY_CATALOG_MISSING model_id=%s stage=registry_validation",
                model_id,
            )
            continue

        if spec.kie_model != resolved_kie_model:
            _record_issue(model_id, f"catalog kie_model mismatch (catalog={spec.kie_model}, registry={resolved_kie_model})")
            logger.warning(
                "REGISTRY_KIE_MODEL_MISMATCH model_id=%s catalog=%s registry=%s stage=registry_validation",
                model_id,
                spec.kie_model,
                resolved_kie_model,
            )

    if _INVALID_MODEL_IDS:
        logger.warning(
            "REGISTRY_VALIDATION_COMPLETE status=issues model_count=%s invalid=%s",
            len(pricing_model_ids),
            len(_INVALID_MODEL_IDS),
        )
    else:
        logger.info("REGISTRY_VALIDATION_COMPLETE status=ok model_count=%s", len(pricing_model_ids))

    _VALIDATION_COMPLETE = True
    return _MODEL_ISSUES


def get_invalid_model_ids() -> Set[str]:
    if not _VALIDATION_COMPLETE:
        validate_registry_consistency()
    return set(_INVALID_MODEL_IDS)


def get_model_issues(model_id: str) -> List[str]:
    if not _VALIDATION_COMPLETE:
        validate_registry_consistency()
    return _MODEL_ISSUES.get(model_id, [])


def is_model_valid(model_id: str) -> bool:
    if not _VALIDATION_COMPLETE:
        validate_registry_consistency()
    return model_id not in _INVALID_MODEL_IDS
