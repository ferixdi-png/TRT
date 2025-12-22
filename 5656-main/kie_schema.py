"""
KIE input schema validation
"""

import yaml
import logging
from typing import Dict, List, Any, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_input(
    model_id: str,
    input_dict: Dict[str, Any],
    catalog_yaml_path: str = "models/catalog.yaml"
) -> Tuple[bool, List[str]]:
    """
    Validate input parameters against schema.
    
    Args:
        model_id: Model ID (e.g., "wan/2-6-text-to-video")
        input_dict: Input parameters to validate
        catalog_yaml_path: Path to catalog.yaml
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    catalog_path = Path(catalog_yaml_path)
    
    # Load catalog
    if not catalog_path.exists():
        logger.warning(f"Catalog not found: {catalog_path}, skipping validation")
        return True, []  # Don't fail if catalog missing
    
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load catalog: {e}, skipping validation")
        return True, []
    
    models = catalog.get("models", {})
    if model_id not in models:
        logger.warning(f"Model {model_id} not in catalog, using basic validation")
        # Fallback to basic validation for WAN models
        return _validate_basic_wan(input_dict, errors)
    
    schema = models[model_id].get("input_schema", {})
    if schema.get("unsupported"):
        logger.warning(f"Model {model_id} has unsupported schema, using basic validation")
        return _validate_basic_wan(input_dict, errors)
    
    # Validate each field
    for field_name, field_spec in schema.items():
        field_value = input_dict.get(field_name)
        field_errors = _validate_field(field_name, field_value, field_spec)
        errors.extend(field_errors)
    
    # Check required fields
    for field_name, field_spec in schema.items():
        if field_spec.get("required", False):
            if field_name not in input_dict or input_dict[field_name] is None:
                errors.append(f"Required field '{field_name}' is missing")
    
    return len(errors) == 0, errors


def _validate_field(field_name: str, field_value: Any, field_spec: Dict[str, Any]) -> List[str]:
    """Validate a single field"""
    errors = []
    
    # Skip if field not provided and not required
    if field_value is None:
        return errors
    
    field_type = field_spec.get("type", "string")
    
    # Type-specific validation
    if field_type == "string":
        if not isinstance(field_value, str):
            errors.append(f"'{field_name}' must be a string, got {type(field_value).__name__}")
        else:
            max_len = field_spec.get("max_len") or field_spec.get("max_length")
            if max_len and len(field_value) > max_len:
                errors.append(f"'{field_name}' exceeds max length {max_len} (got {len(field_value)})")
            
            min_len = field_spec.get("min_len") or field_spec.get("min_length")
            if min_len and len(field_value) < min_len:
                errors.append(f"'{field_name}' is shorter than min length {min_len} (got {len(field_value)})")
            
            # Check enum
            enum_values = field_spec.get("values") or field_spec.get("enum")
            if enum_values and field_value not in enum_values:
                errors.append(f"'{field_name}' must be one of {enum_values}, got '{field_value}'")
    
    elif field_type == "number":
        if not isinstance(field_value, (int, float)):
            errors.append(f"'{field_name}' must be a number, got {type(field_value).__name__}")
        else:
            min_val = field_spec.get("min")
            if min_val is not None and field_value < min_val:
                errors.append(f"'{field_name}' must be >= {min_val}, got {field_value}")
            max_val = field_spec.get("max")
            if max_val is not None and field_value > max_val:
                errors.append(f"'{field_name}' must be <= {max_val}, got {field_value}")
    
    elif field_type == "bool":
        if not isinstance(field_value, bool):
            errors.append(f"'{field_name}' must be a boolean, got {type(field_value).__name__}")
    
    elif field_type == "array_url":
        if not isinstance(field_value, list):
            errors.append(f"'{field_name}' must be a list, got {type(field_value).__name__}")
        else:
            max_items = field_spec.get("max_items") or field_spec.get("maxItems")
            if max_items and len(field_value) > max_items:
                errors.append(f"'{field_name}' must have at most {max_items} items, got {len(field_value)}")
            
            min_items = field_spec.get("min_items") or field_spec.get("minItems")
            if min_items and len(field_value) < min_items:
                errors.append(f"'{field_name}' must have at least {min_items} items, got {len(field_value)}")
            
            # Validate URLs
            for idx, url in enumerate(field_value):
                if not isinstance(url, str):
                    errors.append(f"'{field_name}[{idx}]' must be a string URL, got {type(url).__name__}")
                elif not (url.startswith("http://") or url.startswith("https://")):
                    errors.append(f"'{field_name}[{idx}]' must be a valid HTTP/HTTPS URL, got '{url[:50]}...'")
    
    return errors


def _validate_basic_wan(input_dict: Dict[str, Any], errors: List[str]) -> Tuple[bool, List[str]]:
    """Basic validation for WAN models (fallback)"""
    # Required: prompt
    if "prompt" not in input_dict or not input_dict["prompt"]:
        errors.append("'prompt' is required")
    elif len(input_dict["prompt"]) > 5000:
        errors.append(f"'prompt' exceeds max length 5000 (got {len(input_dict['prompt'])})")
    
    # Optional: duration
    if "duration" in input_dict:
        duration = input_dict["duration"]
        if isinstance(duration, str):
            if duration not in ("5", "10", "15"):
                errors.append(f"'duration' must be one of ['5', '10', '15'], got '{duration}'")
        else:
            errors.append(f"'duration' must be a string, got {type(duration).__name__}")
    
    # Optional: resolution
    if "resolution" in input_dict:
        resolution = input_dict["resolution"]
        if isinstance(resolution, str):
            if resolution not in ("720p", "1080p"):
                errors.append(f"'resolution' must be one of ['720p', '1080p'], got '{resolution}'")
        else:
            errors.append(f"'resolution' must be a string, got {type(resolution).__name__}")
    
    # Optional: image_urls
    if "image_urls" in input_dict:
        image_urls = input_dict["image_urls"]
        if not isinstance(image_urls, list):
            errors.append(f"'image_urls' must be a list, got {type(image_urls).__name__}")
        elif len(image_urls) > 1:
            errors.append(f"'image_urls' must have at most 1 item, got {len(image_urls)}")
        else:
            for idx, url in enumerate(image_urls):
                if not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
                    errors.append(f"'image_urls[{idx}]' must be a valid HTTP/HTTPS URL")
    
    # Optional: video_urls
    if "video_urls" in input_dict:
        video_urls = input_dict["video_urls"]
        if not isinstance(video_urls, list):
            errors.append(f"'video_urls' must be a list, got {type(video_urls).__name__}")
        elif len(video_urls) > 1:
            errors.append(f"'video_urls' must have at most 1 item, got {len(video_urls)}")
        else:
            for idx, url in enumerate(video_urls):
                if not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):
                    errors.append(f"'video_urls[{idx}]' must be a valid HTTP/HTTPS URL")
    
    return len(errors) == 0, errors
