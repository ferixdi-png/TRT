"""
Strict model contract validator.
Ensures impossible to reach createTask with invalid data.
"""
import logging
from typing import Dict, Any, Optional, List, Set
import re

logger = logging.getLogger(__name__)


class ModelContractError(Exception):
    """Raised when model contract is violated."""
    pass


def validate_input_type(value: Any, expected_type: str, field_name: str, is_required: bool = True) -> None:
    """
    Validate input type matches expected type.
    
    Args:
        value: Value to validate
        expected_type: Expected type string
        field_name: Field name for error messages
        is_required: Whether this is a required field (affects empty string validation)
    
    Raises:
        ModelContractError: If type mismatch
    """
    if expected_type in ['file', 'file_id', 'file_url']:
        # File type: must be string (file_id or URL)
        if not isinstance(value, str):
            raise ModelContractError(
                f"Field '{field_name}' requires file (file_id or URL), "
                f"got {type(value).__name__}"
            )
        # Check if it's a valid file identifier or URL
        if not (value.startswith('http://') or value.startswith('https://') or len(value) > 10):
            raise ModelContractError(
                f"Field '{field_name}' requires valid file_id or file URL"
            )
    
    elif expected_type in ['url', 'link', 'source_url']:
        # URL type: must be valid HTTP/HTTPS URL
        if not isinstance(value, str):
            raise ModelContractError(
                f"Field '{field_name}' requires URL, got {type(value).__name__}"
            )
        if not (value.startswith('http://') or value.startswith('https://')):
            raise ModelContractError(
                f"Field '{field_name}' requires valid URL (http:// or https://)"
            )
    
    elif expected_type in ['text', 'string', 'prompt', 'input', 'message']:
        # Text type: must be string, optionally non-empty
        if not isinstance(value, str):
            raise ModelContractError(
                f"Field '{field_name}' requires text, got {type(value).__name__}"
            )
        # ВАЖНО: Для опциональных полей разрешаем пустые строки
        # (примеры из Kie.ai могут содержать пустые negative_prompt и т.д.)
        if is_required and not value.strip():
            raise ModelContractError(
                f"Field '{field_name}' requires non-empty text"
            )
    
    elif expected_type in ['integer', 'int']:
        # Integer type
        if not isinstance(value, (int, str)):
            raise ModelContractError(
                f"Field '{field_name}' requires integer, got {type(value).__name__}"
            )
        try:
            int(value)
        except (ValueError, TypeError):
            raise ModelContractError(
                f"Field '{field_name}' must be a valid integer"
            )
    
    elif expected_type in ['number', 'float']:
        # Number type
        if not isinstance(value, (int, float, str)):
            raise ModelContractError(
                f"Field '{field_name}' requires number, got {type(value).__name__}"
            )
        try:
            float(value)
        except (ValueError, TypeError):
            raise ModelContractError(
                f"Field '{field_name}' must be a valid number"
            )
    
    elif expected_type in ['boolean', 'bool']:
        # Boolean type
        if not isinstance(value, (bool, str, int)):
            raise ModelContractError(
                f"Field '{field_name}' requires boolean, got {type(value).__name__}"
            )


