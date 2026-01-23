"""Generate pricing coverage reports for KIE models."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kie_contract.schema_loader import list_model_ids, get_model_schema
from app.pricing.ssot_catalog import build_param_combinations, get_price_dimensions, list_model_skus, load_pricing_ssot
from app.pricing.price_resolver import resolve_price_quote
REPORT_MD = ROOT / "PRICING_COVERAGE.md"
REPORT_JSON = ROOT / "PRICING_COVERAGE.json"


STATUS_READY = "READY"
STATUS_MISSING_PRICE = "MISSING_PRICE"
STATUS_MISSING_PARAM_SCHEMA = "MISSING_PARAM_SCHEMA"
STATUS_AMBIGUOUS = "AMBIGUOUS_SKU"


def _slugify(model_id: str) -> str:
    return model_id.lower().replace("/", "-").replace("_", "-")


def _normalize_param_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _build_sku_key(model_id: str, params: Dict[str, object]) -> str:
    if not params:
        return f"{model_id}::default"
    parts = [f"{key}={_normalize_param_value(params[key])}" for key in sorted(params)]
    return f"{model_id}::" + "|".join(parts)


def _evaluate_model(model_id: str) -> Dict[str, object]:
    issues: List[str] = []
    schema = get_model_schema(model_id)
    ssot = load_pricing_ssot()
    raw_models = {m.get("id"): m for m in ssot.get("models", []) if isinstance(m, dict)}
    raw_model = raw_models.get(model_id, {})
    unmapped = raw_model.get("unmapped", []) if isinstance(raw_model, dict) else []
    if not schema:
        return {
            "status": STATUS_MISSING_PARAM_SCHEMA,
            "issues": ["No parameter schema in registry."],
        }
    skus = list_model_skus(model_id)
    found_skus = sorted({sku.sku_id for sku in skus})
    if not skus:
        base_issues = ["No READY pricing SKUs in SSOT."]
        if unmapped:
            base_issues.append("SSOT has unmapped pricing entries (missing param schema).")
            return {
                "status": STATUS_MISSING_PARAM_SCHEMA,
                "issues": base_issues,
                "found_skus": found_skus,
            }
        return {
            "status": STATUS_MISSING_PRICE,
            "issues": base_issues,
            "found_skus": found_skus,
        }

    dims = get_price_dimensions(model_id)
    combos, combo_issues = build_param_combinations(model_id)
    issues.extend(combo_issues)
    if combo_issues:
        return {
            "status": STATUS_MISSING_PARAM_SCHEMA,
            "issues": issues,
            "found_skus": found_skus,
        }

    missing_price = False
    ambiguous = False
    expected_skus: List[str] = []
    missing_skus: List[str] = []
    resolver_misses: List[str] = []
    for combo in combos:
        expected_key = _build_sku_key(model_id, combo)
        expected_skus.append(expected_key)
        matches = [
            sku
            for sku in skus
            if all(str(combo.get(key)) == str(sku.params.get(key)) for key in dims)
        ]
        if not matches:
            missing_price = True
            missing_skus.append(expected_key)
        if len(matches) > 1:
            ambiguous = True
        if len(matches) == 1:
            quote = resolve_price_quote(
                model_id=model_id,
                mode_index=0,
                gen_type=None,
                selected_params=combo,
            )
            if not quote or quote.sku_id != matches[0].sku_id:
                resolver_misses.append(expected_key)

    if resolver_misses:
        issues.append("Price resolver mismatch for SKU keys: " + ", ".join(sorted(set(resolver_misses))))

    if ambiguous:
        issues.append("Multiple SKUs match the same param combination.")
        return {
            "status": STATUS_AMBIGUOUS,
            "issues": issues,
            "expected_skus": sorted(set(expected_skus)),
            "found_skus": found_skus,
            "missing_skus": sorted(set(missing_skus)),
        }
    if missing_price:
        issues.append("At least one param combination has no price.")
        return {
            "status": STATUS_MISSING_PRICE,
            "issues": issues,
            "expected_skus": sorted(set(expected_skus)),
            "found_skus": found_skus,
            "missing_skus": sorted(set(missing_skus)),
        }
    return {
        "status": STATUS_READY,
        "issues": issues,
        "expected_skus": sorted(set(expected_skus)),
        "found_skus": found_skus,
        "missing_skus": sorted(set(missing_skus)),
    }


def main() -> None:
    model_ids = list_model_ids()
    results: Dict[str, Dict[str, object]] = {}
    counts = {
        STATUS_READY: 0,
        STATUS_MISSING_PRICE: 0,
        STATUS_MISSING_PARAM_SCHEMA: 0,
        STATUS_AMBIGUOUS: 0,
    }
    for model_id in model_ids:
        result = _evaluate_model(model_id)
        results[model_id] = result
        counts[result["status"]] += 1

    report = {
        "summary": counts,
        "total_models": len(model_ids),
        "models": results,
    }

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Pricing coverage report")
    lines.append("")
    lines.append(f"Total models: {len(model_ids)}")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("| --- | ---: |")
    for key, value in counts.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## Models")
    lines.append("")
    for model_id in sorted(model_ids):
        entry = results[model_id]
        status = entry["status"]
        issues = entry.get("issues", [])
        expected_skus = entry.get("expected_skus", [])
        found_skus = entry.get("found_skus", [])
        missing_skus = entry.get("missing_skus", [])
        lines.append(f"### model-{_slugify(model_id)}")
        lines.append(f"**{model_id}** — `{status}`")
        if issues:
            lines.append("")
            lines.append("Issues:")
            for issue in issues:
                lines.append(f"- {issue}")
        if model_id == "sora-2-text-to-video" or missing_skus or status != STATUS_READY:
            lines.append("")
            lines.append("SKU diagnostics:")
            if expected_skus:
                lines.append(f"- Expected: {', '.join(expected_skus)}")
            if found_skus:
                lines.append(f"- Found: {', '.join(found_skus)}")
            if missing_skus:
                lines.append(f"- Missing: {', '.join(missing_skus)}")
        lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
