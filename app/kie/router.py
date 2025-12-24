"""
API Router для новой архитектуры Kie.ai.
Маршрутизирует запросы к правильным category-specific endpoints.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Загрузка v4 source of truth
def load_v4_source_of_truth() -> Dict[str, Any]:
    """Load source of truth v4.0 with new API architecture."""
    v4_path = Path(__file__).parent.parent.parent / "models" / "kie_source_of_truth_v4.json"
    if not v4_path.exists():
        logger.warning(f"V4 source of truth not found at {v4_path}, falling back to stub")
        return {"version": "4.0.0", "models": [], "categories": {}}
    
    with open(v4_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_api_category_for_model(model_id: str, source_v4: Optional[Dict] = None) -> Optional[str]:
    """
    Determine which API category a model belongs to.
    
    Args:
        model_id: Model identifier (e.g. 'veo3', 'suno-v4', 'gpt-4o-image')
        source_v4: Optional pre-loaded v4 source of truth
    
    Returns:
        API category name ('veo3', 'suno', 'runway', etc.) or None
    """
    if source_v4 is None:
        source_v4 = load_v4_source_of_truth()
    
    models = source_v4.get('models', [])
    for model in models:
        if model.get('model_id') == model_id:
            return model.get('api_category')
    
    logger.warning(f"Model {model_id} not found in v4 source of truth")
    return None


def build_category_payload(
    model_id: str, 
    user_inputs: Dict[str, Any],
    source_v4: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Build payload for category-specific API endpoint.
    
    This is different from old universal createTask - each category
    has its own payload format.
    
    Args:
        model_id: Model ID
        user_inputs: User-provided inputs
        source_v4: Optional pre-loaded v4 source of truth
    
    Returns:
        Payload dict ready for category-specific API
    """
    if source_v4 is None:
        source_v4 = load_v4_source_of_truth()
    
    # Find model schema
    model_schema = None
    for model in source_v4.get('models', []):
        if model.get('model_id') == model_id:
            model_schema = model
            break
    
    if not model_schema:
        raise ValueError(f"Model {model_id} not found in source of truth v4")
    
    category = model_schema.get('api_category')
    input_schema = model_schema.get('input_schema', {})
    properties = input_schema.get('properties', {})
    required_fields = input_schema.get('required', [])
    
    # Build payload based on category
    payload = {}
    
    # Add required fields
    for field in required_fields:
        if field in user_inputs:
            payload[field] = user_inputs[field]
        elif field in properties and 'default' in properties[field]:
            payload[field] = properties[field]['default']
        else:
            raise ValueError(f"Required field '{field}' missing for model {model_id}")
    
    # Add optional fields if provided
    for field, field_schema in properties.items():
        if field not in required_fields and field in user_inputs:
            payload[field] = user_inputs[field]
        elif field not in payload and 'default' in field_schema:
            # Add defaults for optional fields
            payload[field] = field_schema['default']
    
    logger.info(f"Built {category} payload for {model_id}: {payload}")
    return payload


def get_api_endpoint_for_model(model_id: str, source_v4: Optional[Dict] = None) -> str:
    """
    Get the full API endpoint path for a model.
    
    Args:
        model_id: Model ID
        source_v4: Optional pre-loaded v4 source of truth
    
    Returns:
        Full endpoint path (e.g. '/veo3/text_to_video', '/suno/generate')
    """
    if source_v4 is None:
        source_v4 = load_v4_source_of_truth()
    
    for model in source_v4.get('models', []):
        if model.get('model_id') == model_id:
            return model.get('api_endpoint', '')
    
    raise ValueError(f"Model {model_id} not found in source of truth v4")


def get_base_url_for_category(category: str, source_v4: Optional[Dict] = None) -> str:
    """
    Get base URL for API category.
    
    Args:
        category: API category ('veo3', 'suno', etc.)
        source_v4: Optional pre-loaded v4 source of truth
    
    Returns:
        Base URL (typically 'https://api.kie.ai')
    """
    if source_v4 is None:
        source_v4 = load_v4_source_of_truth()
    
    categories = source_v4.get('categories', {})
    if category in categories:
        return categories[category].get('base_url', 'https://api.kie.ai')
    
    # Fallback
    return 'https://api.kie.ai'


# Compatibility helpers для старого кода
def is_v4_model(model_id: str) -> bool:
    """Check if model exists in v4 source of truth."""
    try:
        source_v4 = load_v4_source_of_truth()
        return any(m.get('model_id') == model_id for m in source_v4.get('models', []))
    except Exception as e:
        logger.error(f"Failed to check v4 model: {e}")
        return False


def get_all_v4_models() -> list:
    """Get list of all available v4 models."""
    try:
        source_v4 = load_v4_source_of_truth()
        return source_v4.get('models', [])
    except Exception as e:
        logger.error(f"Failed to load v4 models: {e}")
        return []
