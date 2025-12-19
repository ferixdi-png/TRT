"""
Model Registry - Single Source of Truth for KIE Models

This module provides a unified interface for loading models:
1. If KIE_API_KEY present and API reachable -> use kie_client.list_models() (with cache)
2. If API unavailable -> fallback to static KIE_MODELS from kie_models.py

Returns normalized schema compatible with existing code.
"""

import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Global cache
_model_cache: Optional[List[Dict[str, Any]]] = None
_model_source: Optional[str] = None
_model_timestamp: Optional[datetime] = None


async def load_models(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Load models from API or static fallback.
    
    Returns:
        List of normalized model dictionaries
    """
    global _model_cache, _model_source, _model_timestamp
    
    # Return cached if available and not forcing refresh
    if _model_cache is not None and not force_refresh:
        logger.debug(f"✅ Using cached models from {_model_source}")
        return _model_cache
    
    # Try API first
    api_key = os.getenv('KIE_API_KEY')
    api_url = os.getenv('KIE_API_URL', 'https://api.kie.ai')
    
    if api_key:
        try:
            from kie_client import get_client
            client = get_client()
            logger.info("📡 Attempting to load models from KIE API...")
            api_models = await client.list_models()
            
            if api_models and len(api_models) > 0:
                # Normalize API models
                normalized = _normalize_api_models(api_models)
                _model_cache = normalized
                _model_source = "kie_api"
                _model_timestamp = datetime.now()
                logger.info(f"✅ Loaded {len(normalized)} models from KIE API")
                return normalized
            else:
                logger.warning("⚠️ API returned empty list, falling back to static models")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load from API: {e}, falling back to static models")
    
    # Fallback to static models
    try:
        from kie_models import KIE_MODELS
        _model_cache = KIE_MODELS
        _model_source = "static_fallback"
        _model_timestamp = datetime.now()
        logger.info(f"✅ Using static fallback: {len(KIE_MODELS)} models")
        return KIE_MODELS
    except Exception as e:
        logger.error(f"❌ Failed to load static models: {e}", exc_info=True)
        return []


def _normalize_api_models(api_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize API models to match static KIE_MODELS schema.
    
    API models may have different structure, so we normalize them.
    """
    normalized = []
    for model in api_models:
        # Extract model ID (try different fields)
        model_id = model.get('id') or model.get('model_id') or model.get('name', '')
        if not model_id:
            logger.warning(f"⚠️ Skipping model without ID: {model}")
            continue
        
        # Normalize structure
        normalized_model = {
            "id": model_id,
            "name": model.get('name') or model.get('display_name') or model_id,
            "description": model.get('description') or model.get('summary') or "",
            "category": model.get('category') or model.get('type') or "Другое",
            "emoji": model.get('emoji') or "🤖",
            "pricing": model.get('pricing') or model.get('price') or "Цена не указана",
            "input_params": model.get('input_params') or model.get('parameters') or {}
        }
        
        # Ensure required fields
        if not normalized_model.get('input_params'):
            normalized_model['input_params'] = {
                "prompt": {
                    "type": "string",
                    "description": "Текстовый промпт",
                    "required": True
                }
            }
        
        normalized.append(normalized_model)
    
    return normalized


def get_model_registry() -> Dict[str, Any]:
    """
    Get registry metadata (source, count, timestamp).
    
    Returns:
        Dict with source info
    """
    global _model_cache, _model_source, _model_timestamp
    
    if _model_cache is None:
        # Load synchronously (blocking) - for non-async contexts
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we can't use it - return default
                return {
                    "used_source": "unknown",
                    "count": 0,
                    "timestamp": None,
                    "sample_ids": []
                }
            else:
                models = loop.run_until_complete(load_models())
        except:
            # No event loop - return default
            return {
                "used_source": "unknown",
                "count": 0,
                "timestamp": None,
                "sample_ids": []
            }
    else:
        models = _model_cache
    
    return {
        "used_source": _model_source or "unknown",
        "count": len(models) if models else 0,
        "timestamp": _model_timestamp.isoformat() if _model_timestamp else None,
        "sample_ids": [m.get('id', '') for m in (models[:5] if models else [])]
    }


# Synchronous wrapper for compatibility
def get_models_sync() -> List[Dict[str, Any]]:
    """Synchronous wrapper - loads models blocking."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't use existing loop - return static fallback
            from kie_models import KIE_MODELS
            return KIE_MODELS
        else:
            return loop.run_until_complete(load_models())
    except:
        # Fallback to static
        from kie_models import KIE_MODELS
        return KIE_MODELS
