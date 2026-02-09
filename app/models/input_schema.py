"""
Source of Truth: Model Input Schema
===================================
Единая схема параметров для всех моделей.
Используется для:
- Валидации перед отправкой в API
- Генерации UI форм
- Подсказок и плейсхолдеров
- Текстов ошибок
- Маппинга в API payload
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class ParamType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ENUM = "enum"
    FILE_URL = "file_url"
    FILE_URLS = "file_urls"  # array of URLs


@dataclass
class ParamSpec:
    """Specification for a single parameter."""
    name: str                          # Internal API key
    label_ru: str                      # Human-readable label (RU)
    label_en: str                      # Human-readable label (EN)
    type: ParamType
    required: bool = False
    default: Any = None
    
    # Constraints
    min_value: Optional[float] = None  # For number/integer
    max_value: Optional[float] = None
    min_length: Optional[int] = None   # For string
    max_length: Optional[int] = None
    enum_values: Optional[List[str]] = None  # For enum
    max_items: Optional[int] = None    # For arrays
    
    # UX
    placeholder_ru: str = ""
    placeholder_en: str = ""
    hint_ru: str = ""                  # Why this field matters
    hint_en: str = ""
    error_ru: str = ""                 # Error message template
    error_en: str = ""
    example: str = ""                  # Example value
    
    # Dependencies
    depends_on: Optional[str] = None   # Show only if this param is set
    depends_value: Any = None          # Required value of depends_on
    
    # Advanced
    advanced: bool = False             # Hide in basic mode


@dataclass
class ModelInputSchema:
    """Complete input schema for a model."""
    model_id: str
    model_type: str                    # t2i, i2i, t2v, i2v, etc.
    params: List[ParamSpec] = field(default_factory=list)
    
    # UX metadata
    checklist_ru: List[str] = field(default_factory=list)  # Pre-gen checklist
    checklist_en: List[str] = field(default_factory=list)
    output_ru: str = ""                # What user gets
    output_en: str = ""
    typical_errors_ru: List[str] = field(default_factory=list)
    typical_errors_en: List[str] = field(default_factory=list)


# =============================================================================
# COMMON PARAMETER TEMPLATES
# =============================================================================

PROMPT_PARAM = ParamSpec(
    name="prompt",
    label_ru="Промпт",
    label_en="Prompt",
    type=ParamType.STRING,
    required=True,
    min_length=1,
    max_length=2000,
    placeholder_ru="Опишите, что хотите создать...",
    placeholder_en="Describe what you want to create...",
    hint_ru="Чем детальнее описание, тем точнее результат",
    hint_en="The more detailed the description, the more accurate the result",
    error_ru="Введите описание (от 1 до {max} символов)",
    error_en="Enter a description (1 to {max} characters)",
    example="A serene mountain landscape at sunset with golden light"
)

NEGATIVE_PROMPT_PARAM = ParamSpec(
    name="negative_prompt",
    label_ru="Негативный промпт",
    label_en="Negative prompt",
    type=ParamType.STRING,
    required=False,
    max_length=1000,
    placeholder_ru="Что исключить из генерации...",
    placeholder_en="What to exclude from generation...",
    hint_ru="Укажите элементы, которые не должны появиться",
    hint_en="Specify elements that should not appear",
    error_ru="Слишком длинный негативный промпт (макс. {max} символов)",
    error_en="Negative prompt too long (max {max} characters)",
    example="blurry, low quality, watermark",
    advanced=True
)

ASPECT_RATIO_PARAM = ParamSpec(
    name="aspect_ratio",
    label_ru="Соотношение сторон",
    label_en="Aspect ratio",
    type=ParamType.ENUM,
    required=False,
    default="1:1",
    enum_values=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    placeholder_ru="Выберите формат",
    placeholder_en="Select format",
    hint_ru="1:1 — квадрат, 16:9 — широкий, 9:16 — вертикальный",
    hint_en="1:1 — square, 16:9 — wide, 9:16 — vertical",
    error_ru="Выберите соотношение сторон из списка",
    error_en="Select aspect ratio from the list"
)

IMAGE_URL_PARAM = ParamSpec(
    name="image_input",
    label_ru="Исходное изображение",
    label_en="Source image",
    type=ParamType.FILE_URLS,
    required=True,
    max_items=1,
    placeholder_ru="Загрузите фото или вставьте ссылку",
    placeholder_en="Upload a photo or paste a URL",
    hint_ru="Поддерживаются JPG, PNG, WebP до 20 МБ",
    hint_en="Supports JPG, PNG, WebP up to 20 MB",
    error_ru="Загрузите изображение",
    error_en="Upload an image"
)

DURATION_PARAM = ParamSpec(
    name="duration",
    label_ru="Длительность",
    label_en="Duration",
    type=ParamType.ENUM,
    required=False,
    default="5",
    enum_values=["5", "10", "15"],
    placeholder_ru="Выберите длительность",
    placeholder_en="Select duration",
    hint_ru="Более длинные видео стоят дороже",
    hint_en="Longer videos cost more",
    error_ru="Выберите длительность видео",
    error_en="Select video duration"
)

RESOLUTION_PARAM = ParamSpec(
    name="resolution",
    label_ru="Разрешение",
    label_en="Resolution",
    type=ParamType.ENUM,
    required=False,
    default="720p",
    enum_values=["480p", "720p", "1080p", "4K"],
    placeholder_ru="Выберите качество",
    placeholder_en="Select quality",
    hint_ru="Высокое разрешение = больше деталей, выше цена",
    hint_en="Higher resolution = more details, higher price",
    error_ru="Выберите разрешение из списка",
    error_en="Select resolution from the list"
)

QUALITY_PARAM = ParamSpec(
    name="quality",
    label_ru="Качество",
    label_en="Quality",
    type=ParamType.ENUM,
    required=False,
    default="standard",
    enum_values=["standard", "high", "pro", "max"],
    placeholder_ru="Выберите уровень качества",
    placeholder_en="Select quality level",
    hint_ru="Pro/Max — детальнее, но дороже",
    hint_en="Pro/Max — more detailed, but pricier",
    error_ru="Выберите уровень качества",
    error_en="Select quality level"
)

SEED_PARAM = ParamSpec(
    name="seed",
    label_ru="Seed",
    label_en="Seed",
    type=ParamType.INTEGER,
    required=False,
    min_value=0,
    max_value=2147483647,
    placeholder_ru="Оставьте пустым для случайного",
    placeholder_en="Leave empty for random",
    hint_ru="Один seed = воспроизводимый результат",
    hint_en="Same seed = reproducible result",
    error_ru="Seed должен быть от 0 до 2147483647",
    error_en="Seed must be from 0 to 2147483647",
    advanced=True
)


# =============================================================================
# MODEL SCHEMAS REGISTRY
# =============================================================================

MODEL_SCHEMAS: Dict[str, ModelInputSchema] = {}


def register_schema(schema: ModelInputSchema):
    """Register a model schema."""
    MODEL_SCHEMAS[schema.model_id] = schema


def get_schema(model_id: str) -> Optional[ModelInputSchema]:
    """Get schema for a model."""
    return MODEL_SCHEMAS.get(model_id)


def validate_input(model_id: str, params: Dict[str, Any], lang: str = "ru") -> List[str]:
    """
    Validate input parameters against schema.
    Returns list of error messages (empty if valid).
    """
    schema = get_schema(model_id)
    if not schema:
        return []  # No schema = no validation
    
    errors = []
    for spec in schema.params:
        value = params.get(spec.name)
        
        # Check required
        if spec.required and (value is None or value == ""):
            err = spec.error_ru if lang == "ru" else spec.error_en
            errors.append(err.format(max=spec.max_length or 0, min=spec.min_length or 0))
            continue
        
        if value is None:
            continue
        
        # Type validation
        if spec.type == ParamType.STRING:
            if not isinstance(value, str):
                errors.append(f"{spec.label_ru}: должна быть строка" if lang == "ru" else f"{spec.label_en}: must be a string")
            elif spec.min_length and len(value) < spec.min_length:
                errors.append(f"{spec.label_ru}: минимум {spec.min_length} символов" if lang == "ru" else f"{spec.label_en}: minimum {spec.min_length} characters")
            elif spec.max_length and len(value) > spec.max_length:
                errors.append(f"{spec.label_ru}: максимум {spec.max_length} символов" if lang == "ru" else f"{spec.label_en}: maximum {spec.max_length} characters")
        
        elif spec.type == ParamType.ENUM:
            if spec.enum_values and str(value) not in spec.enum_values:
                err = spec.error_ru if lang == "ru" else spec.error_en
                errors.append(err)
        
        elif spec.type in (ParamType.NUMBER, ParamType.INTEGER):
            try:
                num_val = float(value) if spec.type == ParamType.NUMBER else int(value)
                if spec.min_value is not None and num_val < spec.min_value:
                    errors.append(f"{spec.label_ru}: минимум {spec.min_value}" if lang == "ru" else f"{spec.label_en}: minimum {spec.min_value}")
                if spec.max_value is not None and num_val > spec.max_value:
                    errors.append(f"{spec.label_ru}: максимум {spec.max_value}" if lang == "ru" else f"{spec.label_en}: maximum {spec.max_value}")
            except (TypeError, ValueError):
                errors.append(f"{spec.label_ru}: должно быть число" if lang == "ru" else f"{spec.label_en}: must be a number")
    
    return errors


def get_defaults(model_id: str) -> Dict[str, Any]:
    """Get default values for a model's parameters."""
    schema = get_schema(model_id)
    if not schema:
        return {}
    
    defaults = {}
    for spec in schema.params:
        if spec.default is not None:
            defaults[spec.name] = spec.default
    return defaults


