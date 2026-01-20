#!/usr/bin/env python3
"""Generate readiness, mismatch, and price snapshot reports for SSOT."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pricing.price_ssot import (
    get_min_price,
    list_all_models,
    list_free_sku_keys,
    list_model_skus,
)
from app.ux.model_visibility import (
    STATUS_BLOCKED_NO_PRICE,
    STATUS_BLOCKED_REQUIRED_MISSING,
    STATUS_HIDDEN_NO_INSTRUCTIONS,
    STATUS_READY_VISIBLE,
)


READINESS_MD = ROOT / "TRT_MODEL_READINESS.md"
MISMATCH_MD = ROOT / "TRT_MODEL_MISMATCHES.md"
SNAPSHOT_MD = ROOT / "TRT_PRICE_SNAPSHOT.md"
READINESS_JSON = ROOT / "artifacts" / "model_readiness.json"
MISMATCH_JSON = ROOT / "artifacts" / "model_mismatches.json"
SNAPSHOT_JSON = ROOT / "artifacts" / "price_snapshot.json"


@dataclass(frozen=True)
class ModelReadiness:
    model_id: str
    status: str
    issues: List[str]
    api_required_fields: List[str]
    api_optional_fields: List[str]
    defaults: Dict[str, Any]


def _load_registry_models() -> Dict[str, Any]:
    registry_path = ROOT / "models" / "kie_models.yaml"
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return payload.get("models", {}) if isinstance(payload, dict) else {}


def _enum_values(spec: Dict[str, Any]) -> List[str]:
    values = spec.get("values")
    if values is None:
        values = spec.get("enum")
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values]


def _extract_schema_fields(schema: Dict[str, Any]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    required: List[str] = []
    optional: List[str] = []
    defaults: Dict[str, Any] = {}
    for name, spec in (schema or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("required"):
            required.append(name)
        else:
            optional.append(name)
        if "default" in spec:
            defaults[name] = spec.get("default")
    return sorted(required), sorted(optional), defaults


def _find_missing_price_variants(schema: Dict[str, Any], skus: List[Any]) -> Dict[str, List[str]]:
    sku_values_by_param: Dict[str, set[str]] = {}
    for sku in skus:
        for param_name, param_value in sku.params.items():
            sku_values_by_param.setdefault(param_name, set()).add(str(param_value))
    missing: Dict[str, List[str]] = {}
    for param_name, spec in schema.items():
        if not isinstance(spec, dict):
            continue
        enum_vals = _enum_values(spec)
        if not enum_vals:
            continue
        sku_vals = sku_values_by_param.get(param_name)
        if not sku_vals:
            continue
        missing_values = [value for value in enum_vals if str(value) not in sku_vals]
        if missing_values:
            missing[param_name] = missing_values
    return missing


def _find_required_mismatches(schema: Dict[str, Any]) -> List[str]:
    required, _, _ = _extract_schema_fields(schema)
    missing = [
        name
        for name in required
        if schema.get(name, {}).get("type") == "enum" and not _enum_values(schema.get(name, {}))
    ]
    return missing


def _evaluate_visibility(schema: Dict[str, Any], skus: List[Any]) -> Tuple[str, List[str], List[str], List[str], Dict[str, Any]]:
    issues: List[str] = []
    required, optional, defaults = _extract_schema_fields(schema or {})

    if not schema:
        return STATUS_HIDDEN_NO_INSTRUCTIONS, ["Нет инструкций модели в registry."], required, optional, defaults

    missing_required_fields = [
        name
        for name in required
        if schema.get(name, {}).get("type") == "enum" and not _enum_values(schema.get(name, {}))
    ]
    if missing_required_fields:
        issues.append(f"Нет вариантов для обязательных полей: {', '.join(sorted(missing_required_fields))}")
        return STATUS_BLOCKED_REQUIRED_MISSING, issues, required, optional, defaults

    if not skus:
        return STATUS_BLOCKED_NO_PRICE, ["Нет ценовых SKU в прайс-SSOT."], required, optional, defaults

    missing_variants = _find_missing_price_variants(schema, skus)
    if missing_variants:
        issues.append(
            "Нет цены для вариантов: "
            + "; ".join(f"{param}: {', '.join(values)}" for param, values in sorted(missing_variants.items()))
        )
        return STATUS_BLOCKED_NO_PRICE, issues, required, optional, defaults

    return STATUS_READY_VISIBLE, [], required, optional, defaults


def _build_readiness_models(registry_ids: List[str], price_ids: List[str]) -> List[ModelReadiness]:
    entries: List[ModelReadiness] = []
    registry_models = _load_registry_models()
    for model_id in sorted(set(registry_ids).union(price_ids)):
        model_data = registry_models.get(model_id, {}) if isinstance(registry_models, dict) else {}
        schema = model_data.get("input") if isinstance(model_data, dict) else {}
        skus = list_model_skus(model_id)
        status, issues, required, optional, defaults = _evaluate_visibility(schema or {}, skus)
        entries.append(
            ModelReadiness(
                model_id=model_id,
                status=status,
                issues=issues,
                api_required_fields=required,
                api_optional_fields=optional,
                defaults=defaults,
            )
        )
    return entries


def _write_readiness_report(models: List[ModelReadiness]) -> None:
    counts: Dict[str, int] = {}
    for entry in models:
        counts[entry.status] = counts.get(entry.status, 0) + 1

    lines: List[str] = []
    lines.append("# TRT Model Readiness")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("| --- | ---: |")
    for status, count in sorted(counts.items()):
        lines.append(f"| {status} | {count} |")
    lines.append("")

    for entry in models:
        lines.append(f"## {entry.model_id}")
        lines.append(f"**{entry.status}**")
        if entry.issues:
            lines.append("")
            lines.append("Issues:")
            for issue in entry.issues:
                lines.append(f"- {issue}")
        lines.append("")
        lines.append("### API fields")
        lines.append("")
        lines.append("| Parameter | Required |")
        lines.append("| --- | --- |")
        for name in entry.api_required_fields:
            lines.append(f"| {name} | Yes |")
        for name in entry.api_optional_fields:
            lines.append(f"| {name} | No |")
        lines.append("")
        for name in entry.api_required_fields:
            lines.append(f"#### {name} + Required: Yes")
        for name in entry.api_optional_fields:
            lines.append(f"#### {name} + Required: No")
        if entry.defaults:
            lines.append("")
            lines.append("Defaults:")
            for name, value in sorted(entry.defaults.items()):
                lines.append(f"- {name}: {value}")
        lines.append("")

    READINESS_MD.write_text("\n".join(lines), encoding="utf-8")
    READINESS_JSON.write_text(
        json.dumps([asdict(entry) for entry in models], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_mismatch_report(
    price_only: List[str],
    missing_price_variants: Dict[str, Dict[str, List[str]]],
    required_mismatches: Dict[str, List[str]],
) -> None:
    lines: List[str] = []
    lines.append("# TRT Model Mismatches")
    lines.append("")
    lines.append("## Models present in price but absent in instructions")
    lines.append("")
    if price_only:
        for model_id in price_only:
            lines.append(f"- {model_id}")
    else:
        lines.append("- ✅ None")
    lines.append("")

    lines.append("## Missing price variants (price vs model SSOT)")
    lines.append("")
    if missing_price_variants:
        for model_id, params in sorted(missing_price_variants.items()):
            lines.append(f"- {model_id}")
            for param_name, values in sorted(params.items()):
                values_text = ", ".join(values)
                lines.append(f"  - {param_name}: {values_text}")
    else:
        lines.append("- ✅ None")
    lines.append("")

    lines.append("## Required fields mismatch")
    lines.append("")
    if required_mismatches:
        for model_id, fields in sorted(required_mismatches.items()):
            fields_text = ", ".join(fields)
            lines.append(f"- {model_id}: {fields_text}")
    else:
        lines.append("- ✅ None")
    lines.append("")

    payload = {
        "price_only_models": price_only,
        "missing_price_variants": missing_price_variants,
        "required_field_mismatches": required_mismatches,
    }
    MISMATCH_MD.write_text("\n".join(lines), encoding="utf-8")
    MISMATCH_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_snapshot_report(registry_ids: List[str], price_ids: List[str]) -> None:
    lines: List[str] = []
    snapshot: Dict[str, Any] = {"models": [], "free_skus": []}

    lines.append("# TRT Price Snapshot")
    lines.append("")
    lines.append("| Model | Min price (RUB) | Priced SKUs | Missing variants |")
    lines.append("| --- | ---: | ---: | ---: |")

    registry_models = _load_registry_models()
    for model_id in sorted(set(registry_ids).union(price_ids)):
        skus = list_model_skus(model_id)
        min_price = get_min_price(model_id)
        model_data = registry_models.get(model_id, {}) if isinstance(registry_models, dict) else {}
        schema = model_data.get("input") if isinstance(model_data, dict) else {}
        missing_variants = _find_missing_price_variants(schema or {}, skus)
        missing_count = sum(len(values) for values in missing_variants.values())
        lines.append(
            f"| {model_id} | {min_price if min_price is not None else '—'} | {len(skus)} | {missing_count} |"
        )
        snapshot["models"].append(
            {
                "model_id": model_id,
                "min_price_rub": float(min_price) if min_price is not None else None,
                "count_variants_priced": len(skus),
                "count_variants_missing": missing_count,
            }
        )

    lines.append("")
    lines.append("## Free SKUs")
    lines.append("")
    free_skus = list_free_sku_keys()
    if free_skus:
        for sku_id in free_skus:
            lines.append(f"- {sku_id}")
    else:
        lines.append("- ✅ None")

    snapshot["free_skus"] = free_skus

    SNAPSHOT_MD.write_text("\n".join(lines), encoding="utf-8")
    SNAPSHOT_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    registry_models = _load_registry_models()
    registry_ids = sorted(registry_models.keys())
    price_ids = sorted(list_all_models())

    readiness_entries = _build_readiness_models(registry_ids, price_ids)
    _write_readiness_report(readiness_entries)

    price_only = sorted(set(price_ids) - set(registry_ids))
    missing_price_variants: Dict[str, Dict[str, List[str]]] = {}
    required_mismatches: Dict[str, List[str]] = {}
    for model_id in registry_ids:
        model_data = registry_models.get(model_id, {}) if isinstance(registry_models, dict) else {}
        schema = model_data.get("input") if isinstance(model_data, dict) else {}
        skus = list_model_skus(model_id)
        missing_variants = _find_missing_price_variants(schema or {}, skus)
        if missing_variants:
            missing_price_variants[model_id] = missing_variants
        required_missing = _find_required_mismatches(schema or {})
        if required_missing:
            required_mismatches[model_id] = required_missing

    _write_mismatch_report(price_only, missing_price_variants, required_mismatches)
    _write_snapshot_report(registry_ids, price_ids)


if __name__ == "__main__":
    main()
