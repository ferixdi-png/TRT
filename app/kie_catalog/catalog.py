"""
KIE AI Models Catalog - загрузка и кеширование каталога моделей.
"""

import yaml
import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from functools import lru_cache

from app.kie_contract.schema_loader import REGISTRY_PATH

logger = logging.getLogger(__name__)

# Глобальный кеш
_catalog_cache: Optional[List['ModelSpec']] = None
_catalog_cache_key: Optional[str] = None


def _get_catalog_path() -> Path:
    root_dir = Path(__file__).parent.parent.parent
    return root_dir / "app" / "kie_catalog" / "models_pricing.yaml"


def get_catalog_source_info() -> Dict[str, Any]:
    """Return catalog source metadata for diagnostics and tests."""
    catalog_file = _get_catalog_path()
    raw_models = _load_yaml_catalog()
    return {
        "path": str(catalog_file) if catalog_file.exists() else "unknown",
        "count": len(raw_models),
    }


@dataclass
class ModelMode:
    """Режим генерации модели."""
    unit: str  # image, video, second, minute, 1000_chars, request, megapixel, removal, upscale
    credits: float
    official_usd: float
    notes: Optional[str] = None


@dataclass
class ModelSpec:
    """Спецификация модели."""
    id: str  # model_id для KIE API
    title_ru: str  # Название для пользователя
    name: str  # Alias for title_ru (required by contract)
    type: str  # t2i, i2i, t2v, i2v, v2v, tts, stt, sfx, audio_isolation, upscale, bg_remove, watermark_remove, music, lip_sync
    category: str  # Alias for type (contract requirement)
    model_type: str  # text_to_image, image_to_video, etc (registry)
    schema_required: List[str] = field(default_factory=list)
    schema_properties: Dict[str, Any] = field(default_factory=dict)
    output_media_type: str = "image"  # image|video|audio|voice|text|file
    free: bool = False
    kie_model: str = ""  # if differs from id
    modes: List[ModelMode] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.title_ru
        if not self.category:
            self.category = self.type
        if not self.kie_model:
            self.kie_model = self.id


MODEL_TYPE_TO_MEDIA = {
    "text_to_image": "image",
    "image_to_image": "image",
    "image_edit": "image",
    "outpaint": "image",
    "upscale": "image",
    "text_to_video": "video",
    "image_to_video": "video",
    "video_upscale": "video",
    "speech_to_video": "video",
    "text_to_speech": "voice",
    "audio_to_audio": "audio",
    "speech_to_text": "text",
}


def _load_registry_models() -> Dict[str, Any]:
    """Load registry models from SSOT."""
    if not REGISTRY_PATH.exists():
        logger.error(f"Registry file not found: {REGISTRY_PATH}")
        return {}
    try:
        with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:
        logger.error(f"Failed to load registry: {exc}", exc_info=True)
        return {}
    models = data.get("models", {})
    return models if isinstance(models, dict) else {}


def _extract_schema(model_data: Dict[str, Any]) -> Dict[str, Any]:
    schema = model_data.get("input", {})
    return schema if isinstance(schema, dict) else {}


def _schema_required(schema: Dict[str, Any]) -> List[str]:
    required = [name for name, spec in schema.items() if spec.get("required", False)]
    return required


def _compute_output_media_type(model_type: str) -> Optional[str]:
    return MODEL_TYPE_TO_MEDIA.get(model_type)


def _load_yaml_catalog() -> List[Dict[str, Any]]:
    """Загружает YAML каталог."""
    catalog_file = _get_catalog_path()
    
    if not catalog_file.exists():
        logger.error(f"Catalog file not found: {catalog_file}")
        return []
    
    try:
        with open(catalog_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict) or 'models' not in data:
            logger.error("Invalid catalog format: missing 'models' key")
            return []
        
        return data['models']
    except Exception as e:
        logger.error(f"Error loading catalog: {e}", exc_info=True)
        return []


def _is_free_model_data(model_data: Dict[str, Any]) -> bool:
    """Определяет бесплатную модель по данным каталога."""
    if model_data.get("free") is True:
        return True
    for mode in model_data.get("modes", []):
        if mode.get("free") is True:
            return True
        if mode.get("credits") == 0 or mode.get("official_usd") == 0 or mode.get("price_rub") == 0:
            return True
    return False


def _parse_model_spec(
    model_data: Dict[str, Any],
    registry_data: Optional[Dict[str, Any]] = None,
) -> ModelSpec:
    """Парсит данные модели в ModelSpec."""
    modes = []
    for mode_data in model_data.get('modes', []):
        mode = ModelMode(
            unit=mode_data.get('unit', 'image'),
            credits=float(mode_data.get('credits', 0.0)),
            official_usd=float(mode_data.get('official_usd', 0.0)),
            notes=mode_data.get('notes')
        )
        modes.append(mode)

    model_id = model_data.get('id', '')
    registry_data = registry_data or {}
    model_type = registry_data.get("model_type", "")
    schema = _extract_schema(registry_data)
    output_media_type = _compute_output_media_type(model_type)
    return ModelSpec(
        id=model_id,
        title_ru=model_data.get('title_ru', ''),
        name=model_data.get('title_ru', ''),
        type=model_data.get('type', 't2i'),
        category=model_data.get('type', 't2i'),
        model_type=model_type,
        schema_required=_schema_required(schema),
        schema_properties=schema,
        output_media_type=output_media_type or "",
        free=_is_free_model_data(model_data),
        kie_model=registry_data.get("kie_model", model_id),
        modes=modes
    )