# =============================================================================
# REGISTER ALL MODEL SCHEMAS
# =============================================================================

# --- Text-to-Image Models ---

register_schema(ModelInputSchema(
    model_id="flux-2/pro-text-to-image",
    model_type="t2i",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 5000}),
        ASPECT_RATIO_PARAM,
        ParamSpec(
            name="resolution",
            label_ru="Разрешение",
            label_en="Resolution",
            type=ParamType.ENUM,
            required=True,
            default="1K",
            enum_values=["1K", "2K"],
            hint_ru="2K — детальнее, но дороже",
            hint_en="2K — more detailed, but pricier",
            error_ru="Выберите разрешение",
            error_en="Select resolution"
        ),
        SEED_PARAM,
    ],
    checklist_ru=["✏️ Промпт (детальное описание)", "📐 Соотношение сторон", "🎯 Разрешение 1K/2K"],
    checklist_en=["✏️ Prompt (detailed description)", "📐 Aspect ratio", "🎯 Resolution 1K/2K"],
    output_ru="Фотореалистичное изображение высокого качества",
    output_en="High-quality photorealistic image",
    typical_errors_ru=["Слишком короткий промпт", "Неподдерживаемое соотношение сторон"],
    typical_errors_en=["Prompt too short", "Unsupported aspect ratio"]
))