def validate_model_inputs(
    model_id: str,
    model_schema: Dict[str, Any],
    user_inputs: Dict[str, Any]
) -> None:
    """
    Strictly validate user inputs against model schema.
    
    Contract:
    - Model MUST accept the provided input types
    - File-requiring models MUST NOT accept text
    - URL-requiring models MUST NOT accept file uploads
    - Required fields MUST be present
    
    Raises:
        ModelContractError: If contract is violated
    """
    # СИСТЕМНЫЕ ПОЛЯ - добавляются автоматически builder'ом, НЕ требуются от юзера
    SYSTEM_FIELDS = {'model', 'callBackUrl', 'callback', 'callback_url', 'webhookUrl', 'webhook_url'}
    
    input_schema = model_schema.get('input_schema', {})
    
    # ВАЖНО: Если schema имеет структуру {model: {...}, callBackUrl: {...}, input: {type: dict, examples: [...]}}
    # то реальные user fields находятся внутри examples первого примера для 'input' поля
    if 'input' in input_schema and isinstance(input_schema['input'], dict):
        input_field_spec = input_schema['input']
        
        # ВАРИАНТ 1: input имеет properties (вложенная schema) - например sora-2-pro-storyboard
        if 'properties' in input_field_spec:
            input_schema = input_field_spec['properties']
            logger.debug(f"Extracted input schema from properties for {model_id}: {list(input_schema.keys())}")
        
        # ВАРИАНТ 2: input имеет examples (описание поля) - большинство моделей
        elif 'examples' in input_field_spec and isinstance(input_field_spec['examples'], list):
            # Это описание поля - examples показывают структуру user inputs
            examples = input_field_spec['examples']
            if examples and isinstance(examples[0], dict):
                # Первый example показывает какие поля должны быть в user_inputs
                # Преобразуем пример в schema-подобную структуру
                example_structure = examples[0]
                
                # Создаем schema из примера: каждое поле становится опциональным
                # (т.к. мы не знаем какие ТОЧНО required без доп. анализа)
                input_schema = {}
                for field_name, field_value in example_structure.items():
                    # Определяем тип по значению
                    if isinstance(field_value, str):
                        field_type = 'string'
                    elif isinstance(field_value, (int, float)):
                        field_type = 'number'
                    elif isinstance(field_value, bool):
                        field_type = 'boolean'
                    elif isinstance(field_value, dict):
                        field_type = 'object'
                    elif isinstance(field_value, list):
                        field_type = 'array'
                    else:
                        field_type = 'string'
                    
                    input_schema[field_name] = {
                        'type': field_type,
                        'required': False  # Консервативно - делаем все опциональными
                    }
                
                # ВАЖНО: Для prompt делаем required ТОЛЬКО если он НЕ пустой в примере
                # Пустой prompt в примере = optional field
                if 'prompt' in input_schema:
                    prompt_value = example_structure.get('prompt', '')
                    if isinstance(prompt_value, str) and prompt_value.strip():
                        # Только НЕ пустые промпты делаем required
                        input_schema['prompt']['required'] = True
                    # Иначе остается optional (False)
                
                logger.debug(f"Extracted input schema from examples for {model_id}: {list(input_schema.keys())}")
    
    # Support BOTH flat and nested formats
    if 'properties' in input_schema:
        # Nested format
        properties = input_schema.get('properties', {})
        required_fields = input_schema.get('required', [])
        optional_fields = input_schema.get('optional', [])
    else:
        # Flat format - convert
        properties = input_schema
        required_fields = [k for k, v in properties.items() if v.get('required', False)]
        optional_fields = [k for k in properties.keys() if k not in required_fields]
    
    # ФИЛЬТРУЕМ системные поля - они НЕ валидируются для user_inputs
    # КРИТИЧНО: Для ПРЯМЫХ моделей (veo3_fast, V4) ТОЛЬКО prompt is required
    # Все остальные поля будут заполнены builder'ом defaults
    is_direct_model = model_id in ['veo3_fast', 'V4']
    
    if is_direct_model:
        # Для ПРЯМЫХ моделей: только prompt required, остальное - optional
        logger.info(f"Direct model {model_id}: treating all fields as optional except 'prompt'")
        real_required = ['prompt']  # ТОЛЬКО prompt
        all_other_fields = [f for f in list(properties.keys()) if f != 'prompt']
        required_fields = real_required
        optional_fields = all_other_fields
    else:
        # Обычные модели: фильтруем только системные поля
        required_fields = [f for f in required_fields if f not in SYSTEM_FIELDS]
        optional_fields = [f for f in optional_fields if f not in SYSTEM_FIELDS]
    properties = {k: v for k, v in properties.items() if k not in SYSTEM_FIELDS}
    
    # FALLBACK: If no properties defined in schema, validate based on category
    if not properties:
        logger.info(f"Using fallback validation for {model_id} (no schema properties)")
        
        category = model_schema.get('category', '')
        
        # Get available inputs
        has_prompt = bool(user_inputs.get('prompt') or user_inputs.get('text'))
        has_url = bool(user_inputs.get('url') or user_inputs.get('image_url') or 
                      user_inputs.get('video_url') or user_inputs.get('audio_url'))
        has_file = bool(user_inputs.get('file') or user_inputs.get('file_id'))
        
        # Text-based models require prompt
        if category in ['t2i', 't2v', 'tts', 'music', 'sfx'] or 'text' in model_id.lower():
            if not has_prompt:
                raise ModelContractError(
                    f"Text-based model {model_id} requires 'prompt' or 'text' field"
                )
        
        # Media input models require url or file
        elif category in ['i2v', 'i2i', 'v2v', 'lip_sync', 'upscale', 'bg_remove', 
                         'watermark_remove', 'stt', 'audio_isolation']:
            if not has_url and not has_file:
                raise ModelContractError(
                    f"Media model {model_id} requires URL or file input"
                )
        
        # Unknown category: accept if any input provided
        else:
            if not user_inputs or all(v is None for v in user_inputs.values()):
                raise ModelContractError(
                    f"Model {model_id} requires at least one input"
                )
        
        # Fallback validation passed
        return
    
    # Schema-based validation: check required fields
    all_fields = set(required_fields) | set(optional_fields)
    
    # Check required fields
    for field_name in required_fields:
        if field_name not in user_inputs:
            # Try common aliases
            value = None
            field_spec = properties.get(field_name, {})
            field_type = field_spec.get('type', 'string')
            
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

            if value is None:
                if field_spec.get('default') is not None:
                    continue
                raise ModelContractError(
                        f"Model {model_id} requires field '{field_name}' (type: {field_type}), "
                        f"but it is missing from user inputs"
                    )
    
    # Validate field types and constraints
    for field_name in all_fields:
        field_spec = properties.get(field_name, {})
        field_type = field_spec.get('type', 'string')
        
        # Get value (with alias resolution)
        value = user_inputs.get(field_name)
        if value is None:
            # Try aliases
            if field_name in ['prompt', 'text', 'input', 'message']:
                value = user_inputs.get('text') or user_inputs.get('prompt') or user_inputs.get('input')
            elif field_name in ['url', 'link', 'source_url', 'image_url', 'video_url', 'audio_url']:
                value = (user_inputs.get('url') or user_inputs.get('link') or 
                        user_inputs.get('image_url') or user_inputs.get('video_url') or 
                        user_inputs.get('audio_url'))
            elif field_name in ['file', 'file_id', 'file_url']:
                value = user_inputs.get('file') or user_inputs.get('file_id') or user_inputs.get('file_url')
        
        # Skip validation if field is optional and not provided
        if value is None and field_name in optional_fields:
            continue
        
        # Validate type
        if value is not None:
            # Определяем: required или optional
            is_required = field_name in required_fields
            validate_input_type(value, field_type, field_name, is_required=is_required)
            
            # Check enum constraints
            if 'enum' in field_spec:
                enum_values = field_spec['enum']
                if value not in enum_values:
                    raise ModelContractError(
                        f"Field '{field_name}' must be one of {enum_values}, got '{value}'"
                    )
            
            # Check min/max constraints
            if 'minimum' in field_spec:
                try:
                    num_value = float(value)
                    if num_value < field_spec['minimum']:
                        raise ModelContractError(
                            f"Field '{field_name}' must be >= {field_spec['minimum']}, got {num_value}"
                        )
                except (ValueError, TypeError):
                    pass  # Type validation will catch this
            
            if 'maximum' in field_spec:
                try:
                    num_value = float(value)
                    if num_value > field_spec['maximum']:
                        raise ModelContractError(
                            f"Field '{field_name}' must be <= {field_spec['maximum']}, got {num_value}"
                        )
                except (ValueError, TypeError):
                    pass  # Type validation will catch this
    
    # Cross-field validation: file vs text vs URL
    # If model requires file, reject text/URL
    file_fields = [f for f in all_fields 
                   if properties.get(f, {}).get('type') in ['file', 'file_id', 'file_url']]
    text_fields = [f for f in all_fields 
                   if properties.get(f, {}).get('type') in ['text', 'string', 'prompt', 'input', 'message']]
    url_fields = [f for f in all_fields 
                  if properties.get(f, {}).get('type') in ['url', 'link', 'source_url']]
    
    # Check for type conflicts
    has_file_input = any(
        user_inputs.get(f) or 
        user_inputs.get('file') or 
        user_inputs.get('file_id') or 
        user_inputs.get('file_url')
        for f in file_fields
    )
    
    has_text_input = any(
        user_inputs.get(f) or 
        user_inputs.get('text') or 
        user_inputs.get('prompt') or 
        user_inputs.get('input')
        for f in text_fields
    )
    
    has_url_input = any(
        user_inputs.get(f) or 
        user_inputs.get('url') or 
        user_inputs.get('link')
        for f in url_fields
    )
    
    # If model requires file but got text/URL
    if file_fields and required_fields:
        required_file_fields = [f for f in file_fields if f in required_fields]
        if required_file_fields and not has_file_input:
            if has_text_input:
                raise ModelContractError(
                    f"Model {model_id} requires file input, but text was provided. "
                    f"Please provide a file instead."
                )
            if has_url_input:
                raise ModelContractError(
                    f"Model {model_id} requires file input, but URL was provided. "
                    f"Please provide a file instead."
                )
    
    # If model requires URL but got file
    if url_fields and required_fields:
        required_url_fields = [f for f in url_fields if f in required_fields]
        if required_url_fields and not has_url_input:
            if has_file_input:
                raise ModelContractError(
                    f"Model {model_id} requires URL input, but file was provided. "
                    f"Please provide a URL instead."
                )
    
    # If model requires text but got file/URL
    if text_fields and required_fields:
        required_text_fields = [f for f in text_fields if f in required_fields]
        if required_text_fields and not has_text_input:
            if has_file_input:
                raise ModelContractError(
                    f"Model {model_id} requires text input, but file was provided. "
                    f"Please provide text instead."
                )
            if has_url_input:
                raise ModelContractError(
                    f"Model {model_id} requires text input, but URL was provided. "
                    f"Please provide text instead."
                )


