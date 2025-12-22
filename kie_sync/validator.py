"""
Validation module for pricing and catalog YAML files
"""

import yaml
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_pricing_config(config_path: Path) -> Dict[str, Any]:
    """
    Validate pricing configuration YAML file.
    
    Args:
        config_path: Path to pricing config file
    
    Returns:
        Dictionary with validation results: {'valid': bool, 'errors': List[str], 'warnings': List[str]}
    """
    result = {
        'valid': True,
        'errors': [],
        'warnings': []
    }
    
    if not config_path.exists():
        result['valid'] = False
        result['errors'].append(f"Config file not found: {config_path}")
        return result
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result['valid'] = False
        result['errors'].append(f"YAML parsing error: {e}")
        return result
    except Exception as e:
        result['valid'] = False
        result['errors'].append(f"File reading error: {e}")
        return result
    
    if not config:
        result['valid'] = False
        result['errors'].append("Config is empty")
        return result
    
    # Validate models section
    models = config.get('models', {})
    if not models:
        result['warnings'].append("No models found in config")
    
    for model_id, model_config in models.items():
        # Validate model structure
        if not isinstance(model_config, dict):
            result['errors'].append(f"Model {model_id}: config must be a dictionary")
            result['valid'] = False
            continue
        
        # Validate pricing type
        pricing_type = model_config.get('type')
        if not pricing_type:
            result['errors'].append(f"Model {model_id}: missing 'type' field")
            result['valid'] = False
            continue
        
        if pricing_type == 'matrix':
            # Validate matrix pricing
            axes = model_config.get('axes', [])
            table = model_config.get('table', {})
            
            if not isinstance(axes, list) or len(axes) < 2:
                result['errors'].append(f"Model {model_id}: matrix pricing requires at least 2 axes")
                result['valid'] = False
            
            if not isinstance(table, dict):
                result['errors'].append(f"Model {model_id}: matrix pricing requires 'table' dict")
                result['valid'] = False
            else:
                # Validate table structure
                for key1, subtable in table.items():
                    if not isinstance(subtable, dict):
                        result['errors'].append(f"Model {model_id}: table[{key1}] must be a dict")
                        result['valid'] = False
                    else:
                        for key2, price in subtable.items():
                            if not isinstance(price, (int, float)):
                                result['errors'].append(
                                    f"Model {model_id}: table[{key1}][{key2}] must be a number (USD), got {type(price)}"
                                )
                                result['valid'] = False
                            elif price < 0:
                                result['warnings'].append(
                                    f"Model {model_id}: table[{key1}][{key2}] has negative price: {price}"
                                )
        
        elif pricing_type == 'fixed':
            price_usd = model_config.get('price_usd')
            if price_usd is None:
                result['errors'].append(f"Model {model_id}: fixed pricing requires 'price_usd'")
                result['valid'] = False
            elif not isinstance(price_usd, (int, float)):
                result['errors'].append(f"Model {model_id}: price_usd must be a number, got {type(price_usd)}")
                result['valid'] = False
        
        elif pricing_type == 'per_second':
            price_per_sec = model_config.get('price_per_sec_usd')
            if price_per_sec is None:
                result['errors'].append(f"Model {model_id}: per_second pricing requires 'price_per_sec_usd'")
                result['valid'] = False
            elif not isinstance(price_per_sec, (int, float)):
                result['errors'].append(
                    f"Model {model_id}: price_per_sec_usd must be a number, got {type(price_per_sec)}"
                )
                result['valid'] = False
        
        else:
            result['errors'].append(f"Model {model_id}: unknown pricing type '{pricing_type}'")
            result['valid'] = False
    
    # Validate settings
    settings = config.get('settings', {})
    if settings:
        usd_to_rub = settings.get('usd_to_rub')
        if usd_to_rub is not None and not isinstance(usd_to_rub, (int, float)):
            result['errors'].append("settings.usd_to_rub must be a number")
            result['valid'] = False
        
        markup = settings.get('markup_multiplier')
        if markup is not None and not isinstance(markup, (int, float)):
            result['errors'].append("settings.markup_multiplier must be a number")
            result['valid'] = False
    
    return result