register_schema(ModelInputSchema(
    model_id="flux/kontext",
    model_type="t2i",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 5000}),
        ParamSpec(
            name="quality",
            label_ru="Качество",
            label_en="Quality",
            type=ParamType.ENUM,
            required=True,
            default="Pro",
            enum_values=["Pro", "Max"],
            hint_ru="Max — максимальная детализация",
            hint_en="Max — maximum detail",
            error_ru="Выберите качество: Pro или Max",
            error_en="Select quality: Pro or Max"
        ),
        IMAGE_URL_PARAM,
    ],
    checklist_ru=["🖼️ Исходное изображение", "✏️ Инструкция для редактирования", "⚡ Качество Pro/Max"],
    checklist_en=["🖼️ Source image", "✏️ Editing instructions", "⚡ Quality Pro/Max"],
    output_ru="Отредактированное изображение с пониманием контекста",
    output_en="Context-aware edited image"
))

register_schema(ModelInputSchema(
    model_id="midjourney/text-to-image",
    model_type="t2i",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 4000}),
        ParamSpec(
            name="speed",
            label_ru="Скорость",
            label_en="Speed",
            type=ParamType.ENUM,
            required=False,
            default="fast",
            enum_values=["relaxed", "fast", "turbo"],
            hint_ru="Relaxed — дешевле, Turbo — быстрее",
            hint_en="Relaxed — cheaper, Turbo — faster",
            error_ru="Выберите режим скорости",
            error_en="Select speed mode"
        ),
        ParamSpec(
            name="version",
            label_ru="Версия",
            label_en="Version",
            type=ParamType.ENUM,
            required=False,
            default="7",
            enum_values=["6", "6.1", "7", "niji6", "niji7"],
            hint_ru="v7 — новейшая, niji — аниме стиль",
            hint_en="v7 — newest, niji — anime style",
            error_ru="Выберите версию модели",
            error_en="Select model version"
        ),
        ParamSpec(
            name="aspect_ratio",
            label_ru="Соотношение сторон",
            label_en="Aspect ratio",
            type=ParamType.STRING,
            required=False,
            default="1:1",
            placeholder_ru="Например: 16:9, 4:3, 1:1",
            placeholder_en="Example: 16:9, 4:3, 1:1",
            hint_ru="Формат W:H, поддерживается любое соотношение",
            hint_en="Format W:H, any ratio supported",
            error_ru="Неверный формат (используйте W:H)",
            error_en="Invalid format (use W:H)"
        ),
    ],
    checklist_ru=["✏️ Промпт", "🎨 Версия (v7/niji)", "⏱️ Скорость (relaxed/fast/turbo)"],
    checklist_en=["✏️ Prompt", "🎨 Version (v7/niji)", "⏱️ Speed (relaxed/fast/turbo)"],
    output_ru="Арт в стиле Midjourney",
    output_en="Midjourney-style art"
))

# --- Text-to-Video Models ---

register_schema(ModelInputSchema(
    model_id="sora-2-pro-text-to-video",
    model_type="t2v",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 10000}),
        ParamSpec(
            name="n_frames",
            label_ru="Длительность",
            label_en="Duration",
            type=ParamType.ENUM,
            required=False,
            default="10",
            enum_values=["10", "15"],
            hint_ru="10 или 15 секунд видео",
            hint_en="10 or 15 seconds of video",
            error_ru="Выберите длительность",
            error_en="Select duration"
        ),
        ParamSpec(
            name="size",
            label_ru="Качество",
            label_en="Quality",
            type=ParamType.ENUM,
            required=False,
            default="standard",
            enum_values=["standard", "high"],
            hint_ru="High — кинематографическое качество",
            hint_en="High — cinematic quality",
            error_ru="Выберите качество",
            error_en="Select quality"
        ),
        ParamSpec(
            name="aspect_ratio",
            label_ru="Ориентация",
            label_en="Orientation",
            type=ParamType.ENUM,
            required=False,
            default="landscape",
            enum_values=["portrait", "landscape"],
            hint_ru="Portrait — вертикальное, Landscape — горизонтальное",
            hint_en="Portrait — vertical, Landscape — horizontal",
            error_ru="Выберите ориентацию",
            error_en="Select orientation"
        ),
        ParamSpec(
            name="remove_watermark",
            label_ru="Убрать водяной знак",
            label_en="Remove watermark",
            type=ParamType.BOOLEAN,
            required=False,
            default=False,
            hint_ru="Дополнительная плата за удаление",
            hint_en="Additional charge for removal",
            error_ru="",
            error_en=""
        ),
    ],
    checklist_ru=["✏️ Детальный сценарий", "⏱️ Длительность 10/15 сек", "🎬 Качество Standard/High"],
    checklist_en=["✏️ Detailed script", "⏱️ Duration 10/15 sec", "🎬 Quality Standard/High"],
    output_ru="Кинематографическое видео высокого качества",
    output_en="High-quality cinematic video",
    typical_errors_ru=["Промпт слишком абстрактный", "Запрос нарушает политику контента"],
    typical_errors_en=["Prompt too abstract", "Request violates content policy"]
))

