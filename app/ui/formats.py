"""Format-based model organization."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class Format:
    """Represents a format category (e.g., Text → Image)."""
    
    def __init__(
        self,
        key: str,
        name: str,
        emoji: str,
        description: str,
        input_desc: str,
        output_desc: str,
        categories: List[str],
    ):
        self.key = key
        self.name = name
        self.emoji = emoji
        self.description = description
        self.input_desc = input_desc
        self.output_desc = output_desc
        self.categories = categories  # List of category strings to match


# Define all formats
#
# IMPORTANT: every enabled model must be reachable via UI.
# If a model doesn't match a specific format, it MUST fall back to 'other'.
FORMATS = {
    "text-to-image": Format(
        key="text-to-image",
        name="✍️ Text → Image",
        emoji="✍️🖼",
        description="Создавайте изображения из текстового описания",
        input_desc="✍️ текстовое описание",
        output_desc="🖼 изображение",
        categories=["text-to-image", "t2i", "text2image"],
    ),
    "image-to-image": Format(
        key="image-to-image",
        name="🖼 Image → Image",
        emoji="🖼",
        description="Редактируйте и улучшайте изображения",
        input_desc="🖼 изображение",
        output_desc="🖼 обработанное изображение",
        categories=["image-to-image", "i2i", "image", "enhance", "upscale", "background"],
    ),
    "image-to-video": Format(
        key="image-to-video",
        name="🖼 Image → Video",
        emoji="🖼🎬",
        description="Превращайте фото в видео",
        input_desc="🖼 изображение",
        output_desc="🎬 видео",
        categories=["image-to-video", "i2v", "image2video"],
    ),
    "text-to-video": Format(
        key="text-to-video",
        name="🎬 Text → Video",
        emoji="✍️🎬",
        description="Создавайте видео из текста",
        input_desc="✍️ текстовое описание",
        output_desc="🎬 видео",
        categories=["text-to-video", "t2v", "text2video"],
    ),
    "video-to-video": Format(
        key="video-to-video",
        name="🎞 Video → Video",
        emoji="🎞🎬",
        description="Преобразование / стилизация видео",
        input_desc="🎞 видео",
        output_desc="🎬 новое видео",
        categories=["video-to-video", "v2v", "video2video"],
    ),
    "text-to-audio": Format(
        key="text-to-audio",
        name="🎙 Text → Audio",
        emoji="✍️🎙",
        description="Озвучка текста, звуковые эффекты",
        input_desc="✍️ текст",
        output_desc="🎙 аудио",
        categories=["text-to-audio", "text-to-speech", "tts", "sound-effect", "sfx"],
    ),
    "audio-to-audio": Format(
        key="audio-to-audio",
        name="🎚 Audio → Audio",
        emoji="🎚",
        description="Обработка и улучшение аудио",
        input_desc="🎙 аудио",
        output_desc="🎙 обработанное аудио",
        categories=["audio-to-audio", "audio-processing", "audio"],
    ),
    # Catch-all: MUST exist so that models without a specific mapping remain reachable.
    "other": Format(
        key="other",
        name="🔮 Другое",
        emoji="🔮",
        description="Дополнительные модели и инструменты",
        input_desc="разные входы",
        output_desc="разные результаты",
        categories=["other"],
    ),
}


def get_model_format(model_config: Dict[str, Any]) -> Optional[Format]:
    """Infer format for a model.

    Goal: every enabled model must be reachable via UI.

    We use a layered strategy:
    - Heuristics based on output_type + input_schema fields (most reliable)
    - Fallback to substring matching against known category strings
    - Final fallback: FORMATS["other"]
    """

    category = str(model_config.get("category") or "").lower()
    output_type = str(model_config.get("output_type") or "").lower()
    model_id = str(model_config.get("model_id") or "").lower()

    # Extract schema fields
    schema = model_config.get("input_schema") or {}
    props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
    prop_keys = {str(k).lower() for k in props.keys()} if isinstance(props, dict) else set()

    def has_any(*keys: str) -> bool:
        return any(k.lower() in prop_keys for k in keys)

    has_image = has_any("image_url", "image", "input_image", "imageurl")
    has_video = has_any("video_url", "video", "input_video", "videourl")
    has_audio = has_any("audio_url", "audio", "input_audio", "audiourl")
    has_prompt = has_any("prompt", "text", "caption", "description")

    # Special-cases: ElevenLabs-style ids are sometimes mis-categorized as "other" with output_type="text".
    if "text-to-speech" in model_id or "sound-effect" in model_id or "tts" in model_id:
        return FORMATS.get("text-to-audio")

    # Strong signals from output_type + inputs
    if "video" in output_type:
        if has_video or "video-to-video" in category:
            return FORMATS.get("video-to-video")
        if has_image:
            return FORMATS.get("image-to-video")
        if has_prompt:
            return FORMATS.get("text-to-video")

    if "image" in output_type:
        if has_image and not has_prompt:
            # tools (upscale/remove background) still count as Image→Image
            return FORMATS.get("image-to-image")
        if has_image:
            return FORMATS.get("image-to-image")
        if has_prompt:
            return FORMATS.get("text-to-image")

    if "audio" in output_type or "audio" in category:
        if has_audio:
            return FORMATS.get("audio-to-audio")
        if has_prompt:
            return FORMATS.get("text-to-audio")

    # Substring match on category (legacy)
    for format_obj in FORMATS.values():
        for cat in format_obj.categories:
            if cat and cat in category:
                return format_obj

    # Final catch-all
    return FORMATS.get("other")



def group_models_by_format(models: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group models by format.
    
    Args:
        models: Dictionary of model configs
    
    Returns:
        Dict mapping format_key to list of model configs
    """
    grouped = defaultdict(list)
    
    for model_id, model_config in models.items():
        if not model_config.get("enabled", True):
            continue
        
        format_obj = get_model_format(model_config)
        if format_obj:
            grouped[format_obj.key].append(model_config)
        else:
            # Fallback to "other"
            grouped["other"].append(model_config)
    
    return dict(grouped)