def validate_catalog_config(config_path: Path) -> Dict[str, Any]:
    """
    Validate catalog (models input schema) configuration YAML file.
    
    Args:
        config_path: Path to catalog config file
    
    Returns:
        Dictionary with validation results: {'valid': bool, 'errors': List[str], 'warnings': List[str]}
    """
    result = {
        'valid': True,
        'errors': [],
        'warnings': []
    }
    
    if not config_path.exists():
        result['valid'] = False
        result['errors'].append(f"Config file not found: {config_path}")
        return result
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result['valid'] = False
        result['errors'].append(f"YAML parsing error: {e}")
        return result
    except Exception as e:
        result['valid'] = False
        result['errors'].append(f"File reading error: {e}")
        return result
    
    if not config:
        result['valid'] = False
        result['errors'].append("Config is empty")
        return result
    
    # Validate models section
    models = config.get('models', {})
    if not models:
        result['warnings'].append("No models found in config")
    
    for model_id, model_config in models.items():
        if not isinstance(model_config, dict):
            result['errors'].append(f"Model {model_id}: config must be a dictionary")
            result['valid'] = False
            continue
        
        input_schema = model_config.get('input_schema', {})
        if not input_schema:
            result['warnings'].append(f"Model {model_id}: no input_schema defined")
            continue
        
        if not isinstance(input_schema, dict):
            result['errors'].append(f"Model {model_id}: input_schema must be a dictionary")
            result['valid'] = False
            continue
        
        # Validate each field
        for field_name, field_config in input_schema.items():
            if not isinstance(field_config, dict):
                result['errors'].append(f"Model {model_id}.{field_name}: field config must be a dictionary")
                result['valid'] = False
                continue
            
            # Validate required field
            required = field_config.get('required', False)
            if not isinstance(required, bool):
                result['errors'].append(f"Model {model_id}.{field_name}: 'required' must be boolean")
                result['valid'] = False
            
            # Validate type
            field_type = field_config.get('type')
            if not field_type:
                result['errors'].append(f"Model {model_id}.{field_name}: missing 'type' field")
                result['valid'] = False
                continue
            
            valid_types = ['string', 'enum', 'array_url', 'number', 'bool']
            if field_type not in valid_types:
                result['errors'].append(
                    f"Model {model_id}.{field_name}: invalid type '{field_type}', "
                    f"must be one of: {valid_types}"
                )
                result['valid'] = False
            
            # Type-specific validation
            if field_type == 'string':
                max_len = field_config.get('max_length')
                if max_len is not None:
                    if not isinstance(max_len, int) or max_len < 0:
                        result['errors'].append(
                            f"Model {model_id}.{field_name}: max_length must be a non-negative integer"
                        )
                        result['valid'] = False
                
                min_len = field_config.get('min_length')
                if min_len is not None:
                    if not isinstance(min_len, int) or min_len < 0:
                        result['errors'].append(
                            f"Model {model_id}.{field_name}: min_length must be a non-negative integer"
                        )
                        result['valid'] = False
            
            elif field_type == 'enum':
                enum_values = field_config.get('enum', [])
                if not isinstance(enum_values, list):
                    result['errors'].append(f"Model {model_id}.{field_name}: enum must be a list")
                    result['valid'] = False
                elif not enum_values:
                    result['errors'].append(f"Model {model_id}.{field_name}: enum list cannot be empty")
                    result['valid'] = False
                else:
                    # Check all enum values are strings
                    for i, val in enumerate(enum_values):
                        if not isinstance(val, str):
                            result['errors'].append(
                                f"Model {model_id}.{field_name}: enum[{i}] must be a string, got {type(val)}"
                            )
                            result['valid'] = False
            
            elif field_type == 'number':
                min_val = field_config.get('min')
                if min_val is not None and not isinstance(min_val, (int, float)):
                    result['errors'].append(
                        f"Model {model_id}.{field_name}: min must be a number"
                    )
                    result['valid'] = False
                
                max_val = field_config.get('max')
                if max_val is not None and not isinstance(max_val, (int, float)):
                    result['errors'].append(
                        f"Model {model_id}.{field_name}: max must be a number"
                    )
                    result['valid'] = False
            
            elif field_type == 'array_url':
                min_items = field_config.get('min_items')
                if min_items is not None:
                    if not isinstance(min_items, int) or min_items < 0:
                        result['errors'].append(
                            f"Model {model_id}.{field_name}: min_items must be a non-negative integer"
                        )
                        result['valid'] = False
                
                max_items = field_config.get('max_items')
                if max_items is not None:
                    if not isinstance(max_items, int) or max_items < 0:
                        result['errors'].append(
                            f"Model {model_id}.{field_name}: max_items must be a non-negative integer"
                        )
                        result['valid'] = False
    
    return result


def validate_all() -> Dict[str, Any]:
    """
    Validate both pricing and catalog configs.
    
    Returns:
        Combined validation results
    """
    pricing_result = validate_pricing_config(Path("pricing/config.yaml"))
    catalog_result = validate_catalog_config(Path("models/catalog.yaml"))
    
    return {
        'pricing': pricing_result,
        'catalog': catalog_result,
        'all_valid': pricing_result['valid'] and catalog_result['valid']
    }