register_schema(ModelInputSchema(
    model_id="kling-2.6/text-to-video",
    model_type="t2v",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 1000}),
        ParamSpec(
            name="duration",
            label_ru="Длительность",
            label_en="Duration",
            type=ParamType.ENUM,
            required=True,
            default="5",
            enum_values=["5", "10"],
            hint_ru="5 или 10 секунд",
            hint_en="5 or 10 seconds",
            error_ru="Выберите длительность",
            error_en="Select duration"
        ),
        ParamSpec(
            name="sound",
            label_ru="Со звуком",
            label_en="With sound",
            type=ParamType.BOOLEAN,
            required=True,
            default=False,
            hint_ru="Генерация звукового сопровождения (x2 цена)",
            hint_en="Generate audio track (2x price)",
            error_ru="",
            error_en=""
        ),
        ASPECT_RATIO_PARAM,
    ],
    checklist_ru=["✏️ Промпт", "⏱️ Длительность", "🔊 Нужен ли звук"],
    checklist_en=["✏️ Prompt", "⏱️ Duration", "🔊 Need audio?"],
    output_ru="Видео 5-10 секунд",
    output_en="5-10 second video"
))

register_schema(ModelInputSchema(
    model_id="wan/2-6-text-to-video",
    model_type="t2v",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 5000}),
        ParamSpec(
            name="duration",
            label_ru="Длительность",
            label_en="Duration",
            type=ParamType.ENUM,
            required=False,
            default="5",
            enum_values=["5", "10", "15"],
            hint_ru="До 15 секунд видео",
            hint_en="Up to 15 seconds of video",
            error_ru="Выберите длительность",
            error_en="Select duration"
        ),
        ParamSpec(
            name="resolution",
            label_ru="Разрешение",
            label_en="Resolution",
            type=ParamType.ENUM,
            required=False,
            default="720p",
            enum_values=["720p", "1080p"],
            hint_ru="1080p — выше качество, выше цена",
            hint_en="1080p — higher quality, higher price",
            error_ru="Выберите разрешение",
            error_en="Select resolution"
        ),
        ParamSpec(
            name="multi_shots",
            label_ru="Мультикадр",
            label_en="Multi-shots",
            type=ParamType.BOOLEAN,
            required=False,
            default=False,
            hint_ru="Несколько сцен в одном видео",
            hint_en="Multiple scenes in one video",
            error_ru="",
            error_en=""
        ),
    ],
    checklist_ru=["✏️ Промпт", "⏱️ Длительность 5/10/15 сек", "📺 Разрешение"],
    checklist_en=["✏️ Prompt", "⏱️ Duration 5/10/15 sec", "📺 Resolution"],
    output_ru="Видео до 15 секунд в HD",
    output_en="Video up to 15 seconds in HD"
))

# --- Music Generation ---

register_schema(ModelInputSchema(
    model_id="suno/v5",
    model_type="text_to_music",
    params=[
        ParamSpec(
            name="prompt",
            label_ru="Описание трека",
            label_en="Track description",
            type=ParamType.STRING,
            required=True,
            max_length=3000,
            placeholder_ru="Опишите стиль и настроение музыки...",
            placeholder_en="Describe the style and mood of the music...",
            hint_ru="Укажите жанр, инструменты, темп, настроение",
            hint_en="Specify genre, instruments, tempo, mood",
            error_ru="Введите описание трека",
            error_en="Enter track description",
            example="Upbeat electronic dance music with synths and driving bass"
        ),
        ParamSpec(
            name="style",
            label_ru="Стиль",
            label_en="Style",
            type=ParamType.STRING,
            required=False,
            max_length=500,
            placeholder_ru="pop, rock, electronic...",
            placeholder_en="pop, rock, electronic...",
            hint_ru="Музыкальный жанр или стиль",
            hint_en="Music genre or style",
            error_ru="",
            error_en=""
        ),
        ParamSpec(
            name="instrumental",
            label_ru="Инструментал",
            label_en="Instrumental",
            type=ParamType.BOOLEAN,
            required=False,
            default=False,
            hint_ru="Без вокала",
            hint_en="No vocals",
            error_ru="",
            error_en=""
        ),
    ],
    checklist_ru=["🎵 Описание стиля/настроения", "🎸 Нужен ли вокал"],
    checklist_en=["🎵 Style/mood description", "🎸 Need vocals?"],
    output_ru="Музыкальный трек ~2 минуты",
    output_en="Music track ~2 minutes"
))


# --- Image-to-Video Models ---

register_schema(ModelInputSchema(
    model_id="wan/2-5-image-to-video",
    model_type="i2v",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 800}),
        ParamSpec(
            name="image_url",
            label_ru="Исходное изображение",
            label_en="Source image",
            type=ParamType.FILE_URL,
            required=True,
            placeholder_ru="Загрузите фото",
            placeholder_en="Upload a photo",
            hint_ru="Фото станет первым кадром видео",
            hint_en="Photo will be the first frame",
            error_ru="Загрузите изображение",
            error_en="Upload an image"
        ),
        ParamSpec(
            name="duration",
            label_ru="Длительность",
            label_en="Duration",
            type=ParamType.ENUM,
            required=False,
            default="5",
            enum_values=["5", "10"],
            hint_ru="5 или 10 секунд",
            hint_en="5 or 10 seconds",
            error_ru="Выберите длительность",
            error_en="Select duration"
        ),
        ParamSpec(
            name="resolution",
            label_ru="Разрешение",
            label_en="Resolution",
            type=ParamType.ENUM,
            required=False,
            default="1080p",
            enum_values=["720p", "1080p"],
            hint_ru="1080p — выше качество",
            hint_en="1080p — higher quality",
            error_ru="Выберите разрешение",
            error_en="Select resolution"
        ),
    ],
    checklist_ru=["🖼️ Исходное фото", "✏️ Описание движения", "⏱️ Длительность"],
    checklist_en=["🖼️ Source photo", "✏️ Motion description", "⏱️ Duration"],
    output_ru="Видео 5-10 секунд из вашего фото",
    output_en="5-10 second video from your photo"
))

