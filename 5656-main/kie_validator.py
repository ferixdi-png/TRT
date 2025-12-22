"""
KIE Input Validator - validates input parameters against model schema.

This module provides validation for KIE AI model inputs based on the schema
defined in models/kie_models.yaml. It ensures that all required parameters
are present, types are correct, enum values are valid, and constraints
(min/max length, array sizes) are satisfied before sending requests to KIE API.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

MODELS_YAML_PATH = Path("models/kie_models.yaml")
_models_registry: Optional[Dict[str, Any]] = None


def load_models_registry() -> Dict[str, Any]:
    """Load models registry from YAML"""
    global _models_registry
    if _models_registry is not None:
        return _models_registry
    
    if not MODELS_YAML_PATH.exists():
        logger.error(f"Models registry not found: {MODELS_YAML_PATH}")
        return {}
    
    try:
        with open(MODELS_YAML_PATH, 'r', encoding='utf-8') as f:
            _models_registry = yaml.safe_load(f)
        return _models_registry
    except Exception as e:
        logger.error(f"Failed to load models registry: {e}", exc_info=True)
        return {}


def get_model_schema(model_id: str) -> Optional[Dict[str, Any]]:
    """Get input schema for a model"""
    registry = load_models_registry()
    model_info = registry.get('models', {}).get(model_id)
    if not model_info:
        return None
    return model_info.get('input', {})


def validate(model_id: str, input_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate input parameters against model schema.
    
    Returns:
        (is_valid, list_of_errors)
    """
    schema = get_model_schema(model_id)
    if not schema:
        # Model not found in registry - allow but warn
        logger.warning(f"Model {model_id} not found in registry, skipping validation")
        return True, []
    
    errors = []
    
    # Check required fields
    for param_name, param_schema in schema.items():
        is_required = param_schema.get('required', False)
        param_value = input_dict.get(param_name)
        
        if is_required and (param_value is None or param_value == ""):
            errors.append(f"Параметр '{param_name}' обязателен для заполнения")
            continue
        
        if param_value is None:
            continue  # Optional parameter not provided
        
        param_type = param_schema.get('type', 'string')
        
        # Type validation
        if param_type == 'string':
            if not isinstance(param_value, str):
                errors.append(f"Параметр '{param_name}' должен быть текстом")
                continue
            
            # Length validation
            if 'min' in param_schema:
                if len(param_value) < param_schema['min']:
                    errors.append(f"Параметр '{param_name}' должен содержать минимум {param_schema['min']} символов")
            if 'max' in param_schema:
                if len(param_value) > param_schema['max']:
                    errors.append(f"Параметр '{param_name}' не должен превышать {param_schema['max']} символов")
        
        elif param_type == 'enum':
            valid_values = param_schema.get('values', [])
            if param_value not in valid_values:
                valid_str = ', '.join(map(str, valid_values))
                errors.append(f"Параметр '{param_name}' должен быть одним из: {valid_str} (указано: '{param_value}')")
        
        elif param_type == 'array':
            if not isinstance(param_value, list):
                errors.append(f"Параметр '{param_name}' должен быть списком")
                continue
            
            # Check array length (usually max 1 for image_urls/video_urls)
            if 'max_items' in param_schema or param_name in ('image_urls', 'video_urls', 'video_url', 'image_url'):
                max_items = param_schema.get('max_items', 1)
                if len(param_value) > max_items:
                    errors.append(f"Параметр '{param_name}' может содержать максимум {max_items} элемент(ов) (указано: {len(param_value)})")
            
            if len(param_value) == 0 and is_required:
                errors.append(f"Параметр '{param_name}' обязателен и не может быть пустым")
                continue
            
            # Validate array items
            item_type = param_schema.get('item_type', 'string')
            if item_type == 'string':
                for idx, item in enumerate(param_value):
                    if not isinstance(item, str):
                        errors.append(f"Элемент {idx+1} параметра '{param_name}' должен быть текстом")
                        continue
                    
                    # URL validation for image/video URLs
                    if 'url' in param_name.lower():
                        if not item.startswith('http://') and not item.startswith('https://'):
                            errors.append(f"Элемент {idx+1} параметра '{param_name}' должен быть валидным URL (начинаться с http:// или https://)")
        
        elif param_type in ('number', 'integer', 'float'):
            try:
                float(param_value)
            except (ValueError, TypeError):
                errors.append(f"Параметр '{param_name}' должен быть числом")
    
    return len(errors) == 0, errors
