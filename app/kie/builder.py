"""
Universal payload builder for Kie.ai createTask based on model schema from source_of_truth.
"""
import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def _apply_schema_defaults(input_obj: Dict[str, Any], input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing fields in input_obj using JSONSchema defaults.

    Это ключевой фикс для Syntx-parity: часть моделей Kie.ai на практике требует
    параметры (aspect_ratio, duration, etc.) даже если UI их не спрашивает,
    но они присутствуют в schema с default. Мы добавляем такие defaults
    централизованно, чтобы:
      - wizard не разрастался вопросами
      - dry-run валидация совпадала с реальным контрактом
    """
    if not isinstance(input_schema, dict):
        return input_obj

    props = input_schema.get("properties") or {}
    if not isinstance(props, dict):
        return input_obj

    out = dict(input_obj or {})
    for k, spec in props.items():
        if k in out:
            continue
        if not isinstance(spec, dict):
            continue
        if "default" not in spec:
            continue
        # Respect explicit nulls in schema, but don't inject None by default.
        dv = spec.get("default")
        if dv is None:
            continue
        # Copy complex defaults to avoid shared state.
        if isinstance(dv, (dict, list)):
            out[k] = json.loads(json.dumps(dv))
        else:
            out[k] = dv

    return out


OVERLAY_PATH = Path("models") / "KIE_OVERLAY.json"


def _deep_merge_model_cfg(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Merge per-model overlay with base config.

    Overlay is treated as authoritative for top-level keys like:
    - category
    - output_type
    - input_schema
    - display_name

    We don't do a nested merge for input_schema (it's replaced entirely).
    """

    merged = dict(base)
    if not overlay:
        return merged

    for k, v in overlay.items():
        if k == "input_schema" and isinstance(v, dict):
            merged[k] = dict(v)
        else:
            merged[k] = v
    return merged


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

    # Apply per-model overlay (schema/category/output fixes).
    # This is critical for correct UX and correct payload building.
    # IMPORTANT: overlay format historically changed; use a single loader.
    try:
        from app.kie.overlay_loader import load_kie_overlay

        models = data.get("models", {})
        overrides = load_kie_overlay(OVERLAY_PATH) if OVERLAY_PATH.exists() else {}
        if isinstance(models, dict) and overrides:
            for mid, ov in overrides.items():
                if mid in models and isinstance(models[mid], dict) and isinstance(ov, dict):
                    models[mid] = _deep_merge_model_cfg(models[mid], ov)
            data["models"] = models
    except Exception as e:
        logger.warning("Failed to apply KIE overlay: %s", e)


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


def build_payload(
    model_id: str,
    user_inputs: Dict[str, Any],
    source_of_truth: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Build createTask payload for Kie.ai API.
    
    Args:
        model_id: Model identifier
        user_inputs: User-provided inputs (text, url, file, etc.)
        source_of_truth: Optional pre-loaded source of truth
        
    Returns:
        Payload dictionary for createTask API
    """
    model_schema = get_model_schema(model_id, source_of_truth)
    if not model_schema:
        raise ValueError(f"Model {model_id} not found in source of truth")

    from app.kie.validator import validate_model_inputs, validate_payload_before_create_task

    validate_model_inputs(model_id, model_schema, user_inputs)

    # V7 format detection: has 'parameters' instead of 'input_schema'
    is_v7 = 'parameters' in model_schema and 'endpoint' in model_schema
    
    if is_v7:
        # V7: Specialized endpoints, direct parameters (not wrapped in 'input')
        parameters_schema = model_schema.get('parameters', {})
        api_endpoint = model_schema.get('endpoint') or model_id

        # Build raw parameters first
        raw_params: Dict[str, Any] = {}

        # Добавляем параметры из user_inputs
        for param_name, param_spec in parameters_schema.items():
            if param_name in user_inputs:
                raw_params[param_name] = user_inputs[param_name]
            elif param_spec.get('default') is not None:
                raw_params[param_name] = param_spec['default']
            elif param_spec.get('required'):
                # Для обязательных параметров без значения - пытаемся подобрать
                if param_name == 'prompt' and 'text' in user_inputs:
                    raw_params['prompt'] = user_inputs['text']
                elif param_name == 'model':
                    # Используем model_id из schema как default
                    raw_params['model'] = model_schema.get('model_id')

        # Wrap parameters into the V3 createTask format to avoid 422 "input cannot be null"
        payload = {
            'model': api_endpoint,
            'input': raw_params,
        }

        # Validate using synthetic schema derived from parameters
        synthetic_schema = {
            'input_schema': {
                'type': 'object',
                'properties': parameters_schema,
                'required': [k for k, v in parameters_schema.items() if v.get('required')],
            }
        }

        validate_payload_before_create_task(model_id, payload, synthetic_schema)
        logger.info(f"V7 payload for {model_id}: {payload}")
        return payload
    
    else:
        # V6: Old format with api_endpoint and input_schema
        input_schema = model_schema.get('input_schema', {})
        
        # КРИТИЧНО: Проверяем формат schema
        # ПРЯМОЙ формат (veo3_fast, V4): {prompt: {...}, imageUrls: {...}, customMode: {...}}
        # Если НЕТ поля 'input', значит это ПРЯМОЙ формат
        has_input_wrapper = 'input' in input_schema and isinstance(input_schema['input'], dict)
        
        # ВАЖНО: Если schema имеет структуру {model: {...}, callBackUrl: {...}, input: {type: dict, examples: [...]}}
        # то реальные user fields находятся в examples первого примера для 'input' поля
        if has_input_wrapper:
            input_field_spec = input_schema['input']
            
            # ВАРИАНТ 1: input имеет properties (вложенная schema) — как у sora-2-pro-storyboard
            if 'properties' in input_field_spec and isinstance(input_field_spec['properties'], dict):
                input_schema = input_field_spec['properties']
                logger.debug(f"Extracted input schema from properties for {model_id}: {list(input_schema.keys())}")
            
            # ВАРИАНТ 2: input имеет examples (большинство моделей)
            elif 'examples' in input_field_spec and isinstance(input_field_spec['examples'], list):
                # Это описание поля - examples показывают структуру user inputs
                examples = input_field_spec['examples']
                if examples and isinstance(examples[0], dict):
                    # Первый example показывает какие поля должны быть в user_inputs
                    # Преобразуем пример в schema-подобную структуру
                    example_structure = examples[0]
                    
                    # Создаем schema из примера
                    input_schema = {}
                    for field_name, field_value in example_structure.items():
                        # Определяем тип по значению
                        # ВАЖНО: bool проверяется FIRST, т.к. bool является подклассом int в Python
                        if isinstance(field_value, bool):
                            field_type = 'boolean'
                        elif isinstance(field_value, str):
                            field_type = 'string'
                        elif isinstance(field_value, (int, float)):
                            field_type = 'number'
                        elif isinstance(field_value, dict):
                            field_type = 'object'
                        elif isinstance(field_value, list):
                            field_type = 'array'
                        else:
                            field_type = 'string'
                        
                        input_schema[field_name] = {
                            'type': field_type,
                            'required': False  # Консервативно
                        }
                    
                    # Для prompt делаем required если он есть
                    if 'prompt' in input_schema:
                        input_schema['prompt']['required'] = True
                    
                    logger.debug(f"Extracted input schema from examples for {model_id}: {list(input_schema.keys())}")
        # КРИТИЧНО: Определяем формат payload
        # ПРЯМОЙ формат: параметры на верхнем уровне, БЕЗ input wrapper
        # ОБЫЧНЫЙ формат: параметры в input wrapper
        #
        # ВАЖНО: "direct" допустим только если schema действительно плоская:
        # {"field": {"type": "...", "required": true}, ...}
        schema_is_dict = isinstance(input_schema, dict)
        schema_keys = set(input_schema.keys()) if schema_is_dict else set()
        looks_nested = schema_is_dict and bool(schema_keys & {"properties", "required", "optional"})
        looks_flat_fields = schema_is_dict and input_schema and all(isinstance(v, dict) for v in input_schema.values())

        # Respect explicit payload_format when present in the source of truth.
        payload_format_hint = str(model_schema.get("payload_format") or "").lower()
        force_direct = payload_format_hint == "direct"
        if force_direct and has_input_wrapper:
            logger.warning(
                "payload_format=direct but schema has input wrapper; falling back to wrapped format | model=%s",
                model_id,
            )
            force_direct = False

        is_direct_format = force_direct or ((not has_input_wrapper) and looks_flat_fields and not looks_nested)

        # Kie createTask requires input wrapper for V3. Treat 'direct' as flat input fields, not root-level payload.
        is_direct_format = False

        # CRITICAL: Use api_endpoint for Kie.ai API (not model_id)
        api_endpoint = model_schema.get('api_endpoint', model_id)
        
        # Build payload for Kie createTask.
        #
        # IMPORTANT: Kie Market unified createTask expects an 'input' object for V3 models:
        #   {"model": "<model>", "input": {...}, "callBackUrl": "..."}
        # Even if the source-of-truth marks payload_format=direct, that refers to how the
        # model's user fields are represented (flat properties), not that they belong at
        # the payload root. Root-level user fields cause Kie to return 422 (input cannot be null).
        payload: Dict[str, Any] = {
            'model': api_endpoint,  # Use endpoint/model name for Kie
            'input': {},            # All user fields go under 'input'
        }
        if payload_format_hint in {"direct", "flat"}:
            logger.info(f"Using WRAPPED format for {model_id} (payload_format={payload_format_hint} -> input wrapper required)")
        else:
            logger.info(f"Using WRAPPED format for {model_id} (input wrapper)")

        # From this point on, we always populate payload['input'] (never root fields) for V3.
        input_container = payload['input']
    
    # Parse input_schema: support BOTH flat and nested formats
    # FLAT format (source_of_truth.json): {"field": {"type": "...", "required": true}}
    # NESTED format (old): {"required": [...], "properties": {...}}
    
    # ВАЖНО: Системные поля добавляются автоматически, НЕ требуются от user
    SYSTEM_FIELDS = {'model', 'callBackUrl', 'callback', 'callback_url', 'webhookUrl', 'webhook_url'}
    
    # КРИТИЧНО: Для ПРЯМОГО формата (veo3_fast, V4) поля НЕ фильтруются
    # т.к. они УЖЕ на верхнем уровне и являются обязательными
    if is_direct_format:
        # Direct format: fields live at the payload root (no input wrapper)
        if isinstance(input_schema, dict) and 'properties' in input_schema:
            required_fields = input_schema.get('required', [])
            properties = input_schema.get('properties', {}) or {}
            optional_fields = [k for k in properties.keys() if k not in required_fields]
        else:
            properties = input_schema
            required_fields = [k for k, v in properties.items() if v.get('required', False)]
            optional_fields = [k for k in properties.keys() if k not in required_fields]

        # Filter system fields for most direct models.
        # (Keep legacy behavior for veo3_fast/V4 where system fields are part of the contract.)
        if model_id not in {'veo3_fast', 'V4'}:
            required_fields = [f for f in required_fields if f not in SYSTEM_FIELDS]
            optional_fields = [f for f in optional_fields if f not in SYSTEM_FIELDS]
            properties = {k: v for k, v in properties.items() if k not in SYSTEM_FIELDS}

        logger.debug(f"Direct format: {len(required_fields)} required, {len(optional_fields)} optional")
    elif 'properties' in input_schema:
        # Nested format
        required_fields = input_schema.get('required', [])
        properties = input_schema.get('properties', {})
        # Calculate optional fields as difference
        optional_fields = [k for k in properties.keys() if k not in required_fields]
        
        # ФИЛЬТРУЕМ системные поля
        required_fields = [f for f in required_fields if f not in SYSTEM_FIELDS]
        optional_fields = [f for f in optional_fields if f not in SYSTEM_FIELDS]
        properties = {k: v for k, v in properties.items() if k not in SYSTEM_FIELDS}
    else:
        # Flat format - convert to nested
        properties = input_schema
        required_fields = [k for k, v in properties.items() if v.get('required', False)]
        optional_fields = [k for k in properties.keys() if k not in required_fields]
        
        # ФИЛЬТРУЕМ системные поля
        required_fields = [f for f in required_fields if f not in SYSTEM_FIELDS]
        optional_fields = [f for f in optional_fields if f not in SYSTEM_FIELDS]
        properties = {k: v for k, v in properties.items() if k not in SYSTEM_FIELDS}
    
    # If no properties, use FALLBACK logic
    if not properties:
        logger.warning(f"No input_schema for {model_id}, using fallback")
        # FALLBACK logic (keep for backward compatibility)
        category = model_schema.get('category', '')
        
        # Try to find prompt/text in user_inputs
        prompt_value = user_inputs.get('prompt') or user_inputs.get('text')
        url_value = user_inputs.get('url') or user_inputs.get('image_url') or user_inputs.get('video_url') or user_inputs.get('audio_url')
        file_value = user_inputs.get('file') or user_inputs.get('file_id')
        
        # Text-to-X models: need prompt
        if category in ['t2i', 't2v', 'tts', 'music', 'sfx', 'text-to-image', 'text-to-video'] or 'text' in model_id.lower():
            if prompt_value:
                input_container['prompt'] = prompt_value
            else:
                raise ValueError(f"Model {model_id} requires 'prompt' or 'text' field")
        
        # Image/Video input models: need url or file
        elif category in ['i2v', 'i2i', 'v2v', 'lip_sync', 'upscale', 'bg_remove', 'watermark_remove']:
            if url_value:
                # Determine correct field name based on category
                if 'image' in category or category in ['i2v', 'i2i', 'upscale', 'bg_remove']:
                    input_container['image_url'] = url_value
                elif 'video' in category or category == 'v2v':
                    input_container['video_url'] = url_value
                else:
                    input_container['source_url'] = url_value
            elif file_value:
                input_container['file_id'] = file_value
            else:
                raise ValueError(f"Model {model_id} (category: {category}) requires 'url' or 'file' field")
            
            # Optional prompt for guided processing
            if prompt_value:
                input_container['prompt'] = prompt_value
        
        # Audio models
        elif category in ['stt', 'audio_isolation']:
            if url_value:
                input_container['audio_url'] = url_value
            elif file_value:
                input_container['file_id'] = file_value
            else:
                raise ValueError(f"Model {model_id} (category: {category}) requires audio file or URL")
        
        # Unknown category: try to accept anything user provided
        else:
            logger.warning(f"Unknown category '{category}' for {model_id}, accepting all user inputs")
            for key, value in user_inputs.items():
                if value is not None:
                    input_container[key] = value
        
        return payload
    
    # Process required fields
    for field_name in required_fields:
        field_spec = properties.get(field_name, {})
        field_type = field_spec.get('type', 'string')

        # Get value from user_inputs
        value = user_inputs.get(field_name)

        # Schema default fallback (e.g., aspect_ratio)
        if value is None and field_spec.get('default') is not None:
            value = field_spec.get('default')
        
        # If not provided, try common aliases
        if value is None:
            # Common field mappings
            if field_name in ['prompt', 'text', 'input', 'message']:
                value = user_inputs.get('text') or user_inputs.get('prompt') or user_inputs.get('input')
            elif field_name in ['url', 'link', 'source_url', 'image_url', 'image', 'video_url', 'audio_url']:
                value = (
                    user_inputs.get('url')
                    or user_inputs.get('link')
                    or user_inputs.get('image_url')
                    or user_inputs.get('image')
                    or user_inputs.get('video_url')
                    or user_inputs.get('audio_url')
                )
            elif field_name in ['file', 'file_id', 'file_url']:
                value = user_inputs.get('file') or user_inputs.get('file_id') or user_inputs.get('file_url')
        
        # Validate and set value
        if value is None:
            # Для ПРЯМОГО формата: разрешаем skip системных полей (они добавятся позже)
            if is_direct_format and field_name in {'model', 'callBackUrl'}:
                continue  # Skip, будет добавлено автоматически
            
            # КРИТИЧНО: Smart defaults для veo3_fast и V4
            # Эти модели имеют много required полей, но большинство имеют разумные defaults
            elif model_id == 'veo3_fast':
                # veo3_fast defaults
                defaults = {
                    'imageUrls': [],
                    'watermark': False,
                    'aspectRatio': '16:9',
                    'seeds': [1],
                    'enableFallback': True,
                    'enableTranslation': False,
                    'generationType': 'prediction'
                }
                if field_name in defaults:
                    value = defaults[field_name]
                    logger.debug(f"Using default for veo3_fast.{field_name}: {value}")
                elif field_name in required_fields:
                    raise ValueError(f"Required field '{field_name}' is missing")
            
            elif model_id == 'V4':
                # V4 defaults
                defaults = {
                    'instrumental': False,
                    'customMode': False,
                    'style': '',
                    'title': '',
                    'negativeTags': '',
                    'vocalGender': 'male',
                    'styleWeight': 1.0,
                    'weirdnessConstraint': 1.0,
                    'audioWeight': 1.0,
                    'personaId': ''
                }
                if field_name in defaults:
                    value = defaults[field_name]
                    logger.debug(f"Using default for V4.{field_name}: {value}")
                elif field_name in required_fields:
                    raise ValueError(f"Required field '{field_name}' is missing")
            
            # Other required fields: raise error
            elif field_name in required_fields:
                raise ValueError(f"Required field '{field_name}' is missing")
        
        # Apply value to payload (if we have one after defaults/aliases)
        if value is not None:
            # Type conversion if needed
            # ВАЖНО: Проверяем boolean FIRST, т.к. bool является подклассом int в Python
            if field_type == 'boolean' or field_type == 'bool':
                if isinstance(value, str):
                    value = value.lower() in ('true', '1', 'yes', 'on')
                elif isinstance(value, bool):
                    # Already boolean, keep as is
                    pass
                else:
                    value = bool(value)
            elif field_type in ['array', 'list']:
                # Keep lists/arrays as-is
                if not isinstance(value, list):
                    value = [value]  # Wrap single value in list
            elif field_type == 'integer' or field_type == 'int':
                if not isinstance(value, (list, dict)):  # Don't convert complex types
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        raise ValueError(f"Field '{field_name}' must be an integer")
            elif field_type == 'number' or field_type == 'float':
                if not isinstance(value, (list, dict)):  # Don't convert complex types
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        raise ValueError(f"Field '{field_name}' must be a number")
            
            input_container[field_name] = value
    
    # Process optional fields
    for field_name in optional_fields:
        field_spec = properties.get(field_name, {})
        field_type = field_spec.get('type', 'string')
        
        value = user_inputs.get(field_name)
        if value is not None:
            # Type conversion
            # ВАЖНО: Проверяем boolean FIRST, т.к. bool является подклассом int в Python
            if field_type == 'boolean' or field_type == 'bool':
                if isinstance(value, str):
                    value = value.lower() in ('true', '1', 'yes', 'on')
                elif isinstance(value, bool):
                    # Already boolean, keep as is
                    pass
                else:
                    value = bool(value)
            elif field_type == 'integer' or field_type == 'int':
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    continue  # Skip invalid values
            elif field_type == 'number' or field_type == 'float':
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    continue
            
            input_container[field_name] = value
    

    # Fill schema defaults (aspect_ratio, duration, etc.) when present.
    # This keeps wizard lean but matches real Kie contract.
    try:
        schema_for_defaults = {'properties': properties} if isinstance(properties, dict) else {}
        payload['input'] = _apply_schema_defaults(payload.get('input') or {}, schema_for_defaults)
    except Exception:
        logger.debug("Failed to apply schema defaults", exc_info=True)



    # FREE tier invariant: recraft/remove-background requires `image` (URL) as the primary field.
    # Keep `image_url` for schema compatibility but mirror into `image` to satisfy Kie contract/tests.
    if model_id == "recraft/remove-background":
        image_value = payload['input'].get('image') or payload['input'].get('image_url')
        if image_value:
            payload['input'].setdefault('image_url', image_value)
            payload['input']['image'] = image_value

    validate_payload_before_create_task(model_id, payload, model_schema)
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