register_schema(ModelInputSchema(
    model_id="wan/2-6-image-to-video",
    model_type="i2v",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 5000}),
        ParamSpec(
            name="image_urls",
            label_ru="Изображения",
            label_en="Images",
            type=ParamType.FILE_URLS,
            required=True,
            max_items=2,
            placeholder_ru="Загрузите 1-2 фото",
            placeholder_en="Upload 1-2 photos",
            hint_ru="Первое фото = начало, второе = конец",
            hint_en="First photo = start, second = end",
            error_ru="Загрузите хотя бы 1 изображение",
            error_en="Upload at least 1 image"
        ),
        ParamSpec(
            name="duration",
            label_ru="Длительность",
            label_en="Duration",
            type=ParamType.ENUM,
            required=False,
            default="5",
            enum_values=["5", "10", "15"],
            hint_ru="До 15 секунд",
            hint_en="Up to 15 seconds",
            error_ru="Выберите длительность",
            error_en="Select duration"
        ),
        ParamSpec(
            name="resolution",
            label_ru="Разрешение",
            label_en="Resolution",
            type=ParamType.ENUM,
            required=False,
            default="1080p",
            enum_values=["720p", "1080p"],
            hint_ru="1080p — выше качество, выше цена",
            hint_en="1080p — higher quality, higher price",
            error_ru="Выберите разрешение",
            error_en="Select resolution"
        ),
    ],
    checklist_ru=["🖼️ 1-2 изображения", "✏️ Описание", "⏱️ Длительность"],
    checklist_en=["🖼️ 1-2 images", "✏️ Description", "⏱️ Duration"],
    output_ru="Видео до 15 секунд в HD",
    output_en="Video up to 15 seconds in HD"
))

register_schema(ModelInputSchema(
    model_id="kling-2.6/image-to-video",
    model_type="i2v",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 1000, "required": False}),
        ParamSpec(
            name="image_url",
            label_ru="Исходное изображение",
            label_en="Source image",
            type=ParamType.FILE_URL,
            required=True,
            hint_ru="Фото станет основой видео",
            hint_en="Photo will be the video base",
            error_ru="Загрузите изображение",
            error_en="Upload an image"
        ),
        ParamSpec(
            name="duration",
            label_ru="Длительность",
            label_en="Duration",
            type=ParamType.ENUM,
            required=True,
            default="5",
            enum_values=["5", "10"],
            hint_ru="5 или 10 секунд",
            hint_en="5 or 10 seconds",
            error_ru="Выберите длительность",
            error_en="Select duration"
        ),
        ParamSpec(
            name="sound",
            label_ru="Со звуком",
            label_en="With sound",
            type=ParamType.BOOLEAN,
            required=True,
            default=False,
            hint_ru="Генерация звука (x2 цена)",
            hint_en="Audio generation (2x price)",
            error_ru="",
            error_en=""
        ),
    ],
    checklist_ru=["🖼️ Исходное фото", "⏱️ Длительность", "🔊 Нужен ли звук"],
    checklist_en=["🖼️ Source photo", "⏱️ Duration", "🔊 Need audio?"],
    output_ru="Видео 5-10 секунд",
    output_en="5-10 second video"
))

# --- Free Models ---

register_schema(ModelInputSchema(
    model_id="z-image",
    model_type="t2i",
    params=[
        ParamSpec(**{**PROMPT_PARAM.__dict__, "max_length": 1000}),
        ParamSpec(
            name="aspect_ratio",
            label_ru="Соотношение сторон",
            label_en="Aspect ratio",
            type=ParamType.ENUM,
            required=True,
            default="1:1",
            enum_values=["1:1", "4:3", "3:4", "16:9", "9:16"],
            hint_ru="1:1 — квадрат, 16:9 — широкий",
            hint_en="1:1 — square, 16:9 — wide",
            error_ru="Выберите формат",
            error_en="Select format"
        ),
    ],
    checklist_ru=["✏️ Промпт", "📐 Соотношение сторон"],
    checklist_en=["✏️ Prompt", "📐 Aspect ratio"],
    output_ru="Бесплатное изображение",
    output_en="Free image"
))


# =============================================================================
# BOT INTEGRATION FUNCTIONS
# =============================================================================

def get_param_spec(model_id: str, param_name: str) -> Optional[ParamSpec]:
    """Get specification for a specific parameter."""
    schema = get_schema(model_id)
    if not schema:
        return None
    for spec in schema.params:
        if spec.name == param_name:
            return spec
    return None


def get_param_hint(model_id: str, param_name: str, lang: str = "ru") -> str:
    """Get hint text for a parameter."""
    spec = get_param_spec(model_id, param_name)
    if not spec:
        return ""
    return spec.hint_ru if lang == "ru" else spec.hint_en


def get_param_label(model_id: str, param_name: str, lang: str = "ru") -> str:
    """Get human-readable label for a parameter."""
    spec = get_param_spec(model_id, param_name)
    if not spec:
        # Fallback: humanize param name
        return param_name.replace("_", " ").title()
    return spec.label_ru if lang == "ru" else spec.label_en


def get_param_placeholder(model_id: str, param_name: str, lang: str = "ru") -> str:
    """Get placeholder text for a parameter."""
    spec = get_param_spec(model_id, param_name)
    if not spec:
        return ""
    return spec.placeholder_ru if lang == "ru" else spec.placeholder_en