def get_popular_models(
    models: Dict[str, Any],
    limit: int = 10,
    format_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get popular models.
    
    Priority:
    1. DB statistics (if available)
    2. Curated list from curated_popular.json
    3. Heuristic (free > cheap > alphabetical)
    
    Args:
        models: Dictionary of model configs
        limit: Maximum number of models to return
        format_key: Filter by format (optional)
    
    Returns:
        List of model configs sorted by popularity
    """
    # Load curated list
    curated = _load_curated_popular()
    
    if format_key:
        # Filter by format
        format_models = []
        for model_id, model_config in models.items():
            if not model_config.get("enabled", True):
                continue
            
            model_format = get_model_format(model_config)
            if model_format and model_format.key == format_key:
                format_models.append(model_config)
        
        available_models = format_models
    else:
        available_models = [
            m for m in models.values()
            if m.get("enabled", True)
        ]
    
    # Score models
    scored_models = []
    for model in available_models:
        model_id = model.get("model_id", "")
        score = 0
        
        # Curated score
        if model_id in curated.get("popular_models", []):
            score += 100
            # Higher score for higher position in list
            try:
                idx = curated["popular_models"].index(model_id)
                score += (20 - idx)  # First gets +20, second +19, etc.
            except (ValueError, IndexError):
                pass
        
        # Format-specific recommendation
        model_format = get_model_format(model)
        if model_format and format_key:
            rec_for_format = curated.get("recommended_by_format", {}).get(format_key, [])
            if model_id in rec_for_format:
                score += 50
                try:
                    idx = rec_for_format.index(model_id)
                    score += (10 - idx)
                except (ValueError, IndexError):
                    pass
        
        # Free models get bonus
        pricing = model.get("pricing", {})
        if pricing.get("is_free", False):
            score += 30
        
        # Cheaper models get bonus
        price_rub = pricing.get("rub_per_use", 999999)
        if price_rub < 10:
            score += 20
        elif price_rub < 50:
            score += 10
        elif price_rub < 100:
            score += 5
        
        scored_models.append((score, model_id, model))
    
    # Sort by score (descending), then by name
    scored_models.sort(key=lambda x: (-x[0], x[1]))
    
    # Return top N
    return [m[2] for m in scored_models[:limit]]


def _load_curated_popular() -> Dict[str, Any]:
    """Load curated popular list."""
    try:
        curated_path = Path(__file__).parent / "curated_popular.json"
        if curated_path.exists():
            with open(curated_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load curated_popular.json: {e}")
    
    return {"popular_models": [], "recommended_by_format": {}}


def get_recommended_models(
    models: Dict[str, Any],
    format_key: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Get recommended models for a format.
    
    Args:
        models: Dictionary of model configs
        format_key: Format key
        limit: Maximum number to return
    
    Returns:
        List of recommended model configs
    """
    curated = _load_curated_popular()
    rec_ids = curated.get("recommended_by_format", {}).get(format_key, [])
    
    recommended = []
    for model_id in rec_ids[:limit]:
        if model_id in models and models[model_id].get("enabled", True):
            recommended.append(models[model_id])
    
    # If not enough from curated, fill with popular from format
    if len(recommended) < limit:
        popular = get_popular_models(models, limit=limit, format_key=format_key)
        for model in popular:
            if model not in recommended:
                recommended.append(model)
            if len(recommended) >= limit:
                break
    
    return recommended[:limit]
