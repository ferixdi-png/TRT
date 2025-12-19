"""
Pricing engine for calculating model prices in RUB
Supports multiple pricing types: fixed, per_second, matrix
"""

import os
import logging
import json
from typing import Dict, Any, Optional
from pathlib import Path

# Try to import yaml, fallback to json if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

# Default paths (try YAML first, fallback to JSON)
DEFAULT_CONFIG_PATH_YAML = Path(__file__).parent / "config.yaml"
DEFAULT_CONFIG_PATH_JSON = Path(__file__).parent / "config.json"

# Global settings
USD_TO_RUB = 77.2222  # 1 USD = 77.2222 RUB (calculated from 6.95 / 0.09)
MARKUP_MULTIPLIER = 2.0  # Multiplier for regular users


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load pricing configuration from YAML or JSON file.
    
    Args:
        config_path: Path to config file (default: tries config.yaml, then config.json)
    
    Returns:
        Dictionary with pricing configuration
    """
    if config_path is None:
        # Try YAML first, then JSON
        if YAML_AVAILABLE and DEFAULT_CONFIG_PATH_YAML.exists():
            config_path = DEFAULT_CONFIG_PATH_YAML
        elif DEFAULT_CONFIG_PATH_JSON.exists():
            config_path = DEFAULT_CONFIG_PATH_JSON
        else:
            logger.warning(f"Config file not found: {DEFAULT_CONFIG_PATH_YAML} or {DEFAULT_CONFIG_PATH_JSON}, using defaults")
            return {"models": {}, "settings": {}}
    
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return {"models": {}, "settings": {}}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix.lower() == '.yaml' or config_path.suffix.lower() == '.yml':
                if YAML_AVAILABLE:
                    config = yaml.safe_load(f) or {}
                else:
                    logger.warning("YAML file found but PyYAML not installed, trying JSON parsing (may fail)")
                    # Reset file pointer and try JSON (will fail for YAML-specific syntax)
                    f.seek(0)
                    config = json.load(f) or {}
            else:
                # Assume JSON
                config = json.load(f) or {}
        return config
    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {e}")
        return {"models": {}, "settings": {}}


def calc_model_price_rub(
    model_id: str,
    params: Dict[str, Any],
    is_admin: bool = False,
    config_path: Optional[Path] = None
) -> float:
    """
    Calculate price in RUB for a model based on parameters.
    
    Args:
        model_id: Model identifier (e.g., "wan/2-6-text-to-video")
        params: Model parameters dict (e.g., {"duration": "5", "resolution": "1080p"})
        is_admin: Whether user is admin (affects markup)
        config_path: Optional path to config file
    
    Returns:
        Price in RUB
    
    Raises:
        ValueError: If price configuration not found or invalid
    """
    config = load_config(config_path)
    models = config.get("models", {})
    settings = config.get("settings", {})
    
    # Get model config
    model_cfg = models.get(model_id)
    if not model_cfg:
        raise ValueError(f"Model {model_id} not found in pricing config")
    
    # Get settings with defaults
    usd_to_rub = settings.get("usd_to_rub", USD_TO_RUB)
    markup_multiplier = settings.get("markup_multiplier", MARKUP_MULTIPLIER)
    
    # Determine pricing type
    mtype = model_cfg.get("type", "fixed")
    
    if mtype == "matrix":
        # Matrix pricing by multiple discrete params (e.g. duration + resolution)
        axes = model_cfg.get("axes", [])
        table = model_cfg.get("table", {})
        
        if len(axes) < 2:
            raise ValueError(f"Matrix pricing requires at least 2 axes, got {len(axes)}")
        
        key1 = str(params.get(axes[0], ""))
        key2 = str(params.get(axes[1], ""))
        
        if not key1 or not key2:
            raise ValueError(f"Missing required parameters: {axes[0]}={key1}, {axes[1]}={key2}")
        
        if key1 not in table:
            raise ValueError(f"Price table missing key1 '{key1}' for {axes[0]}")
        
        if key2 not in table[key1]:
            raise ValueError(f"Price table missing key2 '{key2}' for {axes[1]} (with {axes[0]}={key1})")
        
        cost_usd = float(table[key1][key2])
        
    elif mtype == "fixed":
        # Fixed price per generation
        cost_usd = float(model_cfg.get("price_usd", 0.0))
        
    elif mtype == "per_second":
        # Price per second (for video models)
        price_per_sec_usd = float(model_cfg.get("price_per_sec_usd", 0.0))
        duration = int(params.get("duration", 5))
        cost_usd = price_per_sec_usd * duration
        
    else:
        raise ValueError(f"Unknown pricing type: {mtype}")
    
    # Convert USD to RUB
    price_rub = cost_usd * usd_to_rub
    
    # Apply markup for regular users
    if not is_admin:
        price_rub *= markup_multiplier
    
    return price_rub


def get_model_credits(
    model_id: str,
    params: Dict[str, Any],
    config_path: Optional[Path] = None
) -> Optional[float]:
    """
    Get credits value for UI display (reference only, not used in calculation).
    
    Args:
        model_id: Model identifier
        params: Model parameters dict
        config_path: Optional path to config file
    
    Returns:
        Credits value or None if not available
    """
    config = load_config(config_path)
    models = config.get("models", {})
    
    model_cfg = models.get(model_id)
    if not model_cfg:
        return None
    
    credits_config = model_cfg.get("credits")
    if not credits_config:
        return None
    
    mtype = model_cfg.get("type", "fixed")
    
    if mtype == "matrix":
        axes = model_cfg.get("axes", [])
        if len(axes) < 2:
            return None
        
        key1 = str(params.get(axes[0], ""))
        key2 = str(params.get(axes[1], ""))
        
        if key1 in credits_config and key2 in credits_config.get(key1, {}):
            return float(credits_config[key1][key2])
    
    return None