def get_param_error(model_id: str, param_name: str, lang: str = "ru") -> str:
    """Get error message for a parameter."""
    spec = get_param_spec(model_id, param_name)
    if not spec:
        return "Неверное значение" if lang == "ru" else "Invalid value"
    err = spec.error_ru if lang == "ru" else spec.error_en
    return err.format(
        max=spec.max_length or spec.max_value or 0,
        min=spec.min_length or spec.min_value or 0
    )


def get_model_checklist(model_id: str, lang: str = "ru") -> List[str]:
    """Get pre-generation checklist for a model."""
    schema = get_schema(model_id)
    if not schema:
        return []
    return schema.checklist_ru if lang == "ru" else schema.checklist_en


def get_model_output_description(model_id: str, lang: str = "ru") -> str:
    """Get description of what user will receive."""
    schema = get_schema(model_id)
    if not schema:
        return ""
    return schema.output_ru if lang == "ru" else schema.output_en


def build_param_prompt_text(
    model_id: str,
    param_name: str,
    lang: str = "ru",
    include_hint: bool = True,
    include_example: bool = True
) -> str:
    """Build prompt text for parameter input in bot."""
    spec = get_param_spec(model_id, param_name)
    if not spec:
        label = param_name.replace("_", " ").title()
        return f"📝 <b>{label}</b>\n\nВведите значение:" if lang == "ru" else f"📝 <b>{label}</b>\n\nEnter value:"
    
    label = spec.label_ru if lang == "ru" else spec.label_en
    lines = [f"📝 <b>{label}</b>"]
    
    # Add hint
    if include_hint:
        hint = spec.hint_ru if lang == "ru" else spec.hint_en
        if hint:
            lines.append(f"\n💡 {hint}")
    
    # Add constraints info
    if spec.type == ParamType.ENUM and spec.enum_values:
        values_str = ", ".join(spec.enum_values[:5])
        if len(spec.enum_values) > 5:
            values_str += "..."
        lines.append(f"\nℹ️ {"Доступные значения" if lang == "ru" else "Available values"}: {values_str}")
    elif spec.type == ParamType.STRING:
        if spec.max_length:
            lines.append(f"\n📏 {"Максимум" if lang == "ru" else "Maximum"}: {spec.max_length} {"символов" if lang == "ru" else "characters"}")
    
    # Add example
    if include_example and spec.example:
        lines.append(f"\n🧪 {"Пример" if lang == "ru" else "Example"}: {spec.example[:100]}")
    
    # Add default info
    if spec.default is not None:
        lines.append(f"\n⏭️ {"По умолчанию" if lang == "ru" else "Default"}: {spec.default}")
    
    return "".join(lines)


def normalize_param_value(model_id: str, param_name: str, value: Any) -> Any:
    """
    Normalize parameter value according to schema.
    Returns normalized value or None if invalid.
    """
    spec = get_param_spec(model_id, param_name)
    if not spec:
        return value
    
    # String normalization
    if spec.type == ParamType.STRING:
        if value is None:
            return spec.default
        return str(value).strip()
    
    # Enum normalization
    if spec.type == ParamType.ENUM:
        if value is None:
            return spec.default
        str_value = str(value).strip()
        # Case-insensitive match
        if spec.enum_values:
            for enum_val in spec.enum_values:
                if str_value.lower() == enum_val.lower():
                    return enum_val
        return str_value
    
    # Number normalization
    if spec.type in (ParamType.NUMBER, ParamType.INTEGER):
        if value is None:
            return spec.default
        try:
            if spec.type == ParamType.INTEGER:
                return int(float(str(value).strip()))
            return float(str(value).strip())
        except (ValueError, TypeError):
            return spec.default
    
    # Boolean normalization
    if spec.type == ParamType.BOOLEAN:
        if value is None:
            return spec.default
        if isinstance(value, bool):
            return value
        str_value = str(value).strip().lower()
        if str_value in ("true", "1", "yes", "да", "on"):
            return True
        if str_value in ("false", "0", "no", "нет", "off"):
            return False
        return spec.default
    
    return value


# =============================================================================
# AUTO-GENERATE SCHEMAS FROM kie_models.yaml
# =============================================================================

