"""
Field constraints and options for KIE models.
Maps model_id.field_name to allowed options.
"""

FIELD_OPTIONS = {
    # z-image constraints
    "z-image.aspect_ratio": [
        "1:1",
        "16:9",
        "9:16",
        "4:3",
        "3:4",
    ],
    
    # Common aspect ratios for image models
    "qwen/text-to-image.image_size": [
        "256x256",
        "512x512",
        "768x768",
        "1024x1024",
    ],
    
    "qwen/image-edit.image_size": [
        "256x256",
        "512x512",
        "768x768",
        "1024x1024",
    ],
    
    "qwen/image-to-image.output_format": [
        "png",
        "jpg",
        "webp",
    ],
    
    # Video aspect ratios
    "bytedance/v1-lite-text-to-video.aspect_ratio": [
        "9:16",
        "16:9",
        "1:1",
    ],
    
    "bytedance/v1-pro-text-to-video.aspect_ratio": [
        "9:16",
        "16:9",
        "1:1",
    ],
    
    # Common model-specific constraints can be added as discovered
}

# Required fields per model
REQUIRED_FIELDS = {
    "z-image": ["prompt", "aspect_ratio"],  # Both required for z-image
    "qwen/text-to-image": ["prompt", "image_size"],
    "qwen/image-edit": ["image_url", "image_size"],
}

def get_field_options(model_id: str, field_name: str) -> list:
    """
    Get allowed options for a field.
    
    Args:
        model_id: Model identifier
        field_name: Field name
    
    Returns:
        List of allowed values, or empty list if no constraints
    """
    key = f"{model_id}.{field_name}"
    return FIELD_OPTIONS.get(key, [])

def has_field_constraints(model_id: str, field_name: str) -> bool:
    """Check if field has constraints."""
    key = f"{model_id}.{field_name}"
    return key in FIELD_OPTIONS

def get_required_fields(model_id: str) -> list:
    """
    Get list of required fields for a model.
    
    Args:
        model_id: Model identifier
    
    Returns:
        List of required field names, or empty list if none defined
    """
    return REQUIRED_FIELDS.get(model_id, [])

def validate_required_fields(model_id: str, provided_fields: dict) -> tuple[bool, str]:
    """
    Validate that all required fields are provided.
    
    Args:
        model_id: Model identifier
        provided_fields: Dict of provided field values
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    required = get_required_fields(model_id)
    if not required:
        return True, ""
    
    missing = [f for f in required if f not in provided_fields or not provided_fields[f]]
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"
    
    return True, ""