def validate_payload_before_create_task(model_id: str, payload: Dict[str, Any], model_schema: Dict[str, Any]) -> None:
    """Validate payload shape and required inputs BEFORE calling Kie createTask.

    Why this exists:
    - Kie returns generic "This field is required" errors.
    - We want deterministic, user-friendly errors + detailed logs.
    """

    SYSTEM_FIELDS: Set[str] = {'model', 'callBackUrl', 'callback', 'callback_url', 'webhookUrl', 'webhook_url'}

    if not isinstance(payload, dict):
        raise ModelContractError(f"Payload must be a dict, got {type(payload).__name__}")

    # Kie Market unified createTask expects the wrapped payload:
    #   {"model": "<model>", "input": {...}, "callBackUrl": "..."}
    # Models may be marked as payload_format=direct in the source-of-truth, but that only
    # means the *fields inside input* are flat. We still require "input" at the root.
    if 'model' not in payload:
        raise ModelContractError("Payload is missing required root field 'model'")

    if 'input' not in payload or not isinstance(payload.get('input'), dict):
        raise ModelContractError(
            "Payload is missing required field 'input' (Kie V3 createTask requires wrapped payload)"
        )

    input_data = payload['input']

    if not input_data:
        raise ModelContractError("Payload 'input' cannot be empty for createTask (wrap even for direct models)")

    # Normalize schema into properties + required list
    input_schema = (model_schema or {}).get('input_schema') or {}

    properties: Dict[str, Any] = {}
    required_fields: List[str] = []

    if isinstance(input_schema, dict) and input_schema.get('type') == 'object' and isinstance(input_schema.get('properties'), dict):
        properties = input_schema.get('properties', {})
        required_fields = list(input_schema.get('required', []) or [])
    elif isinstance(input_schema, dict) and input_schema and all(isinstance(v, dict) for v in input_schema.values()):
        # Flat schema (field specs directly)
        properties = input_schema
        required_fields = [k for k, v in properties.items() if v.get('required') is True]
    else:
        # No schema - nothing strict to validate
        properties = {}
        required_fields = []

    required_fields = [f for f in required_fields if f not in SYSTEM_FIELDS]

    missing: List[str] = []
    for f in required_fields:
        if f not in input_data:
            missing.append(f)
            continue
        v = input_data.get(f)
        if v is None:
            missing.append(f)
            continue
        if isinstance(v, str) and not v.strip():
            missing.append(f)
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            missing.append(f)
            continue

    if missing:
        raise ModelContractError(
            f"Missing required field(s): {', '.join(missing)} (model={model_id}, format=wrapped)"
        )

    # Type validation for provided fields (best-effort)
    for field_name, value in list(input_data.items()):
        if field_name in SYSTEM_FIELDS:
            continue
        spec = properties.get(field_name)
        if not isinstance(spec, dict):
            continue

        expected_type = spec.get('type')
        fmt = spec.get('format')

        # Heuristics: *_url or format=uri -> url
        if fmt == 'uri' or field_name.endswith('_url'):
            validate_input_type(value, 'url', field_name, is_required=(field_name in required_fields))
            continue

        if expected_type in {'string'}:
            validate_input_type(value, 'text', field_name, is_required=(field_name in required_fields))
        elif expected_type in {'integer'}:
            validate_input_type(value, 'integer', field_name, is_required=(field_name in required_fields))
        elif expected_type in {'number'}:
            validate_input_type(value, 'number', field_name, is_required=(field_name in required_fields))
        elif expected_type in {'boolean'}:
            validate_input_type(value, 'boolean', field_name, is_required=(field_name in required_fields))

    logger.info(
        "Payload contract ok | model=%s format=%s keys=%s",
        model_id,
        'direct' if False else 'wrapped',
        sorted(list(payload.keys())),
    )