# UX Labels for parameters (human-readable)
PARAM_LABELS = {
    "prompt": {"ru": "Описание", "en": "Description"},
    "text": {"ru": "Текст", "en": "Text"},
    "negative_prompt": {"ru": "Негативный промпт", "en": "Negative prompt"},
    "aspect_ratio": {"ru": "Формат", "en": "Format"},
    "image_size": {"ru": "Размер изображения", "en": "Image size"},
    "image_input": {"ru": "Изображение", "en": "Image"},
    "image_urls": {"ru": "Изображения", "en": "Images"},
    "video_input": {"ru": "Видео", "en": "Video"},
    "video_url": {"ru": "Видео", "en": "Video"},
    "audio_input": {"ru": "Аудио", "en": "Audio"},
    "duration": {"ru": "Длительность", "en": "Duration"},
    "resolution": {"ru": "Разрешение", "en": "Resolution"},
    "quality": {"ru": "Качество", "en": "Quality"},
    "style": {"ru": "Стиль", "en": "Style"},
    "seed": {"ru": "Сид (воспроизводимость)", "en": "Seed (reproducibility)"},
    "guidance_scale": {"ru": "Точность следования", "en": "Guidance scale"},
    "cfg_scale": {"ru": "Точность следования", "en": "CFG scale"},
    "num_images": {"ru": "Количество изображений", "en": "Number of images"},
    "max_images": {"ru": "Количество изображений", "en": "Number of images"},
    "upscale_factor": {"ru": "Коэффициент увеличения", "en": "Upscale factor"},
    "enable_safety_checker": {"ru": "Фильтр контента", "en": "Safety filter"},
    "sound": {"ru": "Со звуком", "en": "With sound"},
    "multi_shots": {"ru": "Мульти-ракурсы", "en": "Multi shots"},
    "n_frames": {"ru": "Количество кадров", "en": "Frame count"},
    "remove_watermark": {"ru": "Убрать водяной знак", "en": "Remove watermark"},
    "rendering_speed": {"ru": "Скорость рендера", "en": "Rendering speed"},
    "output_format": {"ru": "Формат файла", "en": "Output format"},
    "image_resolution": {"ru": "Разрешение", "en": "Resolution"},
    "prompt_optimizer": {"ru": "Оптимизация промпта", "en": "Prompt optimizer"},
    "end_image_url": {"ru": "Конечное изображение", "en": "End image"},
    "mode": {"ru": "Режим", "en": "Mode"},
    "character_orientation": {"ru": "Ориентация персонажа", "en": "Character orientation"},
    "input_urls": {"ru": "Входное изображение", "en": "Input image"},
    "video_urls": {"ru": "Референсное видео", "en": "Reference video"},
    "enable_prompt_expansion": {"ru": "Расширение промпта", "en": "Prompt expansion"},
    "num_inference_steps": {"ru": "Шаги генерации", "en": "Inference steps"},
    "frames_per_second": {"ru": "Кадров в секунду", "en": "Frames per second"},
    "num_frames": {"ru": "Количество кадров", "en": "Number of frames"},
    "shift": {"ru": "Сдвиг", "en": "Shift"},
    "mask_input": {"ru": "Маска", "en": "Mask"},
    "reference_image_input": {"ru": "Референс", "en": "Reference"},
}

# UX Hints for parameters
PARAM_HINTS = {
    "prompt": {"ru": "Чем детальнее описание, тем лучше результат", "en": "More detail = better results"},
    "negative_prompt": {"ru": "Что НЕ должно быть на изображении", "en": "What should NOT appear"},
    "aspect_ratio": {"ru": "1:1=квадрат, 16:9=широкий, 9:16=вертикальный", "en": "1:1=square, 16:9=wide, 9:16=vertical"},
    "duration": {"ru": "Длительность видео в секундах", "en": "Video duration in seconds"},
    "resolution": {"ru": "Выше разрешение = дороже", "en": "Higher resolution = more expensive"},
    "quality": {"ru": "Выше качество = дороже", "en": "Higher quality = more expensive"},
    "guidance_scale": {"ru": "Выше = точнее следует промпту", "en": "Higher = follows prompt more closely"},
    "sound": {"ru": "Генерация звука удваивает цену", "en": "Audio generation doubles the price"},
    "upscale_factor": {"ru": "Во сколько раз увеличить", "en": "How many times to enlarge"},
    "enable_safety_checker": {"ru": "Фильтрует неприемлемый контент", "en": "Filters inappropriate content"},
    "image_input": {"ru": "Отправьте фото или ссылку", "en": "Send a photo or URL"},
    "audio_input": {"ru": "Отправьте аудио файл", "en": "Send an audio file"},
    "video_input": {"ru": "Отправьте видео файл", "en": "Send a video file"},
}

# Model type to output description
MODEL_TYPE_OUTPUT = {
    "text_to_image": {"ru": "Изображение", "en": "Image"},
    "image_to_image": {"ru": "Изображение", "en": "Image"},
    "image_edit": {"ru": "Отредактированное изображение", "en": "Edited image"},
    "text_to_video": {"ru": "Видео", "en": "Video"},
    "image_to_video": {"ru": "Видео из фото", "en": "Video from photo"},
    "video_editing": {"ru": "Отредактированное видео", "en": "Edited video"},
    "video_upscale": {"ru": "Улучшенное видео", "en": "Upscaled video"},
    "upscale": {"ru": "Увеличенное изображение", "en": "Upscaled image"},
    "lip_sync": {"ru": "Видео с синхронизацией губ", "en": "Lip-synced video"},
    "speech_to_video": {"ru": "Говорящее видео", "en": "Talking video"},
    "bg_remove": {"ru": "Изображение без фона", "en": "Image without background"},
    "outpaint": {"ru": "Расширенное изображение", "en": "Extended image"},
    "t2i": {"ru": "Изображение", "en": "Image"},
    "i2i": {"ru": "Изображение", "en": "Image"},
    "t2v": {"ru": "Видео", "en": "Video"},
    "i2v": {"ru": "Видео из фото", "en": "Video from photo"},
}


def _yaml_type_to_param_type(yaml_type: str, is_array: bool = False) -> ParamType:
    """Convert YAML type to ParamType."""
    if is_array or yaml_type == "array":
        return ParamType.FILE_URLS
    mapping = {
        "string": ParamType.STRING,
        "number": ParamType.NUMBER,
        "integer": ParamType.INTEGER,
        "boolean": ParamType.BOOLEAN,
        "enum": ParamType.ENUM,
    }
    return mapping.get(yaml_type, ParamType.STRING)


