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
    
    # nano-banana-pro - TEXT2IMAGE with image conditioning
    # ERROR: Missing required field: image_input, aspect_ratio, resolution, output_format
    # SOURCE: models/KIE_SOURCE_OF_TRUTH.json (nano-banana-pro examples)
    "nano-banana-pro": {
        "image_input": [],              # Empty array for text-only generation
        "aspect_ratio": "1:1",          # Default from SOURCE_OF_TRUTH
        "resolution": "1K",             # Default from SOURCE_OF_TRUTH
        "output_format": "png",         # Default from SOURCE_OF_TRUTH
    },
    
    # google/nano-banana - TEXT2IMAGE
    # ERROR: Missing required field: output_format
    # ERROR: Invalid value for image_size: 1920x1080. Must be one of: portrait_hd, square_hd, landscape_hd, 1024x1024, 512x512, 1:1, portrait, square, landscape
    # SOURCE: models/KIE_SOURCE_OF_TRUTH.json example shows output_format=png, image_size=1:1
    "google/nano-banana": {
        "output_format": "png",         # Required, default from SOURCE_OF_TRUTH
        "image_size": "1:1",            # Required, default from SOURCE_OF_TRUTH
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
