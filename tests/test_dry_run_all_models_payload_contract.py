import json
from typing import Any, Dict, List, Tuple

from app.kie.builder import build_payload, load_source_of_truth
from app.kie.validator import ModelContractError, validate_payload_before_create_task


PLACEHOLDER_IMAGE = "https://example.com/image.png"
PLACEHOLDER_VIDEO = "https://example.com/video.mp4"
PLACEHOLDER_AUDIO = "https://example.com/audio.wav"
PLACEHOLDER_URL = "https://example.com/resource"
DEFAULT_PROMPT = "котик"


def _clone_default(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.loads(json.dumps(value))
    return value


def _extract_schema(model_cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    if "parameters" in model_cfg and isinstance(model_cfg.get("parameters"), dict):
        params = model_cfg["parameters"] or {}
        required = [k for k, v in params.items() if isinstance(v, dict) and v.get("required")]
        return params, required

    input_schema = model_cfg.get("input_schema") or {}
    if isinstance(input_schema, dict) and input_schema.get("type") == "object" and isinstance(
        input_schema.get("properties"), dict
    ):
        properties = input_schema.get("properties") or {}
        required = list(input_schema.get("required") or [])
        return properties, required

    if isinstance(input_schema, dict):
        properties = input_schema
        required = [k for k, v in properties.items() if isinstance(v, dict) and v.get("required")]
        return properties, required

    return {}, []


def _value_for_field(field_name: str, spec: Dict[str, Any]) -> Any:
    fname = field_name.lower()
    field_type = spec.get("type")

    if "enum" in spec and spec["enum"]:
        return spec["enum"][0]

    if spec.get("default") is not None:
        return _clone_default(spec.get("default"))

    if "prompt" in fname or fname in {"text", "query", "message", "input"}:
        return DEFAULT_PROMPT

    if "image" in fname:
        return PLACEHOLDER_IMAGE

    if "audio" in fname:
        return PLACEHOLDER_AUDIO

    if "video" in fname:
        return PLACEHOLDER_VIDEO

    if fname.endswith("_url") or fname == "url":
        return PLACEHOLDER_URL

    if field_type == "boolean":
        return True

    if field_type == "integer":
        return int(spec.get("minimum", 1) or 1)

    if field_type == "number":
        return float(spec.get("minimum", 0.5) or 0.5)

    if field_type == "array":
        item_spec = spec.get("items") if isinstance(spec.get("items"), dict) else {}
        return [_value_for_field(f"{field_name}_item", item_spec) or DEFAULT_PROMPT]

    if field_type == "object":
        return {}

    return DEFAULT_PROMPT


def _build_minimal_inputs(model_cfg: Dict[str, Any]) -> Dict[str, Any]:
    properties, required = _extract_schema(model_cfg)

    fields = list(required) if required else list(properties.keys())
    if not fields and "prompt" in properties:
        fields = ["prompt"]

    inputs: Dict[str, Any] = {}
    for field in fields:
        spec = properties.get(field, {}) if isinstance(properties, dict) else {}
        value = _value_for_field(field, spec if isinstance(spec, dict) else {})
        inputs[field] = value

    if not inputs:
        inputs["prompt"] = DEFAULT_PROMPT

    return inputs


def test_payload_contract_all_enabled_models():
    sot = load_source_of_truth()
    models = sot.get("models", {})

    enabled_models = {
        mid: cfg
        for mid, cfg in models.items()
        if isinstance(cfg, dict) and cfg.get("enabled", True) and not mid.endswith("_processor")
    }

    totals = {
        "passed": [],
        "skipped": [],
        "contract_errors": [],
        "unexpected_errors": [],
    }

    for model_id, cfg in enabled_models.items():
        try:
            inputs = _build_minimal_inputs(cfg)
            if inputs is None:
                totals["skipped"].append((model_id, "inputs-not-derived"))
                continue

            payload = build_payload(model_id, inputs, sot)
            validate_payload_before_create_task(model_id, payload, cfg)
            totals["passed"].append(model_id)
        except ModelContractError as err:
            totals["contract_errors"].append((model_id, str(err)))
        except Exception as err:  # pragma: no cover - unexpected path we assert below
            totals["unexpected_errors"].append((model_id, str(err)))

    print("\nPAYLOAD CONTRACT SUMMARY")
    print(f"Total enabled: {len(enabled_models)}")
    print(f"Passed: {len(totals['passed'])}")
    print(f"Skipped: {len(totals['skipped'])}")
    print(f"Contract errors: {len(totals['contract_errors'])}")
    if totals["contract_errors"]:
        print("First contract error:", totals["contract_errors"][0])

    if totals["unexpected_errors"]:
        print("Unexpected errors:")
        for mid, msg in totals["unexpected_errors"]:
            print(f" - {mid}: {msg}")

    assert len(totals["unexpected_errors"]) == 0, f"Unexpected errors: {totals['unexpected_errors']}"
    assert len(totals["passed"]) + len(totals["skipped"]) + len(totals["contract_errors"]) == len(
        enabled_models
    )
