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
        # Нормализуем статические модели тоже (гарантируем model_type и обязательные поля)
        normalized_static = []
        seen_ids = set()
        for model in KIE_MODELS:
            try:
                normalized_model = _normalize_model(model)
                model_id = normalized_model['id']
                if model_id in seen_ids:
                    logger.warning(f"⚠️ Duplicate model ID in static models: {model_id}, skipping")
                    continue
                seen_ids.add(model_id)
                normalized_static.append(normalized_model)
            except Exception as e:
                logger.warning(f"⚠️ Failed to normalize static model {model.get('id', 'unknown')}: {e}")
                continue
        
        _model_cache = normalized_static
        _model_source = "static_fallback"
        _model_timestamp = datetime.now()
        logger.info(f"✅ Using static fallback: {len(normalized_static)} normalized models")
        return normalized_static
    except Exception as e:
        logger.error(f"❌ Failed to load static models: {e}", exc_info=True)
        return []


def _determine_model_type(model_id: str, category: str, input_params: Dict[str, Any]) -> str:
    """
    Определяет model_type на основе model_id, category и input_params.
    
    Returns:
        model_type string (text_to_image, text_to_video, image_to_video, etc.)
    """
    model_id_lower = model_id.lower()
    category_lower = category.lower()
    
    # Проверяем input_params для более точного определения
    has_video = any('video' in k.lower() for k in input_params.keys())
    has_image = any('image' in k.lower() for k in input_params.keys())
    has_prompt = 'prompt' in input_params
    
    # Маппинг на основе model_id
    if 'text-to-video' in model_id_lower or 'text_to_video' in model_id_lower:
        return 'text_to_video'
    elif 'image-to-video' in model_id_lower or 'image_to_video' in model_id_lower:
        return 'image_to_video'
    elif 'video-to-video' in model_id_lower or 'video_to_video' in model_id_lower:
        return 'video_to_video'
    elif 'text-to-image' in model_id_lower or 'text_to_image' in model_id_lower:
        return 'text_to_image'
    elif 'image-to-image' in model_id_lower or 'image_to_image' in model_id_lower:
        return 'image_to_image'
    elif 'image-edit' in model_id_lower or 'image_edit' in model_id_lower or ('edit' in model_id_lower and 'image' in model_id_lower):
        return 'image_edit'
    elif 'upscale' in model_id_lower:
        if 'video' in category_lower:
            return 'video_upscale'
        return 'image_upscale'
    elif 'watermark' in model_id_lower or ('remove' in model_id_lower and 'watermark' in model_id_lower):
        return 'video_edit'
    elif 'speech-to-video' in model_id_lower or 'speech_to_video' in model_id_lower:
        return 'speech_to_video'
    elif 'text-to-speech' in model_id_lower or 'text_to_speech' in model_id_lower:
        return 'text_to_speech'
    elif 'speech-to-text' in model_id_lower or 'speech_to_text' in model_id_lower:
        return 'speech_to_text'
    elif 'text-to-music' in model_id_lower or 'text_to_music' in model_id_lower or 'suno' in model_id_lower:
        return 'text_to_music'
    elif 'outpaint' in model_id_lower:
        return 'outpaint'
    elif 'audio-to-audio' in model_id_lower or 'audio_to_audio' in model_id_lower:
        return 'audio_to_audio'
    
    # Маппинг на основе category
    if 'видео' in category_lower or 'video' in category_lower:
        if has_prompt and not has_image:
            return 'text_to_video'
        elif has_image:
            return 'image_to_video'
        else:
            return 'video_edit'
    elif 'фото' in category_lower or 'image' in category_lower or 'photo' in category_lower:
        if has_prompt and not has_image:
            return 'text_to_image'
        elif has_image:
            return 'image_to_image'
        else:
            return 'image_edit'
    elif 'аудио' in category_lower or 'audio' in category_lower or 'speech' in category_lower:
        if 'speech' in model_id_lower:
            if 'to-text' in model_id_lower or 'to_text' in model_id_lower:
                return 'speech_to_text'
            elif 'to-video' in model_id_lower or 'to_video' in model_id_lower:
                return 'speech_to_video'
        return 'audio_to_audio'
    
    # Маппинг на основе input_params
    if has_video and has_image:
        return 'image_to_video'
    elif has_video and has_prompt:
        return 'text_to_video'
    elif has_image and has_prompt:
        return 'image_to_image'
    elif has_prompt:
        return 'text_to_image'
    
    # Дефолт
    return 'text_to_image'