def _build_param_spec_from_yaml(name: str, param_def: dict) -> ParamSpec:
    """Build ParamSpec from YAML parameter definition."""
    yaml_type = param_def.get("type", "string")
    is_array = yaml_type == "array"
    
    # Determine ParamType
    if param_def.get("values"):
        ptype = ParamType.ENUM
    elif is_array:
        ptype = ParamType.FILE_URLS
    else:
        ptype = _yaml_type_to_param_type(yaml_type)
    
    # Get labels
    labels = PARAM_LABELS.get(name, {"ru": name.replace("_", " ").title(), "en": name.replace("_", " ").title()})
    hints = PARAM_HINTS.get(name, {"ru": "", "en": ""})
    
    return ParamSpec(
        name=name,
        label_ru=labels["ru"],
        label_en=labels["en"],
        type=ptype,
        required=param_def.get("required", False),
        default=param_def.get("default"),
        min_value=param_def.get("min"),
        max_value=param_def.get("max"),
        max_length=param_def.get("max") if yaml_type == "string" else None,
        enum_values=param_def.get("values"),
        max_items=param_def.get("max_items"),
        hint_ru=hints["ru"],
        hint_en=hints["en"],
        error_ru=f"Неверное значение для {labels['ru']}",
        error_en=f"Invalid value for {labels['en']}",
    )


def auto_register_schemas_from_yaml():
    """
    Auto-register schemas for all models from kie_models.yaml.
    This is called at module load time.
    """
    import os
    import yaml
    
    # Find kie_models.yaml relative to this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_paths = [
        os.path.join(current_dir, "..", "..", "models", "kie_models.yaml"),
        os.path.join(current_dir, "..", "..", "..", "models", "kie_models.yaml"),
    ]
    
    yaml_path = None
    for path in yaml_paths:
        if os.path.exists(path):
            yaml_path = path
            break
    
    if not yaml_path:
        return  # YAML not found, skip auto-registration
    
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return
    
    models = data.get("models", {})
    
    for model_id, model_def in models.items():
        # Skip if already registered
        if model_id in MODEL_SCHEMAS:
            continue
        
        model_type = model_def.get("model_type", model_def.get("model_mode", "unknown"))
        input_params = model_def.get("input", {})
        
        # Build params list
        params = []
        for param_name, param_def in input_params.items():
            if isinstance(param_def, dict):
                params.append(_build_param_spec_from_yaml(param_name, param_def))
        
        # Get output description
        output_desc = MODEL_TYPE_OUTPUT.get(model_type, {"ru": "Результат", "en": "Result"})
        
        # Build checklist from required params
        checklist_ru = []
        checklist_en = []
        for p in params:
            if p.required:
                labels = PARAM_LABELS.get(p.name, {"ru": p.name, "en": p.name})
                emoji = "✏️" if p.name in ("prompt", "text") else "🖼️" if "image" in p.name else "🎵" if "audio" in p.name else "📹" if "video" in p.name else "⚙️"
                checklist_ru.append(f"{emoji} {labels['ru']}")
                checklist_en.append(f"{emoji} {labels['en']}")
        
        # Register schema
        schema = ModelInputSchema(
            model_id=model_id,
            model_type=model_type,
            params=params,
            checklist_ru=checklist_ru,
            checklist_en=checklist_en,
            output_ru=output_desc["ru"],
            output_en=output_desc["en"],
        )
        MODEL_SCHEMAS[model_id] = schema


# Auto-register on module load
auto_register_schemas_from_yaml()


def get_all_model_ids() -> List[str]:
    """Get list of all registered model IDs."""
    return list(MODEL_SCHEMAS.keys())


def get_ux_schema_for_webapp(model_id: str, lang: str = "ru") -> Optional[Dict[str, Any]]:
    """
    Get UX schema for Mini App / webapp.
    Returns dict with fields, validation rules, and UX metadata.
    """
    schema = get_schema(model_id)
    if not schema:
        return None
    
    fields = []
    for spec in schema.params:
        field = {
            "name": spec.name,
            "label": spec.label_ru if lang == "ru" else spec.label_en,
            "type": spec.type.value,
            "required": spec.required,
            "hint": spec.hint_ru if lang == "ru" else spec.hint_en,
            "placeholder": spec.placeholder_ru if lang == "ru" else spec.placeholder_en,
            "error": spec.error_ru if lang == "ru" else spec.error_en,
            "advanced": spec.advanced,
        }
        
        # Add constraints
        if spec.default is not None:
            field["default"] = spec.default
        if spec.enum_values:
            field["options"] = spec.enum_values
        if spec.min_value is not None:
            field["min"] = spec.min_value
        if spec.max_value is not None:
            field["max"] = spec.max_value
        if spec.max_length is not None:
            field["maxLength"] = spec.max_length
        if spec.max_items is not None:
            field["maxItems"] = spec.max_items
        if spec.example:
            field["example"] = spec.example
        
        fields.append(field)
    
    return {
        "model_id": model_id,
        "model_type": schema.model_type,
        "fields": fields,
        "checklist": schema.checklist_ru if lang == "ru" else schema.checklist_en,
        "output": schema.output_ru if lang == "ru" else schema.output_en,
    }


# Export for easy access
__all__ = [
    "ParamType",
    "ParamSpec", 
    "ModelInputSchema",
    "MODEL_SCHEMAS",
    "register_schema",
    "get_schema",
    "validate_input",
    "get_defaults",
    # Bot integration
    "get_param_spec",
    "get_param_hint",
    "get_param_label",
    "get_param_placeholder",
    "get_param_error",
    "get_model_checklist",
    "get_model_output_description",
    "build_param_prompt_text",
    "normalize_param_value",
    # Auto-gen
    "auto_register_schemas_from_yaml",
    "get_all_model_ids",
    "get_ux_schema_for_webapp",
    # Common params
    "PROMPT_PARAM",
    "NEGATIVE_PROMPT_PARAM",
    "ASPECT_RATIO_PARAM",
    "IMAGE_URL_PARAM",
    "DURATION_PARAM",
    "RESOLUTION_PARAM",
    "QUALITY_PARAM",
    "SEED_PARAM",
]
