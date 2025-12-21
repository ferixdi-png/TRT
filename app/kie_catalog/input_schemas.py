"""
Схемы входных параметров для каждого типа модели KIE AI.
Whitelist разрешённых полей для каждого типа.
"""

from typing import Dict, Set, List, Optional

# Whitelist разрешённых полей для каждого типа модели
INPUT_SCHEMAS: Dict[str, Set[str]] = {
    # Text-to-Image
    't2i': {
        'prompt',
        'negative_prompt',
        'width',
        'height',
        'steps',
        'seed',
        'guidance',
        'style',
        'image_count',
        'aspect_ratio',
        'quality',
        'resolution',
        'model',
        'mode'
    },
    
    # Image-to-Image
    'i2i': {
        'prompt',
        'image_url',
        'image_base64',
        'image',
        'strength',
        'width',
        'height',
        'seed',
        'steps',
        'guidance',
        'negative_prompt',
        'style',
        'mode',
        'quality'
    },
    
    # Text-to-Video
    't2v': {
        'prompt',
        'duration',
        'fps',
        'resolution',
        'seed',
        'with_audio',
        'width',
        'height',
        'guidance',
        'steps',
        'negative_prompt',
        'motion',
        'style',
        'aspect_ratio'
    },
    
    # Image-to-Video
    'i2v': {
        'image_url',
        'image_base64',
        'image',
        'prompt',
        'duration',
        'resolution',
        'with_audio',
        'fps',
        'seed',
        'strength',
        'width',
        'height',
        'guidance',
        'motion',
        'style'
    },
    
    # Video-to-Video
    'v2v': {
        'video_url',
        'video',
        'prompt',
        'duration',
        'resolution',
        'fps',
        'seed',
        'strength',
        'with_audio',
        'guidance',
        'motion',
        'style'
    },
    
    # Text-to-Speech
    'tts': {
        'text',
        'voice',
        'language',
        'speed',
        'model',
        'style',
        'emotion'
    },
    
    # Speech-to-Text
    'stt': {
        'audio_url',
        'audio',
        'language',
        'model',
        'format'
    },
    
    # Sound Effects
    'sfx': {
        'prompt',
        'duration',
        'style',
        'seed'
    },
    
    # Audio Isolation
    'audio_isolation': {
        'audio_url',
        'audio',
        'mode',
        'strength'
    },
    
    # Upscale
    'upscale': {
        'image_url',
        'image_base64',
        'image',
        'scale',
        'upscale_factor',
        'model',
        'quality'
    },
    
    # Background Remove
    'bg_remove': {
        'image_url',
        'image_base64',
        'image'
    },
    
    # Watermark Remove
    'watermark_remove': {
        'image_url',
        'image_base64',
        'image',
        'strength'
    },
    
    # Music Generation
    'music': {
        'prompt',
        'duration',
        'style',
        'tempo',
        'seed',
        'model',
        'format'
    },
    
    # Lip Sync
    'lip_sync': {
        'video_url',
        'video',
        'audio_url',
        'audio',
        'image_url',
        'image',
        'resolution',
        'model'
    }
}

# Критичные обязательные поля для каждого типа
REQUIRED_FIELDS: Dict[str, Set[str]] = {
    't2i': {'prompt'},
    'i2i': {'image_url', 'image_base64', 'image'},  # Хотя бы одно
    't2v': {'prompt'},
    'i2v': {'image_url', 'image_base64', 'image'},  # Хотя бы одно
    'v2v': {'video_url', 'video'},  # Хотя бы одно
    'tts': {'text'},
    'stt': {'audio_url', 'audio'},  # Хотя бы одно
    'sfx': {'prompt'},
    'audio_isolation': {'audio_url', 'audio'},  # Хотя бы одно
    'upscale': {'image_url', 'image_base64', 'image'},  # Хотя бы одно
    'bg_remove': {'image_url', 'image_base64', 'image'},  # Хотя бы одно
    'watermark_remove': {'image_url', 'image_base64', 'image'},  # Хотя бы одно
    'music': {'prompt'},
    'lip_sync': {'video_url', 'video', 'image_url', 'image'}  # Хотя бы одно из каждой группы
}

# Алиасы для нормализации полей
FIELD_ALIASES: Dict[str, str] = {
    # Image aliases
    'img': 'image_url',
    'image_input': 'image_url',
    'input_image': 'image_url',
    'photo': 'image_url',
    
    # Video aliases
    'vid': 'video_url',
    'video_input': 'video_url',
    'input_video': 'video_url',
    
    # Audio aliases
    'audio_input': 'audio_url',
    'input_audio': 'audio_url',
    
    # Prompt aliases
    'neg': 'negative_prompt',
    'neg_prompt': 'negative_prompt',
    'negative': 'negative_prompt',
    
    # Other aliases
    'scale_factor': 'scale',
    'upscale_scale': 'scale',
    'fps_value': 'fps',
    'duration_seconds': 'duration',
    'audio_enabled': 'with_audio',
    'has_audio': 'with_audio'
}

# Дефолтные значения для полей (если не указаны)
DEFAULT_VALUES: Dict[str, Dict[str, any]] = {
    't2i': {
        'width': 1024,
        'height': 1024,
        'steps': 20,
        'guidance': 7.5
    },
    'i2i': {
        'strength': 0.75,
        'width': 1024,
        'height': 1024
    },
    't2v': {
        'duration': 5.0,
        'fps': 24,
        'with_audio': False
    },
    'i2v': {
        'duration': 5.0,
        'fps': 24,
        'with_audio': False
    },
    'v2v': {
        'with_audio': False
    },
    'tts': {
        'speed': 1.0
    },
    'stt': {},
    'sfx': {
        'duration': 5.0
    },
    'audio_isolation': {},
    'upscale': {
        'scale': 2
    },
    'bg_remove': {},
    'watermark_remove': {
        'strength': 0.5
    },
    'music': {
        'duration': 30.0
    },
    'lip_sync': {
        'resolution': '720p'
    }
}


def get_schema_for_type(model_type: str) -> Set[str]:
    """
    Получает whitelist разрешённых полей для типа модели.
    
    Args:
        model_type: Тип модели (t2i, i2i, t2v, и т.д.)
    
    Returns:
        Множество разрешённых полей
    """
    return INPUT_SCHEMAS.get(model_type, set())


def get_required_fields_for_type(model_type: str) -> Set[str]:
    """
    Получает обязательные поля для типа модели.
    
    Args:
        model_type: Тип модели
    
    Returns:
        Множество обязательных полей
    """
    return REQUIRED_FIELDS.get(model_type, set())


def normalize_field_name(field_name: str) -> str:
    """
    Нормализует имя поля через алиасы.
    
    Args:
        field_name: Исходное имя поля
    
    Returns:
        Нормализованное имя поля
    """
    return FIELD_ALIASES.get(field_name, field_name)


def get_default_value(model_type: str, field_name: str) -> Optional[any]:
    """
    Получает дефолтное значение для поля типа модели.
    
    Args:
        model_type: Тип модели
        field_name: Имя поля
    
    Returns:
        Дефолтное значение или None
    """
    defaults = DEFAULT_VALUES.get(model_type, {})
    return defaults.get(field_name)

