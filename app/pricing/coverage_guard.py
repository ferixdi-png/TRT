"""Pricing coverage guard for disabling models without resolvable SKU mappings."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from app.kie_contract.schema_loader import get_model_schema, list_model_ids
from app.kie_catalog import get_model_map
from app.models.canonical import canonicalize_model_id
from app.pricing.price_resolver import resolve_price_quote
from app.pricing.price_ssot import list_model_skus

logger = logging.getLogger(__name__)

DISABLED_REASON_NO_PRICE = "NO_PRICE_FOR_PARAMS"


@dataclass(frozen=True)
class DisabledModelInfo:
    model_id: str
    reason: str
    issues: List[str]


_disabled_models: Dict[str, DisabledModelInfo] = {}


def _required_enum_params(schema: dict) -> List[str]:
    required = []
    for name, spec in (schema or {}).items():
        if not isinstance(spec, dict):
            continue
        if not spec.get("required"):
            continue
        enum_values = spec.get("values") or spec.get("enum")
        if spec.get("type") == "enum" and enum_values:
            required.append(name)
    return required


def _resolve_mode_price(model_id: str, mode_index: int) -> bool:
    try:
        quote = resolve_price_quote(
            model_id=model_id,
            mode_index=mode_index,
            gen_type=None,
            selected_params={},
        )
        return quote is not None
    except Exception as exc:
        logger.warning(
            "PRICING_PREFLIGHT_RESOLVE_FAILED model_id=%s mode_index=%s error=%s",
            model_id,
            mode_index,
            exc,
            exc_info=True,
        )
        return False


def _evaluate_model_pricing(model_id: str) -> Optional[DisabledModelInfo]:
    canonical_id = canonicalize_model_id(model_id)
    catalog_map = get_model_map()
    catalog_model = catalog_map.get(canonical_id)
    if not catalog_model:
        return DisabledModelInfo(
            model_id=canonical_id,
            reason=DISABLED_REASON_NO_PRICE,
            issues=["Модель отсутствует в pricing каталоге."],
        )

    skus = list_model_skus(canonical_id)
    if not skus:
        return DisabledModelInfo(
            model_id=canonical_id,
            reason=DISABLED_REASON_NO_PRICE,
            issues=["Нет SKU в pricing SSOT."],
        )

    schema = get_model_schema(canonical_id) or {}
    required_params = _required_enum_params(schema)
    sku_param_keys = set()
    for sku in skus:
        sku_param_keys.update(sku.params.keys())
    missing_required = [name for name in required_params if name not in sku_param_keys]
    if missing_required:
        return DisabledModelInfo(
            model_id=canonical_id,
            reason=DISABLED_REASON_NO_PRICE,
            issues=[
                "Нет SKU маппинга для обязательных параметров: "
                + ", ".join(sorted(missing_required))
            ],
        )

    modes = catalog_model.modes or []
    if not modes:
        return DisabledModelInfo(
            model_id=canonical_id,
            reason=DISABLED_REASON_NO_PRICE,
            issues=["В каталоге нет режимов для модели."],
        )

    for index in range(len(modes)):
        if not _resolve_mode_price(canonical_id, index):
            return DisabledModelInfo(
                model_id=canonical_id,
                reason=DISABLED_REASON_NO_PRICE,
                issues=[f"Не найден SKU для режима {index}."],
            )

    return None


def run_pricing_coverage_preflight() -> Dict[str, DisabledModelInfo]:
    disabled: Dict[str, DisabledModelInfo] = {}
    try:
        registry_ids = list_model_ids()
        for model_id in registry_ids:
            info = _evaluate_model_pricing(model_id)
            if info:
                disabled[info.model_id] = info
    except Exception as exc:
        logger.error("PRICING_PREFLIGHT_FAILED error=%s", exc, exc_info=True)
        return {}

    if disabled:
        logger.warning(
            "PRICING_PREFLIGHT_DISABLED models=%s",
            {key: value.reason for key, value in disabled.items()},
        )
    return disabled


def refresh_pricing_coverage_guard() -> Dict[str, DisabledModelInfo]:
    disabled = run_pricing_coverage_preflight()
    _disabled_models.clear()
    _disabled_models.update(disabled)
    get_pricing_coverage_guard_snapshot.cache_clear()
    return disabled


def get_disabled_model_info(model_id: str) -> Optional[DisabledModelInfo]:
    canonical_id = canonicalize_model_id(model_id)
    if not _disabled_models:
        refresh_pricing_coverage_guard()
    return _disabled_models.get(canonical_id)


def is_model_disabled(model_id: str) -> bool:
    return get_disabled_model_info(model_id) is not None


def reset_pricing_coverage_guard() -> None:
    _disabled_models.clear()
    get_pricing_coverage_guard_snapshot.cache_clear()


@lru_cache(maxsize=1)
def get_pricing_coverage_guard_snapshot() -> Tuple[DisabledModelInfo, ...]:
    if not _disabled_models:
        refresh_pricing_coverage_guard()
    return tuple(_disabled_models.values())
