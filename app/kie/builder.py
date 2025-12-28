"""
Universal payload builder for Kie.ai createTask based on model schema from source_of_truth.
"""
import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ModelsView(dict):
    """Dict wrapper where iteration yields model configs (values), not keys.

    This allows code/tests to use BOTH patterns:
    - for model_id, cfg in models.items(): ...
    - for cfg in models: ...  (iterates over values)
    """

    def __iter__(self):
        return iter(self.values())




def load_source_of_truth(file_path: str = "models/kie_api_models.json") -> Dict[str, Any]:
    """Load SOURCE OF TRUTH registry.

    The on-disk registry uses: {"models": {model_id: {...}}}

    Some parts of the code/tests iterate models as a list (for cfg in models),
    while others expect a dict (models.items()).

    We satisfy both by wrapping models dict with ModelsView where __iter__ yields values.
    """
    master_path = "models/KIE_SOURCE_OF_TRUTH.json"

    if not os.path.exists(master_path):
        logger.error(f"CRITICAL: SOURCE_OF_TRUTH not found: {master_path}")
        return {}

    logger.info(f"✅ Using SOURCE_OF_TRUTH (master): {master_path}")

    with open(master_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Enforce runtime allowlist lock (expected 42 models)
    try:
        from app.utils.config import get_config
        cfg = get_config()
        if getattr(cfg, "minimal_models_locked", True):
            allowed = list(getattr(cfg, "allowed_model_ids", []) or getattr(cfg, "minimal_model_ids", []) or [])
            if allowed:
                models = data.get("models", {})
                if isinstance(models, dict):
                    data["models"] = {mid: models[mid] for mid in allowed if mid in models}
                elif isinstance(models, list):
                    allowset = set(allowed)
                    data["models"] = [m for m in models if (m or {}).get("model_id") in allowset]
    except Exception:
        pass


    models = data.get("models", {})
    if isinstance(models, dict):
        # Ensure every model has model_id field (some registries store it in the key)
        normalized = {}
        for mid, cfg in models.items():
            if not isinstance(cfg, dict):
                continue
            if not cfg.get("model_id"):
                cfg = {**cfg, "model_id": mid}
            normalized[mid] = cfg
        data["models"] = ModelsView(normalized)
    else:
        # Fallback: keep whatever, but ensure at least iterable
        data["models"] = models or ModelsView({})

    return data




def get_model_schema(model_id: str, source_of_truth: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """Get model schema from source of truth."""
    if source_of_truth is None:
        source_of_truth = load_source_of_truth()

    models = source_of_truth.get("models", {})
    # dict-like (including ModelsView)
    if hasattr(models, "get") and hasattr(models, "items"):
        cfg = models.get(model_id)
        if isinstance(cfg, dict):
            return cfg

    # list fallback
    if isinstance(models, list):
        for model in models:
            if isinstance(model, dict) and model.get("model_id") == model_id:
                return model

    logger.warning(f"Model {model_id} not found in source of truth")
    return None




def get_model_config(model_id: str, source_of_truth: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """
    Get full model configuration including metadata, pricing, and schema.
    
    Returns complete model data for UI display:
    - model_id, provider, category
    - display_name, description
    - pricing (rub_per_gen, usd_per_gen)
    - input_schema or parameters
    - endpoint, method
    - examples, tags, ui_example_prompts
    
    Args:
        model_id: Model identifier
        source_of_truth: Optional pre-loaded source of truth
        
    Returns:
        Full model configuration dict or None if not found
    """
    return get_model_schema(model_id, source_of_truth)


def build_payload(model_id: str, user_inputs: Dict[str, Any], source_of_truth: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build Kie createTask payload.

    Supports two payload formats:
      - wrapped (default): {"model": "...", "input": {...}}
      - direct:            {"model": "...", <fields...>}

    The format is driven by model_schema.payload_format (SOURCE_OF_TRUTH).
    """

    model_schema = get_model_schema(model_id, source_of_truth=source_of_truth)
    if not model_schema:
        raise ValueError(f"Unknown model: {model_id}")

    api_endpoint = model_schema.get('api_endpoint', model_id)

    forced_format = (model_schema or {}).get('payload_format') or (model_schema or {}).get('payloadFormat')
    forced_format = str(forced_format).strip().lower() if forced_format else 'wrapped'
    is_direct_format = forced_format in {'direct', 'flat'}

    payload: Dict[str, Any] = {'model': api_endpoint}
    payload_input: Dict[str, Any]

    if is_direct_format:
        payload_input = payload
        logger.info(f"Using DIRECT format for {model_id} (flat fields)")
    else:
        payload['input'] = {}
        payload_input = payload['input']
        logger.info(f"Using WRAPPED format for {model_id} (input wrapper)")

    input_schema = model_schema.get('input_schema') or {}

    # Normalize schema to (properties, required_fields)
    properties: Dict[str, Any] = {}
    required_fields: list[str] = []

    if isinstance(input_schema, dict) and input_schema.get('type') == 'object' and isinstance(input_schema.get('properties'), dict):
        properties = input_schema.get('properties', {})
        required_fields = list(input_schema.get('required', []) or [])
    elif isinstance(input_schema, dict) and input_schema and all(isinstance(v, dict) for v in input_schema.values()):
        # "flat spec" schema: {field: {type, required?, default?...}}
        properties = input_schema
        required_fields = [k for k, v in properties.items() if v.get('required') is True]
    else:
        logger.warning(f"Model {model_id} has unsupported input_schema format: {type(input_schema)}")

    # Convert + attach fields
    def _convert_value(field: str, spec: Dict[str, Any], value: Any) -> Any:
        if value is None:
            return None

        field_type = (spec.get('type') or '').lower()
        field_format = (spec.get('format') or '').lower()

        # Keep URLs as strings (wizard already converts TG files into signed URLs)
        if field_format in {'uri', 'url'}:
            return str(value)

        if field_type == 'string':
            return str(value)
        if field_type == 'integer':
            try:
                return int(value)
            except Exception:
                return value
        if field_type == 'number':
            try:
                return float(value)
            except Exception:
                return value
        if field_type == 'boolean':
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                v = value.strip().lower()
                if v in {'true', '1', 'yes', 'y', 'да'}:
                    return True
                if v in {'false', '0', 'no', 'n', 'нет'}:
                    return False
            return bool(value)
        return value

    # Required fields
    missing_required: list[str] = []
    for field in required_fields:
        spec = properties.get(field, {}) if isinstance(properties.get(field), dict) else {}

        if field in user_inputs:
            payload_input[field] = _convert_value(field, spec, user_inputs[field])
        elif isinstance(spec, dict) and 'default' in spec:
            payload_input[field] = spec['default']
            logger.info(f"Using default value for {field}: {spec['default']}")
        else:
            missing_required.append(field)

    if missing_required:
        # Let validator format the final error; but keep logs super explicit
        logger.error(f"Missing required fields for {model_id}: {missing_required}. user_inputs={list(user_inputs.keys())}")

    # Optional fields (only if provided)
    for field, spec in properties.items():
        if field in required_fields:
            continue
        if field in user_inputs:
            payload_input[field] = _convert_value(field, spec if isinstance(spec, dict) else {}, user_inputs[field])

    # Validate against contract before hitting Kie
    validate_payload_before_create_task(model_id, payload, model_schema=model_schema)

    logger.info(f"Payload built model={model_id} keys={list(payload.keys())} input_keys={list(payload_input.keys())}")
    return payload

def build_payload_from_text(model_id: str, text: str, **kwargs) -> Dict[str, Any]:
    """Convenience method to build payload from text input."""
    user_inputs = {'text': text, 'prompt': text, 'input': text, **kwargs}
    return build_payload(model_id, user_inputs)


def build_payload_from_url(model_id: str, url: str, **kwargs) -> Dict[str, Any]:
    """Convenience method to build payload from URL input."""
    user_inputs = {'url': url, 'link': url, 'source_url': url, **kwargs}
    return build_payload(model_id, user_inputs)


def build_payload_from_file(model_id: str, file_id: str, **kwargs) -> Dict[str, Any]:
    """Convenience method to build payload from file input."""
    user_inputs = {'file': file_id, 'file_id': file_id, 'file_url': file_id, **kwargs}
    return build_payload(model_id, user_inputs)