def load_catalog(force_reload: bool = False) -> List[ModelSpec]:
    """
    Загружает каталог моделей.
    
    Args:
        force_reload: Если True, принудительно перезагружает каталог
    
    Returns:
        Список ModelSpec
    """
    global _catalog_cache
    global _catalog_cache_key

    cache_key = _compute_catalog_cache_key()
    
    if _catalog_cache is not None and not force_reload and _catalog_cache_key == cache_key:
        logger.debug("CATALOG_CACHE hit cache_key=%s models=%s", cache_key, len(_catalog_cache))
        return _catalog_cache
    
    logger.info("CATALOG_CACHE miss cache_key=%s force_reload=%s", cache_key, force_reload)
    start_time = time.monotonic()
    logger.info("Loading KIE models catalog...")
    raw_models = _load_yaml_catalog()
    registry_models = _load_registry_models()
    
    models = []
    for model_data in raw_models:
        try:
            model_id = model_data.get("id", "")
            registry_data = registry_models.get(model_id, {})
            model_spec = _parse_model_spec(model_data, registry_data)
            if model_spec.id:
                models.append(model_spec)
        except Exception as e:
            logger.warning(f"Error parsing model {model_data.get('id', 'unknown')}: {e}")
            continue
    
    _catalog_cache = models
    _catalog_cache_key = cache_key
    load_ms = int((time.monotonic() - start_time) * 1000)
    logger.info("CATALOG_CACHE loaded models=%s load_ms=%s", len(models), load_ms)
    logger.info(f"Loaded {len(models)} models from catalog")
    
    # Проверяем каталог при загрузке (только предупреждения, не останавливаем)
    _verify_catalog_internal(models)
    
    return models


def get_free_model_ids() -> List[str]:
    """
    Возвращает список ID бесплатных моделей из каталога.
    Бесплатность определяется только по данным каталога (free=true или 0 credits).
    """
    return [model.id for model in load_catalog() if model.free]


def _verify_catalog_internal(models: List[ModelSpec]) -> None:
    """
    Внутренняя проверка каталога (только логирование, не останавливает работу).
    
    Args:
        models: Список моделей для проверки
    """
    from collections import Counter
    
    # Проверяем дубли model_id
    model_ids = [m.id for m in models]
    duplicates = [model_id for model_id, count in Counter(model_ids).items() if count > 1]
    if duplicates:
        logger.warning(f"Catalog warning: duplicate model_ids found: {duplicates}")
    
    # Проверяем что все official_usd > 0
    invalid_prices = []
    for model in models:
        for mode in model.modes:
            if mode.official_usd <= 0:
                invalid_prices.append(f"{model.id} mode {mode.notes or 'default'}")
    if invalid_prices:
        logger.warning(f"Catalog warning: models with official_usd <= 0: {invalid_prices[:5]}")
    
    # Проверяем типы
    allowed_types = {'t2i', 'i2i', 't2v', 'i2v', 'v2v', 'tts', 'stt', 'sfx', 'audio_isolation', 
                     'upscale', 'bg_remove', 'watermark_remove', 'music', 'lip_sync'}
    invalid_types = [m.id for m in models if m.type not in allowed_types]
    if invalid_types:
        logger.warning(f"Catalog warning: models with invalid types: {invalid_types[:5]}")

    # Проверяем уникальные model_id и обязательные поля SSOT
    if len(model_ids) != len(set(model_ids)):
        raise ValueError(f"Duplicate model_ids detected: {duplicates}")

    invalid_schema = [m.id for m in models if m.schema_properties is None or m.schema_required is None]
    if invalid_schema:
        raise ValueError(f"Missing schema for models: {invalid_schema}")

    missing_output = [m.id for m in models if not m.output_media_type]
    if missing_output:
        raise ValueError(f"Missing output_media_type for models: {missing_output}")


def get_model_map() -> Dict[str, ModelSpec]:
    """Return dict[model_id] = ModelSpec."""
    return {model.id: model for model in load_catalog()}


def get_model(model_id: str) -> Optional[ModelSpec]:
    """
    Получает модель по ID.
    
    Args:
        model_id: ID модели
    
    Returns:
        ModelSpec или None
    """
    catalog = load_catalog()
    for model in catalog:
        if model.id == model_id:
            return model
    return None


def list_models() -> List[ModelSpec]:
    """
    Возвращает список всех моделей.
    
    Returns:
        Список всех ModelSpec
    """
    return load_catalog()


def reset_catalog_cache():
    """Сбрасывает кеш каталога (для тестов)."""
    global _catalog_cache
    global _catalog_cache_key
    _catalog_cache = None
    _catalog_cache_key = None
    logger.debug("Catalog cache reset")
def _compute_catalog_cache_key() -> str:
    catalog_file = _get_catalog_path()
    registry_file = REGISTRY_PATH
    catalog_mtime = catalog_file.stat().st_mtime if catalog_file.exists() else 0
    registry_mtime = registry_file.stat().st_mtime if registry_file.exists() else 0
    return f"{catalog_mtime:.6f}:{registry_mtime:.6f}"
