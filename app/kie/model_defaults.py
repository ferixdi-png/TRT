"""
Model-specific default values for optional/required parameters.
Used when user doesn't provide value via UI.

CRITICAL: These defaults ensure models can run without validation errors.
Source: KIE API error messages + SOURCE_OF_TRUTH examples.
"""
from typing import Dict, Any


# Model-specific defaults (keyed by model_id)
MODEL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # bytedance/seedream - TEXT2IMAGE
    # ERROR: Missing required field: guidance_scale
    # SOURCE: models/KIE_SOURCE_OF_TRUTH.json line 40 (guidance_scale: 2.5)
    "bytedance/seedream": {
        "guidance_scale": 2.5,
        "enable_safety_checker": False,
        "image_size": "square_hd",  # Default from SOURCE_OF_TRUTH
    },
    
    # bytedance/seedream-v4-text-to-image
    "bytedance/seedream-v4-text-to-image": {
        "image_size": "square_hd",
        "image_resolution": "2K",
        "max_images": 1,
    },
    
    # qwen models
    "qwen/text-to-image": {
        "image_size": "square_hd",
        "enable_safety_checker": False,
    },
    
    "qwen/image-edit": {
        "image_size": "square_hd",
    },
}


def get_model_defaults(model_id: str) -> Dict[str, Any]:
    """
    Get default values for model.
    
    Args:
        model_id: Model identifier (e.g., "bytedance/seedream")
        
    Returns:
        Dictionary of default values for optional fields
    """
    return MODEL_DEFAULTS.get(model_id, {}).copy()


def apply_defaults(model_id: str, user_inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply model defaults to user inputs (only for missing keys).
    
    Args:
        model_id: Model identifier
        user_inputs: User-provided inputs
        
    Returns:
        Merged dictionary (user inputs + defaults for missing keys)
    """
    defaults = get_model_defaults(model_id)
    result = defaults.copy()
    result.update(user_inputs)  # User values override defaults
    return result
