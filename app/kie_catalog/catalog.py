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
from pricing.engine import load_config

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
    title_ru: Optional[str] = None
    short_hint_ru: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit": self.unit,
            "credits": self.credits,
            "official_usd": self.official_usd,
            "notes": self.notes,
            "title_ru": self.title_ru,
            "short_hint_ru": self.short_hint_ru,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self.to_dict()


@dataclass
class ModelSpec:
    """Спецификация модели."""
    id: str  # model_id для KIE API
    title_ru: str  # Название для пользователя
    name: str  # Alias for title_ru (required by contract)
    type: str  # t2i, i2i, t2v, i2v, v2v, tts, stt, sfx, audio_isolation, upscale, bg_remove, watermark_remove, music, lip_sync
    category: str  # Alias for type (contract requirement)
    model_type: str  # text_to_image, image_to_video, etc (registry)
    model_mode: str  # text_to_image, image_to_image, image_edit, etc (registry)
    schema_required: List[str] = field(default_factory=list)
    schema_properties: Dict[str, Any] = field(default_factory=dict)
    output_media_type: str = "document"  # image|video|audio|text|document
    free: bool = False
    kie_model: str = ""  # if differs from id
    modes: List[ModelMode] = field(default_factory=list)
    description_ru: str = ""
    required_inputs_ru: List[str] = field(default_factory=list)
    output_type_ru: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.title_ru
        if not self.category:
            self.category = self.type
        if not self.kie_model:
            self.kie_model = self.id

    @property
    def gen_type(self) -> str:
        """Compatibility alias for generation type (text-to-image)."""
        base = self.model_mode or self.model_type or self.type
        return base.replace("_", "-") if base else "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "title_ru": self.title_ru,
            "type": self.type,
            "category": self.category,
            "model_type": self.model_type,
            "model_mode": self.model_mode,
            "gen_type": self.gen_type,
            "schema_required": self.schema_required,
            "schema_properties": self.schema_properties,
            "output_media_type": self.output_media_type,
            "free": self.free,
            "kie_model": self.kie_model,
            "modes": [mode.to_dict() for mode in self.modes],
            "description_ru": self.description_ru,
            "required_inputs_ru": self.required_inputs_ru,
            "output_type_ru": self.output_type_ru,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self.to_dict()


ALLOWED_OUTPUT_MEDIA_TYPES = {"image", "video", "audio", "text", "document"}

MODEL_TYPE_TO_MEDIA = {
    "text_to_image": "image",
    "image_to_image": "image",
    "image_edit": "image",
    "outpaint": "image",
    "upscale": "image",
    "text_to_video": "video",
    "image_to_video": "video",
    "video_upscale": "video",
    "video_editing": "video",
    "speech_to_video": "video",
    "lip_sync": "video",
    "text_to_speech": "audio",
    "text_to_audio": "audio",
    "audio_to_audio": "audio",
    "speech_to_text": "text",
    "text": "text",
}

OUTPUT_MEDIA_TYPE_RU = {
    "image": "Изображение",
    "video": "Видео",
    "audio": "Аудио",
    "text": "Текст",
    "document": "Файл",
}

MODEL_TYPE_DESCRIPTION_RU = {
    "text_to_image": "Генерация изображения по текстовому описанию.",
    "image_to_image": "Преобразование изображения по вашему запросу.",
    "image_edit": "Редактирование изображения по описанию.",
    "outpaint": "Расширение изображения по описанию.",
    "upscale": "Повышение качества и разрешения изображения.",
    "text_to_video": "Генерация видео по текстовому описанию.",
    "image_to_video": "Анимация изображения в видео.",
    "video_upscale": "Повышение качества видео.",
    "video_editing": "Редактирование и очистка видео.",
    "speech_to_video": "Создание видео по голосу.",
    "lip_sync": "Синхронизация губ по аудио.",
    "text_to_speech": "Озвучка текста.",
    "text_to_audio": "Генерация аудио по тексту.",
    "audio_to_audio": "Обработка и улучшение аудио.",
    "speech_to_text": "Распознавание речи в текст.",
    "text": "Генерация текстового результата.",
}


def _humanize_param_ru(param_name: str) -> str:
    ru_map = {
        "prompt": "Текст запроса",
        "text": "Текст запроса",
        "image_input": "Изображение",
        "image_urls": "Изображение",
        "image_url": "Изображение",
        "audio_input": "Аудио",
        "audio_url": "Аудио",
        "video_input": "Видео",
        "video_url": "Видео",
        "mask": "Маска",
    }
    return ru_map.get(param_name, param_name.replace("_", " ").capitalize())


