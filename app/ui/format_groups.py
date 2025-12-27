"""Format grouping and sorting helpers."""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Format groups for catalog organization
FORMAT_GROUPS = {
    "text2image": {
        "emoji": "📝→🖼",
        "title": "Текст в картинку",
        "desc": "Креативы, баннеры, иллюстрации"
    },
    "image2image": {
        "emoji": "🖼→🖼",
        "title": "Редактировать фото",
        "desc": "Изменить стиль, улучшить, вариации"
    },
    "image2video": {
        "emoji": "🖼→🎥",
        "title": "Фото в видео",
        "desc": "Оживить фото, создать анимацию"
    },
    "text2video": {
        "emoji": "📝→🎥",
        "title": "Текст в видео",
        "desc": "Генерация видео из промпта"
    },
    "audio2text": {
        "emoji": "🎧→📝",
        "title": "Аудио в текст",
        "desc": "Транскрибация, распознавание речи"
    },
    "text2audio": {
        "emoji": "📝→🎧",
        "title": "Текст в озвучку",
        "desc": "Голосовые сообщения, звуки"
    },
    "tools": {
        "emoji": "🛠",
        "title": "Инструменты",
        "desc": "Фон, апскейл, обработка"
    }
}


def get_format_group(model: Dict) -> str:
    """
    Get format group for model (from overlay or inferred).
    
    Args:
        model: Model dict (with overlay)
    
    Returns:
        Format group key (text2image, image2video, tools, etc.)
    """
    # Check UI overlay first
    if "ui" in model and "format_group" in model["ui"]:
        return model["ui"]["format_group"]
    
    # Fallback: infer from category
    category = model.get("category", "").lower()
    
    if "text-to-image" in category or "t2i" in category:
        return "text2image"
    elif "image-to-image" in category or "i2i" in category:
        return "image2image"
    elif "image-to-video" in category:
        return "image2video"
    elif "text-to-video" in category:
        return "text2video"
    elif "audio-to-text" in category or "stt" in category or "transcription" in category:
        return "audio2text"
    elif "text-to-audio" in category or "tts" in category or "text-to-speech" in category:
        return "text2audio"
    elif "upscale" in category or "background" in category or "enhance" in category:
        return "tools"
    else:
        return "tools"  # Default fallback


def get_popular_score(model: Dict) -> int:
    """
    Get popularity score (higher = more popular).
    
    Args:
        model: Model dict (with overlay)
    
    Returns:
        Score 0-100
    """
    # 1) Curated popularity (hand-picked). Это именно то, что люди будут юзать в первые месяцы.
    curated = {
        # VIDEO (самый спрос)
        "kling/v2-5-turbo-text-to-video-pro": 100,
        "kling/v2-5-turbo-image-to-video-pro": 98,
        "kling-2.6/text-to-video": 96,
        "kling-2.6/image-to-video": 95,
        "kling/v2-5-master-text-to-video": 94,
        "kling/v2-5-master-image-to-video": 93,
        "kling/v2-0-image-to-video": 90,
        "kling/v2-0-text-to-video": 89,

        # IMAGES (топовые креативы)
        "flux-2/pro-text-to-image": 92,
        "flux-2/flex-text-to-image": 88,
        "flux-2/pro-image-to-image": 86,
        "seedream/4.5-text-to-image": 85,
        "seedream/4.5-edit": 84,
        "google/imagen4": 83,
        "google/imagen4-fast": 82,
        "google/imagen4-ultra": 81,
        "google/nano-banana": 80,
        "google/nano-banana-edit": 79,
        "nano-banana-pro": 78,

        # TOOLS (быстрые утилиты)
        "recraft/remove-background": 77,
        "topaz/image-upscale": 76,

        # AUDIO (озвучка)
        "elevenlabs/text-to-speech-turbo-2-5": 75,
        "elevenlabs/text-to-speech-multilingual-v2": 74,
        "elevenlabs/sound-effect-v2": 73,
        "elevenlabs/audio-isolation": 72,
        "infinitalk/from-audio": 71,

        # FREE entry (чтоб новичок сразу кайфанул)
        "z-image": 70,
    }

    model_id = model.get("model_id") or model.get("id")
    if model_id and model_id in curated:
        return curated[model_id]

    # 2) UI overlay (если админ задаст вручную)
    if "ui" in model and "popular_score" in model["ui"]:
        return int(model["ui"]["popular_score"])
    
    # Fallback heuristic: cheaper + faster = more popular
    pricing = model.get("pricing", {})
    rub_per_gen = pricing.get("rub_per_gen", 999999)
    
    # 3) Fallback heuristic: дешевле = выше (чтобы список не был пустой)
    if rub_per_gen < 10:
        return 60
    elif rub_per_gen < 50:
        return 45
    elif rub_per_gen < 200:
        return 30
    else:
        return 15


def group_by_format(models: Dict[str, Dict]) -> Dict[str, List[Dict]]:
    """
    Group models by format group.
    
    Args:
        models: Dict of models (model_id -> model)
    
    Returns:
        Dict[format_group, List[model]]
    """
    groups = {key: [] for key in FORMAT_GROUPS.keys()}
    
    for model_id, model in models.items():
        if not model.get("enabled", True):
            continue
        
        format_group = get_format_group(model)
        if format_group not in groups:
            format_group = "tools"  # Fallback
        
        groups[format_group].append(model)
    
    # Sort each group by popular_score
    for group_key in groups:
        groups[group_key].sort(key=lambda m: get_popular_score(m), reverse=True)
    
    return groups


def get_popular_models(models: Dict[str, Dict], limit: int = 10) -> List[Dict]:
    """
    Get top N popular models (sorted by popular_score).
    
    Args:
        models: Dict of models
        limit: Max models to return
    
    Returns:
        List of models sorted by popularity
    """
    enabled = [m for m in models.values() if m.get("enabled", True)]
    enabled.sort(key=lambda m: get_popular_score(m), reverse=True)
    return enabled[:limit]
