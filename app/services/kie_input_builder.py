"""
Builder для входных параметров KIE AI API.
Собирает input строго по типу модели, валидирует и нормализует.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple, List
from app.kie_catalog.catalog import ModelSpec, ModelMode
from app.kie_catalog.input_schemas import (
    get_schema_for_type,
    get_required_fields_for_type,
    normalize_field_name,
    get_default_value
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def _parse_duration_from_notes(notes: Optional[str]) -> Optional[float]:
    """
    Парсит duration из notes (например "5.0s" -> 5.0).
    
    Args:
        notes: Строка с notes режима
    
    Returns:
        Duration в секундах или None
    """
    if not notes:
        return None
    
    # Ищем паттерны типа "5.0s", "10.0s", "5s", "10s"
    match = re.search(r'(\d+\.?\d*)s', notes, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    
    return None


def _parse_resolution_from_notes(notes: Optional[str]) -> Optional[str]:
    """
    Парсит resolution из notes (например "720p", "1080p").
    
    Args:
        notes: Строка с notes режима
    
    Returns:
        Resolution или None
    """
    if not notes:
        return None
    
    # Ищем паттерны типа "720p", "1080p", "1K", "2K", "4K"
    match = re.search(r'(\d+p|\d+K)', notes, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    
    return None


def _check_required_fields(
    model_type: str,
    input_data: Dict[str, Any],
    required_fields: Set[str]
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет наличие обязательных полей.
    
    Args:
        model_type: Тип модели
        input_data: Входные данные
        required_fields: Множество обязательных полей
    
    Returns:
        (is_valid, error_message)
    """
    if not required_fields:
        return True, None
    
    # Для полей типа image_url/image_base64/image проверяем хотя бы одно
    image_fields = {'image_url', 'image_base64', 'image'}
    video_fields = {'video_url', 'video'}
    audio_fields = {'audio_url', 'audio'}
    
    # Проверяем группы полей
    if image_fields.intersection(required_fields):
        has_image = any(
            input_data.get(field) for field in image_fields
            if field in input_data and input_data[field]
        )
        if not has_image:
            if model_type == 'i2i':
                return False, "Нужно загрузить изображение для генерации"
            elif model_type == 'i2v':
                return False, "Нужно загрузить изображение для создания видео"
            elif model_type in ['upscale', 'bg_remove', 'watermark_remove']:
                return False, "Нужно загрузить изображение"
    
    if video_fields.intersection(required_fields):
        has_video = any(
            input_data.get(field) for field in video_fields
            if field in input_data and input_data[field]
        )
        if not has_video:
            if model_type == 'v2v':
                return False, "Нужно загрузить видео"
            elif model_type == 'lip_sync':
                return False, "Нужно загрузить видео или изображение"
    
    if audio_fields.intersection(required_fields):
        has_audio = any(
            input_data.get(field) for field in audio_fields
            if field in input_data and input_data[field]
        )
        if not has_audio:
            if model_type == 'stt':
                return False, "Нужно загрузить аудио"
            elif model_type == 'audio_isolation':
                return False, "Нужно загрузить аудио"
            elif model_type == 'lip_sync':
                return False, "Нужно загрузить аудио"
    
    # Проверяем остальные обязательные поля
    for field in required_fields:
        if field in image_fields or field in video_fields or field in audio_fields:
            continue  # Уже проверили выше
        
        if field not in input_data or not input_data[field]:
            if field == 'prompt':
                return False, "Введите текст для генерации"
            elif field == 'text':
                return False, "Введите текст для синтеза речи"
            else:
                return False, f"Поле '{field}' обязательно"
    
    return True, None


