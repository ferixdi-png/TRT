#!/usr/bin/env python3
"""Audit model readiness across registry, pricing, schemas, and mock delivery."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.kie_catalog import get_model_map
from app.kie_catalog.input_schemas import get_schema_for_type
from app.kie_contract.payload_builder import build_kie_payload, PayloadBuildError
from kie_gateway import MockKieGateway

REGISTRY_PATH = ROOT / "models" / "kie_models.yaml"
PRICING_PATH = ROOT / "app" / "kie_catalog" / "models_pricing.yaml"
REPORT_PATH = ROOT / "TRT_MODEL_READINESS.md"
ARTIFACT_PATH = ROOT / "artifacts" / "model_readiness.json"


MEDIA_FIELD_TOKENS = ("image", "mask", "video", "audio", "voice")


def _load_registry() -> Dict[str, Any]:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return payload if isinstance(payload, dict) else {}


def _load_pricing() -> List[Dict[str, Any]]:
    with PRICING_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if isinstance(payload, dict):
        models = payload.get("models", [])
        return models if isinstance(models, list) else []
    return payload if isinstance(payload, list) else []


def _generation_type_from_model_type(model_type: Optional[str]) -> str:
    if not model_type:
        return ""
    return model_type.replace("_", "-")


def _derive_model_gen_type(model_mode: Optional[str], model_type: Optional[str]) -> str:
    return _generation_type_from_model_type(model_mode or model_type)


def _collect_schema_fields(schema: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    required: List[str] = []
    optional: List[str] = []
    for name, spec in schema.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("required"):
            required.append(name)
        else:
            optional.append(name)
    return sorted(required), sorted(optional)


def _infer_media_kind(field_name: str) -> Optional[str]:
    field_lower = field_name.lower()
    if "video" in field_lower:
        return "video"
    if "audio" in field_lower or "voice" in field_lower:
        return "audio"
    if "image" in field_lower or "mask" in field_lower:
        return "image"
    if "document" in field_lower or "file" in field_lower:
        return "document"
    return None


def _derive_required_media_expected(model_type: str, schema: Dict[str, Any]) -> List[str]:
    required_fields, _ = _collect_schema_fields(schema)
    media_expected = {
        _infer_media_kind(field)
        for field in required_fields
    }
    media_expected.discard(None)
    if media_expected:
        return sorted(media_expected)

    model_type_lower = (model_type or "").lower()
    inferred: List[str] = []
    if model_type_lower in {"image_edit", "image_to_image", "image_to_video", "outpaint", "image_upscale", "upscale"}:
        inferred.append("image")
    if model_type_lower in {"video_upscale", "video_editing", "video_to_video", "v2v"}:
        inferred.append("video")
    if model_type_lower in {"speech_to_text", "audio_to_audio"}:
        inferred.append("audio")
    return sorted(set(inferred))


def _detect_ssot_conflicts(model_type: str, schema: Dict[str, Any]) -> List[str]:
    conflicts: List[str] = []
    required_media = [
        name for name, spec in schema.items()
        if isinstance(spec, dict)
        and spec.get("required")
        and any(token in name.lower() for token in MEDIA_FIELD_TOKENS)
    ]
    model_type_lower = (model_type or "").lower()
    if model_type_lower in {"text_to_image", "text_to_video", "text_to_audio", "text_to_speech", "text"}:
        for field in required_media:
            field_lower = field.lower()
            if "video" in field_lower:
                conflicts.append("SSOT_CONFLICT_TEXT_MODEL_REQUIRES_VIDEO")
            elif "audio" in field_lower or "voice" in field_lower:
                conflicts.append("SSOT_CONFLICT_TEXT_MODEL_REQUIRES_AUDIO")
            else:
                conflicts.append("SSOT_CONFLICT_TEXT_MODEL_REQUIRES_IMAGE")
    if model_type_lower in {
        "image_edit",
        "image_to_image",
        "image_to_video",
        "outpaint",
        "upscale",
    }:
        if not any("image" in name.lower() for name in required_media):
            conflicts.append("SSOT_CONFLICT_IMAGE_MODEL_MISSING_IMAGE_INPUT")
    if model_type_lower in {"speech_to_text", "audio_to_audio"}:
        if not any("audio" in name.lower() or "voice" in name.lower() for name in required_media):
            conflicts.append("SSOT_CONFLICT_AUDIO_MODEL_MISSING_AUDIO_INPUT")
    if model_type_lower in {"video_upscale", "video_editing", "video_to_video", "v2v"}:
        if not any("video" in name.lower() for name in required_media):
            conflicts.append("SSOT_CONFLICT_VIDEO_MODEL_MISSING_VIDEO_INPUT")
    return sorted(set(conflicts))


def _mode_has_ru(mode: Dict[str, Any]) -> bool:
    return bool(mode.get("title_ru")) and bool(mode.get("short_hint_ru"))


def _collect_mode_missing_fields(model_id: str, modes: List[Dict[str, Any]]) -> List[str]:
    missing: List[str] = []
    for index, mode in enumerate(modes):
        if not mode.get("title_ru"):
            missing.append(
                f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].modes[{index}].title_ru"
            )
        if not mode.get("short_hint_ru"):
            missing.append(
                f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].modes[{index}].short_hint_ru"
            )
    return missing


def _collect_price_missing_fields(model_id: str, modes: List[Dict[str, Any]]) -> List[str]:
    missing: List[str] = []
    for index, mode in enumerate(modes):
        if "unit" not in mode:
            missing.append(
                f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].modes[{index}].unit"
            )
        if "credits" not in mode:
            missing.append(
                f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].modes[{index}].credits"
            )
        if "official_usd" not in mode:
            missing.append(
                f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].modes[{index}].official_usd"
            )
    return missing


def _collect_model_card_missing_fields(model_id: str, pricing_data: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    if "description_ru" not in pricing_data:
        missing.append(f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].description_ru")
    if "required_inputs_ru" not in pricing_data:
        missing.append(f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].required_inputs_ru")
    if "output_type_ru" not in pricing_data:
        missing.append(f"app/kie_catalog/models_pricing.yaml:models[id={model_id}].output_type_ru")
    return missing


def _build_minimal_params(schema: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for field in required_fields:
        spec = schema.get(field, {})
        field_type = spec.get("type", "string")
        field_lower = field.lower()
        ext = ".png"
        if "video" in field_lower:
            ext = ".mp4"
        elif "audio" in field_lower or "voice" in field_lower:
            ext = ".mp3"
        if field_type == "string":
            if "prompt" in field_lower or "text" in field_lower:
                params[field] = "Test prompt"
            elif "url" in field_lower or "image" in field_lower or "video" in field_lower or "audio" in field_lower:
                params[field] = f"https://example.com/test{ext}"
            else:
                params[field] = "test_value"
        elif field_type == "enum":
            values = spec.get("values") or []
            params[field] = values[0] if values else "default"
        elif field_type == "array":
            item_type = spec.get("item_type", "string")
            if item_type == "string":
                params[field] = [f"https://example.com/test{ext}"]
            else:
                params[field] = []
        elif field_type == "boolean":
            params[field] = spec.get("default", False)
        elif field_type in ("number", "integer", "float"):
            params[field] = spec.get("min", spec.get("default", 1))
        else:
            params[field] = "test_value"
    return params


async def _dry_run_delivery(model_id: str, payload_input: Dict[str, Any]) -> Tuple[bool, str]:
    gateway = MockKieGateway()
    create_result = await gateway.create_task(model_id, payload_input)
    if not create_result.get("ok"):
        return False, f"create_task_failed:{create_result.get('error')}"
    task_id = create_result.get("taskId")
    if not task_id:
        return False, "create_task_missing_task_id"
    if hasattr(gateway, "_tasks") and task_id in gateway._tasks:
        gateway._tasks[task_id]["created_at"] -= 1.0
    for _ in range(3):
        status_result = await gateway.get_task(task_id)
        if not status_result.get("ok"):
            return False, f"get_task_failed:{status_result.get('error')}"
        state = (status_result.get("status") or status_result.get("state") or "").lower()
        if state == "success":
            result_json = status_result.get("resultJson") or "{}"
            try:
                parsed = json.loads(result_json)
            except json.JSONDecodeError:
                parsed = {}
            urls = []
            if isinstance(parsed, dict):
                urls = parsed.get("resultUrls") or parsed.get("urls") or parsed.get("result_urls") or []
            if isinstance(urls, str):
                urls = [urls]
            if urls:
                return True, ""
            return False, "missing_result_urls"
        await asyncio.sleep(0.01)
    return False, "task_not_completed"


@dataclass
class ModelReadiness:
    model_id: str
    status: str
    status_symbol: str
    gen_type: str
    model_mode: str
    model_type: str
    schema_key: str
    required_inputs: List[str]
    optional_inputs: List[str]
    required_media_expected: List[str]
    mode_count: int
    has_ru_mode_titles: bool
    has_ru_model_card: bool
    has_price_mapping: bool
    can_build_api_request: bool
    can_deliver_output: bool
    ssot_conflicts: List[str]
    missing_fields: List[str]
    blocked_reason: List[str]
    notes: str


async def audit() -> List[ModelReadiness]:
    registry = _load_registry()
    registry_models = registry.get("models", {}) if isinstance(registry.get("models"), dict) else {}
    pricing_models = _load_pricing()
    pricing_map = {entry.get("id"): entry for entry in pricing_models if isinstance(entry, dict)}
    catalog_map = get_model_map()

    all_model_ids = sorted(set(registry_models.keys()) | set(pricing_map.keys()))

    results: List[ModelReadiness] = []
    for model_id in all_model_ids:
        registry_data = registry_models.get(model_id, {})
        pricing_data = pricing_map.get(model_id, {})
        schema = registry_data.get("input") if isinstance(registry_data, dict) else {}
        if not isinstance(schema, dict):
            schema = {}
        model_type = registry_data.get("model_type", "") if isinstance(registry_data, dict) else ""
        schema_key = pricing_data.get("type", "") if isinstance(pricing_data, dict) else ""

        missing_fields: List[str] = []
        notes: List[str] = []

        if not registry_data:
            missing_fields.append(f"models/kie_models.yaml:models.{model_id}")
        if registry_data and not model_type:
            missing_fields.append(f"models/kie_models.yaml:models.{model_id}.model_type")
        if not schema:
            missing_fields.append(f"models/kie_models.yaml:models.{model_id}.input")
        if not pricing_data:
            missing_fields.append(f"app/kie_catalog/models_pricing.yaml:models[id={model_id}]")

        schema_required, schema_optional = _collect_schema_fields(schema)
        required_media_expected = _derive_required_media_expected(model_type, schema)
        ssot_conflicts = _detect_ssot_conflicts(model_type, schema) if model_type else []

        if schema_key and not get_schema_for_type(schema_key):
            missing_fields.append(
                f"app/kie_catalog/input_schemas.py:INPUT_SCHEMAS['{schema_key}']"
            )

        modes = pricing_data.get("modes", []) if isinstance(pricing_data, dict) else []
        mode_count = len(modes) if isinstance(modes, list) else 0

        has_ru_mode_titles = bool(modes) and all(_mode_has_ru(mode) for mode in modes)
        if isinstance(modes, list):
            missing_fields.extend(_collect_mode_missing_fields(model_id, modes))

        has_price_mapping = bool(modes) and all(
            isinstance(mode, dict) and "credits" in mode and "official_usd" in mode and "unit" in mode
            for mode in modes
        )
        if isinstance(modes, list):
            missing_fields.extend(_collect_price_missing_fields(model_id, modes))

        has_ru_model_card = bool(pricing_data) and all(
            key in pricing_data for key in ("description_ru", "required_inputs_ru", "output_type_ru")
        )
        if isinstance(pricing_data, dict):
            missing_fields.extend(_collect_model_card_missing_fields(model_id, pricing_data))

        model_spec = catalog_map.get(model_id)
        model_mode = ""
        if model_spec:
            model_mode = getattr(model_spec, "model_mode", "") or ""
        gen_type = _derive_model_gen_type(model_mode, model_type)
        can_build_api_request = False
        can_deliver_output = False
        if model_spec and schema:
            minimal_params = _build_minimal_params(schema, model_spec.schema_required)
            try:
                payload = build_kie_payload(model_spec, minimal_params)
                can_build_api_request = True
                delivery_ok, delivery_error = await _dry_run_delivery(
                    model_spec.kie_model,
                    payload.get("input", {}),
                )
                can_deliver_output = delivery_ok
                if delivery_error:
                    notes.append(delivery_error)
            except PayloadBuildError as exc:
                notes.append(str(exc))
            except Exception as exc:
                notes.append(f"build_failed:{exc}")
        else:
            if not model_spec:
                notes.append("missing_catalog_entry")

        required_inputs_ok = bool(schema_required)
        if not required_inputs_ok and model_type:
            missing_fields.append(f"models/kie_models.yaml:models.{model_id}.input(required)")

        blocked = (
            bool(ssot_conflicts)
            or not required_inputs_ok
            or not can_build_api_request
            or not can_deliver_output
            or not has_price_mapping
            or not pricing_data
            or not registry_data
        )
        partial = (not blocked) and (not has_ru_mode_titles or not has_ru_model_card)
        blocked_reason: List[str] = []
        if ssot_conflicts:
            blocked_reason.append("SSOT_CONFLICT")
        if not required_inputs_ok:
            blocked_reason.append("MISSING_REQUIRED_INPUTS")
        if not can_build_api_request:
            blocked_reason.append("CANNOT_BUILD_API_REQUEST")
        if not can_deliver_output:
            blocked_reason.append("CANNOT_DELIVER_OUTPUT")
        if not has_price_mapping or not pricing_data:
            blocked_reason.append("MISSING_PRICING")
        if not registry_data:
            blocked_reason.append("MISSING_REGISTRY_ENTRY")
        if not schema:
            blocked_reason.append("MISSING_SCHEMA")

        if blocked:
            status = "BLOCKED"
            status_symbol = "⛔"
        elif partial:
            status = "PARTIAL"
            status_symbol = "⚠️"
        else:
            status = "READY"
            status_symbol = "✅"

        results.append(
            ModelReadiness(
                model_id=model_id,
                status=status,
                status_symbol=status_symbol,
                gen_type=gen_type,
                model_mode=model_mode,
                model_type=model_type,
                schema_key=schema_key,
                required_inputs=schema_required,
                optional_inputs=schema_optional,
                required_media_expected=required_media_expected,
                mode_count=mode_count,
                has_ru_mode_titles=has_ru_mode_titles,
                has_ru_model_card=has_ru_model_card,
                has_price_mapping=has_price_mapping,
                can_build_api_request=can_build_api_request,
                can_deliver_output=can_deliver_output,
                ssot_conflicts=ssot_conflicts,
                missing_fields=sorted(set(missing_fields)),
                blocked_reason=sorted(set(blocked_reason)),
                notes="; ".join(sorted(set(notes))),
            )
        )

    return results


def _render_markdown(results: List[ModelReadiness]) -> str:
    ready = sum(1 for r in results if r.status == "READY")
    partial = sum(1 for r in results if r.status == "PARTIAL")
    blocked = sum(1 for r in results if r.status == "BLOCKED")

    blockers: Dict[str, int] = {}
    for result in results:
        if result.status != "BLOCKED":
            continue
        for conflict in result.ssot_conflicts:
            blockers[conflict] = blockers.get(conflict, 0) + 1
        if result.missing_fields:
            blockers["MISSING_FIELDS"] = blockers.get("MISSING_FIELDS", 0) + 1

    blocker_lines = "\n".join(
        f"- {key}: {count}" for key, count in sorted(blockers.items(), key=lambda item: item[1], reverse=True)
    ) or "- None"

    lines = [
        "# TRT Model Readiness Report",
        "",
        "## Summary by category",
        "",
        f"- ✅ READY: {ready}",
        f"- ⚠️ PARTIAL: {partial}",
        f"- ⛔ BLOCKED: {blocked}",
        "",
        "### Top blockers",
        blocker_lines,
        "",
        "## Model readiness matrix",
        "",
        "| status | model_id | gen_type | model_mode | model_type | schema_key | required_inputs | required_media_expected | optional_inputs | mode_count | has_ru_mode_titles | has_ru_model_card | has_price_mapping | can_build_api_request | can_deliver_output | ssot_conflicts | missing_fields | blocked_reason | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for result in results:
        lines.append(
            "| {status_symbol} | {model_id} | {gen_type} | {model_mode} | {model_type} | {schema_key} | {required_inputs} | {required_media_expected} | {optional_inputs} | {mode_count} | {has_ru_mode_titles} | {has_ru_model_card} | {has_price_mapping} | {can_build_api_request} | {can_deliver_output} | {ssot_conflicts} | {missing_fields} | {blocked_reason} | {notes} |".format(
                status_symbol=result.status_symbol,
                model_id=result.model_id,
                gen_type=result.gen_type or "—",
                model_mode=result.model_mode or "—",
                model_type=result.model_type or "—",
                schema_key=result.schema_key or "—",
                required_inputs=", ".join(result.required_inputs) if result.required_inputs else "—",
                required_media_expected=", ".join(result.required_media_expected) if result.required_media_expected else "—",
                optional_inputs=", ".join(result.optional_inputs) if result.optional_inputs else "—",
                mode_count=result.mode_count,
                has_ru_mode_titles="yes" if result.has_ru_mode_titles else "no",
                has_ru_model_card="yes" if result.has_ru_model_card else "no",
                has_price_mapping="yes" if result.has_price_mapping else "no",
                can_build_api_request="yes" if result.can_build_api_request else "no",
                can_deliver_output="yes" if result.can_deliver_output else "no",
                ssot_conflicts=", ".join(result.ssot_conflicts) if result.ssot_conflicts else "—",
                missing_fields=", ".join(result.missing_fields) if result.missing_fields else "—",
                blocked_reason=", ".join(result.blocked_reason) if result.blocked_reason else "—",
                notes=result.notes or "—",
            )
        )
    lines.append("")
    return "\n".join(lines)


def _write_outputs(results: List[ModelReadiness]) -> None:
    REPORT_PATH.write_text(_render_markdown(results), encoding="utf-8")
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {result.model_id: asdict(result) for result in results},
    }
    ARTIFACT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    results = asyncio.run(audit())
    _write_outputs(results)
    print(f"Wrote {REPORT_PATH} and {ARTIFACT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