def _default_required_inputs_ru(schema: Dict[str, Any]) -> List[str]:
    required = [name for name, info in schema.items() if info.get("required", False)]
    return [_humanize_param_ru(name) for name in required]


def _default_description_ru(model_type: str) -> str:
    return MODEL_TYPE_DESCRIPTION_RU.get(model_type, "Генерация результата по вашему запросу.")


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
    if not isinstance(models, dict):
        return {}
    for model_id, model_data in models.items():
        if not isinstance(model_data, dict):
            continue
        output_media_type = _normalize_output_media_type(model_data.get("output_media_type"))
        if not output_media_type:
            model_type = model_data.get("model_type")
            if model_type and model_type in MODEL_TYPE_TO_MEDIA:
                output_media_type = MODEL_TYPE_TO_MEDIA[model_type]
        if output_media_type:
            if output_media_type not in ALLOWED_OUTPUT_MEDIA_TYPES:
                logger.warning(
                    "SSOT invalid output_media_type model=%s media=%s",
                    model_id,
                    output_media_type,
                )
            model_data["output_media_type"] = output_media_type
            logger.debug(
                "SSOT enriched output_media_type model=%s media=%s",
                model_id,
                output_media_type,
            )
    return models


def _extract_schema(model_data: Dict[str, Any]) -> Dict[str, Any]:
    schema = model_data.get("input", {})
    return schema if isinstance(schema, dict) else {}


def _schema_required(schema: Dict[str, Any], model_mode: str) -> List[str]:
    required = []
    for name, spec in schema.items():
        is_required = spec.get("required", False)
        if name in {"image_input", "image_urls"}:
            if model_mode in {"text_to_image", "text_to_video", "text_to_audio", "text_to_speech", "text"}:
                is_required = False
            elif model_mode in {"image_to_image", "image_edit", "image_to_video", "outpaint", "upscale", "video_upscale"}:
                is_required = True
        if is_required:
            required.append(name)
    return required


def _compute_output_media_type(model_type: str) -> Optional[str]:
    return MODEL_TYPE_TO_MEDIA.get(model_type)


def _normalize_output_media_type(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = str(value).lower()
    if normalized == "file":
        return "document"
    if normalized == "voice":
        return "audio"
    return normalized


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
    from app.pricing.price_ssot import model_has_free_sku

    model_id = model_data.get("id")
    if not model_id:
        return False
    return model_has_free_sku(model_id)


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
            notes=mode_data.get('notes'),
            title_ru=mode_data.get('title_ru'),
            short_hint_ru=mode_data.get('short_hint_ru') or mode_data.get('notes'),
        )
        modes.append(mode)

    model_id = model_data.get('id', '')
    registry_data = registry_data or {}
    model_type = registry_data.get("model_type", "")
    model_mode = registry_data.get("model_mode") or model_type
    schema = _extract_schema(registry_data)
    output_media_type = _compute_output_media_type(model_type)
    description_ru = model_data.get("description_ru") or _default_description_ru(model_type)
    required_inputs_ru = model_data.get("required_inputs_ru") or _default_required_inputs_ru(schema)
    output_type_ru = model_data.get("output_type_ru") or OUTPUT_MEDIA_TYPE_RU.get(output_media_type or "", "")
    return ModelSpec(
        id=model_id,
        title_ru=model_data.get('title_ru', ''),
        name=model_data.get('title_ru', ''),
        type=model_data.get('type', 't2i'),
        category=model_data.get('type', 't2i'),
        model_type=model_type,
        model_mode=model_mode,
        schema_required=_schema_required(schema, model_mode),
        schema_properties=schema,
        output_media_type=output_media_type or "",
        free=_is_free_model_data(model_data),
        kie_model=registry_data.get("kie_model", model_id),
        modes=modes,
        description_ru=description_ru,
        required_inputs_ru=required_inputs_ru,
        output_type_ru=output_type_ru,
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
    Бесплатность определяется только по явным SKU в прайс-SSOT.
    """
    free_tools = load_config().get("free_tools", {})
    model_ids = free_tools.get("model_ids")
    if isinstance(model_ids, list) and model_ids:
        return list(model_ids)
    return []


def get_free_tools_model_ids(*, log_selection: bool = True) -> List[str]:
    """Return SKU IDs marked as free in the pricing SSOT."""
    from app.pricing.ssot_catalog import get_free_sku_ids
    from app.observability.structured_logs import log_structured_event

    selected = get_free_sku_ids()
    if log_selection:
        log_structured_event(
            action="FREE_TOOLS_SELECT",
            action_path="kie_catalog.get_free_tools_model_ids",
            stage="FREE_TOOLS",
            outcome="selected",
            param={"selected_count": len(selected), "sku_ids": selected},
        )
    return selected


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