def build_input(
    model_spec: ModelSpec,
    user_payload: Dict[str, Any],
    mode_index: int = 0
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Строит input для KIE API на основе типа модели и пользовательских данных.
    
    Args:
        model_spec: Спецификация модели из каталога
        user_payload: Пользовательские данные (сырые параметры)
        mode_index: Индекс режима (для извлечения дефолтов из notes)
    
    Returns:
        (input_dict, error_message) где error_message - None если всё ок
    """
    model_type = model_spec.type
    model_id = model_spec.id
    
    # Получаем whitelist и обязательные поля
    allowed_fields = get_schema_for_type(model_type)
    required_fields = get_required_fields_for_type(model_type)
    
    if not allowed_fields:
        logger.warning(f"No schema for model type: {model_type}, model_id: {model_id}")
        # Fallback: разрешаем все поля если схема не найдена
        allowed_fields = set(user_payload.keys())
    
    # Нормализуем и фильтруем поля
    normalized_input: Dict[str, Any] = {}
    
    for key, value in user_payload.items():
        # Нормализуем имя поля через алиасы
        normalized_key = normalize_field_name(key)
        
        # Проверяем что поле разрешено
        if normalized_key not in allowed_fields:
            logger.debug(f"Field '{key}' (normalized: '{normalized_key}') not in whitelist for type {model_type}, skipping")
            continue
        
        # Обрабатываем специальные случаи
        if normalized_key in ['image_url', 'image_base64', 'image']:
            # Если это список, берём первый элемент
            if isinstance(value, list) and len(value) > 0:
                value = value[0]
            # Если пустая строка или None, пропускаем
            if not value:
                continue
        
        if normalized_key in ['video_url', 'video']:
            if isinstance(value, list) and len(value) > 0:
                value = value[0]
            if not value:
                continue
        
        if normalized_key in ['audio_url', 'audio']:
            if isinstance(value, list) and len(value) > 0:
                value = value[0]
            if not value:
                continue
        
        normalized_input[normalized_key] = value
    
    # Применяем дефолты из схемы
    for field_name in allowed_fields:
        if field_name not in normalized_input:
            default_value = get_default_value(model_type, field_name)
            if default_value is not None:
                normalized_input[field_name] = default_value
    
    # Извлекаем дефолты из notes режима
    if mode_index < len(model_spec.modes):
        mode = model_spec.modes[mode_index]
        if mode.notes:
            # Парсим duration из notes
            if 'duration' not in normalized_input:
                duration = _parse_duration_from_notes(mode.notes)
                if duration is not None:
                    normalized_input['duration'] = duration
            
            # Парсим resolution из notes
            if 'resolution' not in normalized_input:
                resolution = _parse_resolution_from_notes(mode.notes)
                if resolution is not None:
                    normalized_input['resolution'] = resolution
    
    # Валидируем обязательные поля
    is_valid, error_msg = _check_required_fields(model_type, normalized_input, required_fields)
    if not is_valid:
        return {}, error_msg
    
    # Логируем (без секретов)
    input_keys = list(normalized_input.keys())
    # Маскируем длинные значения
    safe_input = {}
    for key, value in normalized_input.items():
        if key in ['prompt', 'text', 'negative_prompt']:
            if isinstance(value, str) and len(value) > 50:
                safe_input[key] = value[:50] + "..."
            else:
                safe_input[key] = value
        elif key in ['image_url', 'image_base64', 'video_url', 'audio_url']:
            if isinstance(value, str):
                safe_input[key] = value[:50] + "..." if len(value) > 50 else value
            else:
                safe_input[key] = "<binary>"
        else:
            safe_input[key] = value
    
    logger.info(
        f"MODEL={model_id} TYPE={model_type} INPUT_KEYS={input_keys} "
        f"INPUT_PREVIEW={safe_input}"
    )
    
    return normalized_input, None


def get_callback_url() -> Optional[str]:
    """
    Получает callback URL из настроек.
    
    Returns:
        Callback URL или None
    """
    settings = get_settings()
    callback_url = getattr(settings, 'kie_callback_url', None)
    if not callback_url:
        # Пробуем из env
        import os
        callback_url = os.getenv('KIE_CALLBACK_URL')
    
    return callback_url