def _normalize_model(model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализует одну модель, гарантируя наличие всех обязательных полей.
    
    Обязательные поля:
    - id (str)
    - name (str)
    - category (str)
    - emoji (str)
    - model_type (str)
    - input_params (dict)
    
    Returns:
        Нормализованная модель
    """
    # Извлекаем обязательные поля
    model_id = model.get('id') or model.get('model_id') or model.get('name', '')
    if not model_id:
        raise ValueError(f"Model missing required field 'id': {model}")
    
    name = model.get('name') or model.get('display_name') or model.get('title') or model_id
    category = model.get('category') or model.get('type') or "Другое"
    emoji = model.get('emoji') or "🤖"
    input_params = model.get('input_params') or model.get('parameters') or model.get('input_schema', {}).get('properties', {}) or {}
    
    # Определяем model_type (если не указан)
    model_type = model.get('model_type') or model.get('generation_type')
    if not model_type:
        model_type = _determine_model_type(model_id, category, input_params)
    
    # Обеспечиваем input_params (минимум prompt)
    if not input_params:
        input_params = {
            "prompt": {
                "type": "string",
                "description": "Текстовый промпт",
                "required": True
            }
        }
    
    # Строим нормализованную модель
    normalized = {
        "id": model_id,
        "name": name,
        "category": category,
        "emoji": emoji,
        "model_type": model_type,
        "input_params": input_params
    }
    
    # Добавляем опциональные поля
    if 'description' in model:
        normalized['description'] = model['description']
    if 'pricing' in model:
        normalized['pricing'] = model['pricing']
    elif 'price' in model:
        normalized['pricing'] = model['price']
    
    return normalized


def _normalize_api_models(api_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize API models to match static KIE_MODELS schema.
    
    API models may have different structure, so we normalize them.
    Гарантирует наличие всех обязательных полей, включая model_type.
    """
    normalized = []
    seen_ids = set()
    
    for model in api_models:
        try:
            normalized_model = _normalize_model(model)
            
            # Проверка на дубликаты
            model_id = normalized_model['id']
            if model_id in seen_ids:
                logger.warning(f"⚠️ Duplicate model ID: {model_id}, skipping")
                continue
            seen_ids.add(model_id)
            
            normalized.append(normalized_model)
        except Exception as e:
            logger.warning(f"⚠️ Failed to normalize model: {e}, skipping")
            continue
    
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
            # Can't use existing loop - return static fallback (normalized)
            from kie_models import KIE_MODELS
            normalized = []
            seen_ids = set()
            for model in KIE_MODELS:
                try:
                    norm_model = _normalize_model(model)
                    if norm_model['id'] not in seen_ids:
                        seen_ids.add(norm_model['id'])
                        normalized.append(norm_model)
                except:
                    continue
            return normalized
        else:
            return loop.run_until_complete(load_models())
    except:
        # Fallback to static (normalized)
        from kie_models import KIE_MODELS
        normalized = []
        seen_ids = set()
        for model in KIE_MODELS:
            try:
                norm_model = _normalize_model(model)
                if norm_model['id'] not in seen_ids:
                    seen_ids.add(norm_model['id'])
                    normalized.append(norm_model)
            except:
                continue
        return normalized


def _model_type_to_generation_type(model_type: str) -> str:
    """Конвертирует model_type в generation_type формат (с дефисами)."""
    mapping = {
        'text_to_image': 'text-to-image',
        'text_to_video': 'text-to-video',
        'image_to_video': 'image-to-video',
        'image_to_image': 'image-to-image',
        'image_edit': 'image-edit',
        'image_upscale': 'upscale',
        'video_upscale': 'video-upscale',
        'video_edit': 'video-edit',
        'speech_to_video': 'speech-to-video',
        'text_to_speech': 'text-to-speech',
        'speech_to_text': 'speech-to-text',
        'text_to_music': 'text-to-music',
        'outpaint': 'outpaint',
        'audio_to_audio': 'audio-to-audio',
    }
    return mapping.get(model_type, model_type.replace('_', '-'))


def get_models_by_model_type(model_type: str) -> List[Dict[str, Any]]:
    """Получить модели по model_type (синхронно)."""
    models = get_models_sync()
    return [m for m in models if m.get('model_type') == model_type]


def get_all_model_types() -> List[str]:
    """Получить список всех model_type (синхронно)."""
    models = get_models_sync()
    return sorted(set(m.get('model_type', 'unknown') for m in models))


def get_generation_types() -> List[str]:
    """Получить список generation_types (для совместимости с kie_models)."""
    model_types = get_all_model_types()
    return [_model_type_to_generation_type(mt) for mt in model_types]


def get_models_by_generation_type(gen_type: str) -> List[Dict[str, Any]]:
    """Получить модели по generation_type (для совместимости с kie_models)."""
    # Конвертируем generation_type обратно в model_type
    reverse_mapping = {
        'text-to-image': 'text_to_image',
        'text-to-video': 'text_to_video',
        'image-to-video': 'image_to_video',
        'image-to-image': 'image_to_image',
        'image-edit': 'image_edit',
        'upscale': 'image_upscale',
        'video-upscale': 'video_upscale',
        'video-edit': 'video_edit',
        'speech-to-video': 'speech_to_video',
        'text-to-speech': 'text_to_speech',
        'speech-to-text': 'speech_to_text',
        'text-to-music': 'text_to_music',
        'outpaint': 'outpaint',
        'audio-to-audio': 'audio_to_audio',
    }
    model_type = reverse_mapping.get(gen_type, gen_type.replace('-', '_'))
    return get_models_by_model_type(model_type)
