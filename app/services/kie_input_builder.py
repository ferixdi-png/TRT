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


def _normalize_duration_for_wan_2_6(value: Any) -> Optional[str]:
    """
    Нормализует duration для wan/2-6-text-to-video.
    Принимает числа (5, 10, 15) или строки ("5", "10", "15") и возвращает строку.
    
    Args:
        value: Значение duration (может быть int, float, str)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Убираем "s" или "seconds" в конце, если есть
    if str_value.lower().endswith('seconds'):
        str_value = str_value[:-7].strip()
    elif str_value.lower().endswith('s'):
        str_value = str_value[:-1].strip()
    
    # Проверяем что это валидное значение
    valid_values = ["5", "10", "15"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем конвертировать число в строку
    try:
        num_value = float(str_value)
        if num_value == 5.0 or num_value == 5:
            return "5"
        elif num_value == 10.0 or num_value == 10:
            return "10"
        elif num_value == 15.0 or num_value == 15:
            return "15"
    except (ValueError, TypeError):
        pass
    
    return None


def _normalize_resolution_for_wan_2_6(value: Any) -> Optional[str]:
    """
    Нормализует resolution для wan/2-6-text-to-video.
    Принимает строки ("720p", "1080p") и возвращает нормализованную строку.
    
    Args:
        value: Значение resolution
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    str_value = str(value).strip().lower()
    
    # Убеждаемся что есть суффикс "p"
    if not str_value.endswith('p'):
        str_value = str_value + 'p'
    
    # Проверяем что это валидное значение
    valid_values = ["720p", "1080p"]
    if str_value in valid_values:
        return str_value
    
    return None


def _normalize_video_urls_for_wan_2_6(value: Any) -> Optional[List[str]]:
    """
    Нормализует video_urls для wan/2-6-video-to-video.
    Принимает строку, массив строк или None и возвращает массив строк.
    
    Args:
        value: Значение video_urls (может быть str, list, None)
    
    Returns:
        Нормализованный массив URL или None
    """
    if value is None:
        return None
    
    # Если это строка, конвертируем в массив
    if isinstance(value, str):
        if value.strip():
            return [value.strip()]
        return None
    
    # Если это массив, проверяем и нормализуем элементы
    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
        return normalized if normalized else None
    
    return None


def _normalize_duration_for_wan_2_6_v2v(value: Any) -> Optional[str]:
    """
    Нормализует duration для wan/2-6-video-to-video.
    Принимает числа (5, 10) или строки ("5", "10") и возвращает строку.
    ВАЖНО: Для v2v поддерживаются только "5" и "10", не "15"!
    
    Args:
        value: Значение duration (может быть int, float, str)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Убираем "s" или "seconds" в конце, если есть
    if str_value.lower().endswith('seconds'):
        str_value = str_value[:-7].strip()
    elif str_value.lower().endswith('s'):
        str_value = str_value[:-1].strip()
    
    # Проверяем что это валидное значение (только 5 и 10 для v2v!)
    valid_values = ["5", "10"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем конвертировать число в строку
    try:
        num_value = float(str_value)
        if num_value == 5.0 or num_value == 5:
            return "5"
        elif num_value == 10.0 or num_value == 10:
            return "10"
    except (ValueError, TypeError):
        pass
    
    return None


def _normalize_image_urls_for_wan_2_6(value: Any) -> Optional[List[str]]:
    """
    Нормализует image_urls для wan/2-6-image-to-video.
    Принимает строку, массив строк или None и возвращает массив строк.
    
    Args:
        value: Значение image_urls (может быть str, list, None)
    
    Returns:
        Нормализованный массив URL или None
    """
    if value is None:
        return None
    
    # Если это строка, конвертируем в массив
    if isinstance(value, str):
        if value.strip():
            return [value.strip()]
        return None
    
    # Если это массив, проверяем и нормализуем элементы
    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
        return normalized if normalized else None
    
    return None


def _validate_wan_2_6_image_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для wan/2-6-image-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "wan/2-6-image-to-video":
        return True, None
    
    # Валидация prompt: обязательный, 2-5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len < 2:
        return False, "Поле 'prompt' должно содержать минимум 2 символа"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация image_urls: обязательный массив
    # Проверяем различные варианты имени поля
    image_urls = None
    if 'image_urls' in normalized_input:
        image_urls = normalized_input['image_urls']
    elif 'image_url' in normalized_input:
        # Конвертируем image_url в image_urls
        image_urls = normalized_input['image_url']
    elif 'image' in normalized_input:
        image_urls = normalized_input['image']
    
    if not image_urls:
        return False, "Поле 'image_urls' обязательно для генерации видео из изображения"
    
    # Нормализуем image_urls
    normalized_image_urls = _normalize_image_urls_for_wan_2_6(image_urls)
    if not normalized_image_urls:
        return False, "Поле 'image_urls' должно содержать хотя бы один валидный URL изображения"
    
    # Проверяем что все URL начинаются с http:// или https://
    for idx, url in enumerate(normalized_image_urls):
        if not (url.startswith('http://') or url.startswith('https://')):
            return False, f"URL изображения #{idx + 1} должен начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['image_urls'] = normalized_image_urls
    
    # Валидация duration: опциональный, "5" | "10" | "15", default "5"
    duration = normalized_input.get('duration')
    if duration is not None:
        normalized_duration = _normalize_duration_for_wan_2_6(duration)
        if normalized_duration is None:
            return False, f"Поле 'duration' должно быть '5', '10' или '15' (получено: {duration})"
        normalized_input['duration'] = normalized_duration
    
    # Валидация resolution: опциональный, "720p" | "1080p", default "1080p"
    resolution = normalized_input.get('resolution')
    if resolution is not None:
        normalized_resolution = _normalize_resolution_for_wan_2_6(resolution)
        if normalized_resolution is None:
            return False, f"Поле 'resolution' должно быть '720p' или '1080p' (получено: {resolution})"
        normalized_input['resolution'] = normalized_resolution
    
    return True, None


def _validate_wan_2_6_video_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для wan/2-6-video-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "wan/2-6-video-to-video":
        return True, None
    
    # Валидация prompt: обязательный, 2-5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len < 2:
        return False, "Поле 'prompt' должно содержать минимум 2 символа"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация video_urls: обязательный массив
    # Проверяем различные варианты имени поля
    video_urls = None
    if 'video_urls' in normalized_input:
        video_urls = normalized_input['video_urls']
    elif 'video_url' in normalized_input:
        # Конвертируем video_url в video_urls
        video_urls = normalized_input['video_url']
    elif 'video' in normalized_input:
        video_urls = normalized_input['video']
    
    if not video_urls:
        return False, "Поле 'video_urls' обязательно для генерации видео из видео"
    
    # Нормализуем video_urls
    normalized_video_urls = _normalize_video_urls_for_wan_2_6(video_urls)
    if not normalized_video_urls:
        return False, "Поле 'video_urls' должно содержать хотя бы один валидный URL видео"
    
    # Проверяем что все URL начинаются с http:// или https://
    for idx, url in enumerate(normalized_video_urls):
        if not (url.startswith('http://') or url.startswith('https://')):
            return False, f"URL видео #{idx + 1} должен начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['video_urls'] = normalized_video_urls
    
    # Валидация duration: опциональный, "5" | "10" (НЕ "15"!), default "5"
    duration = normalized_input.get('duration')
    if duration is not None:
        normalized_duration = _normalize_duration_for_wan_2_6_v2v(duration)
        if normalized_duration is None:
            return False, f"Поле 'duration' должно быть '5' или '10' (получено: {duration})"
        normalized_input['duration'] = normalized_duration
    
    # Валидация resolution: опциональный, "720p" | "1080p", default "1080p"
    resolution = normalized_input.get('resolution')
    if resolution is not None:
        normalized_resolution = _normalize_resolution_for_wan_2_6(resolution)
        if normalized_resolution is None:
            return False, f"Поле 'resolution' должно быть '720p' или '1080p' (получено: {resolution})"
        normalized_input['resolution'] = normalized_resolution
    
    return True, None


def _normalize_aspect_ratio_for_seedream_4_5(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для seedream/4.5-text-to-image.
    Принимает строки и возвращает нормализованную строку.
    
    Args:
        value: Значение aspect_ratio
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    str_value = str(value).strip()
    
    # Валидные значения
    valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]
    if str_value in valid_values:
        return str_value
    
    return None


def _normalize_quality_for_seedream_4_5(value: Any) -> Optional[str]:
    """
    Нормализует quality для seedream/4.5-text-to-image.
    Принимает строки и возвращает нормализованную строку в нижнем регистре.
    
    Args:
        value: Значение quality
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    str_value = str(value).strip().lower()
    
    # Валидные значения
    valid_values = ["basic", "high"]
    if str_value in valid_values:
        return str_value
    
    return None


def _validate_seedream_4_5_text_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для seedream/4.5-text-to-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "seedream/4.5-text-to-image":
        return True, None
    
    # Валидация prompt: обязательный, максимум 3000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 3000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 3000)"
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_seedream_4_5(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация quality: обязательный, enum
    quality = normalized_input.get('quality')
    if not quality:
        return False, "Поле 'quality' обязательно для генерации изображения"
    
    normalized_quality = _normalize_quality_for_seedream_4_5(quality)
    if normalized_quality is None:
        return False, f"Поле 'quality' должно быть 'basic' или 'high' (получено: {quality})"
    normalized_input['quality'] = normalized_quality
    
    return True, None


def _validate_seedream_4_5_edit(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для seedream/4.5-edit согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "seedream/4.5-edit":
        return True, None
    
    # Валидация prompt: обязательный, максимум 3000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для редактирования изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 3000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 3000)"
    
    # Валидация image_urls: обязательный массив
    # Проверяем различные варианты имени поля
    image_urls = None
    if 'image_urls' in normalized_input:
        image_urls = normalized_input['image_urls']
    elif 'image_url' in normalized_input:
        # Конвертируем image_url в image_urls
        image_urls = normalized_input['image_url']
    elif 'image' in normalized_input:
        image_urls = normalized_input['image']
    
    if not image_urls:
        return False, "Поле 'image_urls' обязательно для редактирования изображения"
    
    # Нормализуем image_urls
    normalized_image_urls = _normalize_image_urls_for_wan_2_6(image_urls)  # Используем ту же функцию
    if not normalized_image_urls:
        return False, "Поле 'image_urls' должно содержать хотя бы один валидный URL изображения"
    
    # Проверяем что все URL начинаются с http:// или https://
    for idx, url in enumerate(normalized_image_urls):
        if not (url.startswith('http://') or url.startswith('https://')):
            return False, f"URL изображения #{idx + 1} должен начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['image_urls'] = normalized_image_urls
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для редактирования изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_seedream_4_5(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация quality: обязательный, enum
    quality = normalized_input.get('quality')
    if not quality:
        return False, "Поле 'quality' обязательно для редактирования изображения"
    
    normalized_quality = _normalize_quality_for_seedream_4_5(quality)
    if normalized_quality is None:
        return False, f"Поле 'quality' должно быть 'basic' или 'high' (получено: {quality})"
    normalized_input['quality'] = normalized_quality
    
    return True, None


def _normalize_sound_for_kling_2_6(value: Any) -> Optional[bool]:
    """
    Нормализует sound для kling-2.6/image-to-video.
    Принимает boolean, строку или число и возвращает boolean.
    
    Args:
        value: Значение sound (может быть bool, str, int, None)
    
    Returns:
        Нормализованный boolean или None
    """
    if value is None:
        return None
    
    # Если это уже boolean, возвращаем как есть
    if isinstance(value, bool):
        return value
    
    # Если это строка, конвертируем в boolean
    if isinstance(value, str):
        str_value = str(value).strip().lower()
        if str_value in ['true', '1', 'yes', 'on']:
            return True
        elif str_value in ['false', '0', 'no', 'off']:
            return False
    
    # Если это число, конвертируем в boolean
    if isinstance(value, (int, float)):
        return bool(value)
    
    return None


def _normalize_duration_for_kling_2_6(value: Any) -> Optional[str]:
    """
    Нормализует duration для kling-2.6/image-to-video.
    Принимает числа (5, 10) или строки ("5", "10") и возвращает строку.
    ВАЖНО: Для kling-2.6 поддерживаются только "5" и "10"!
    
    Args:
        value: Значение duration (может быть int, float, str)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Убираем "s" или "seconds" в конце, если есть
    if str_value.lower().endswith('seconds'):
        str_value = str_value[:-7].strip()
    elif str_value.lower().endswith('s'):
        str_value = str_value[:-1].strip()
    
    # Проверяем что это валидное значение (только 5 и 10 для kling-2.6!)
    valid_values = ["5", "10"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем конвертировать число в строку
    try:
        num_value = float(str_value)
        if num_value == 5.0 or num_value == 5:
            return "5"
        elif num_value == 10.0 or num_value == 10:
            return "10"
    except (ValueError, TypeError):
        pass
    
    return None


def _validate_kling_2_6_image_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для kling-2.6/image-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "kling-2.6/image-to-video":
        return True, None
    
    # Валидация prompt: обязательный, максимум 1000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 1000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 1000)"
    
    # Валидация image_urls: обязательный массив
    # Проверяем различные варианты имени поля
    image_urls = None
    if 'image_urls' in normalized_input:
        image_urls = normalized_input['image_urls']
    elif 'image_url' in normalized_input:
        # Конвертируем image_url в image_urls
        image_urls = normalized_input['image_url']
    elif 'image' in normalized_input:
        image_urls = normalized_input['image']
    
    if not image_urls:
        return False, "Поле 'image_urls' обязательно для генерации видео из изображения"
    
    # Нормализуем image_urls
    normalized_image_urls = _normalize_image_urls_for_wan_2_6(image_urls)  # Используем ту же функцию
    if not normalized_image_urls:
        return False, "Поле 'image_urls' должно содержать хотя бы один валидный URL изображения"
    
    # Проверяем что все URL начинаются с http:// или https://
    for idx, url in enumerate(normalized_image_urls):
        if not (url.startswith('http://') or url.startswith('https://')):
            return False, f"URL изображения #{idx + 1} должен начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['image_urls'] = normalized_image_urls
    
    # Валидация sound: обязательный boolean
    sound = normalized_input.get('sound')
    if sound is None:
        return False, "Поле 'sound' обязательно для генерации видео"
    
    normalized_sound = _normalize_sound_for_kling_2_6(sound)
    if normalized_sound is None:
        return False, f"Поле 'sound' должно быть boolean (true/false) (получено: {sound})"
    normalized_input['sound'] = normalized_sound
    
    # Валидация duration: обязательный, "5" | "10", default "5"
    duration = normalized_input.get('duration')
    if not duration:
        return False, "Поле 'duration' обязательно для генерации видео"
    
    normalized_duration = _normalize_duration_for_kling_2_6(duration)
    if normalized_duration is None:
        return False, f"Поле 'duration' должно быть '5' или '10' (получено: {duration})"
    normalized_input['duration'] = normalized_duration
    
    return True, None


def _validate_wan_2_6_text_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для wan/2-6-text-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "wan/2-6-text-to-video":
        return True, None
    
    # Валидация prompt: обязательный, 1-5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len < 1:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация duration: опциональный, "5" | "10" | "15", default "5"
    duration = normalized_input.get('duration')
    if duration is not None:
        normalized_duration = _normalize_duration_for_wan_2_6(duration)
        if normalized_duration is None:
            return False, f"Поле 'duration' должно быть '5', '10' или '15' (получено: {duration})"
        normalized_input['duration'] = normalized_duration
    
    # Валидация resolution: опциональный, "720p" | "1080p", default "1080p"
    resolution = normalized_input.get('resolution')
    if resolution is not None:
        normalized_resolution = _normalize_resolution_for_wan_2_6(resolution)
        if normalized_resolution is None:
            return False, f"Поле 'resolution' должно быть '720p' или '1080p' (получено: {resolution})"
        normalized_input['resolution'] = normalized_resolution
    
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
        # Для image_urls сохраняем как массив (для wan/2-6-image-to-video)
        if normalized_key == 'image_urls':
            # Если это строка, конвертируем в массив
            if isinstance(value, str) and value.strip():
                value = [value.strip()]
            # Если это массив, оставляем как есть
            elif isinstance(value, list):
                # Фильтруем пустые элементы
                value = [item.strip() for item in value if isinstance(item, str) and item.strip()]
            # Если пустое, пропускаем
            if not value:
                continue
        
        if normalized_key in ['image_url', 'image_base64', 'image']:
            # Если это список, берём первый элемент
            if isinstance(value, list) and len(value) > 0:
                value = value[0]
            # Если пустая строка или None, пропускаем
            if not value:
                continue
        
        # Для video_urls сохраняем как массив (для wan/2-6-video-to-video)
        if normalized_key == 'video_urls':
            # Если это строка, конвертируем в массив
            if isinstance(value, str) and value.strip():
                value = [value.strip()]
            # Если это массив, оставляем как есть
            elif isinstance(value, list):
                # Фильтруем пустые элементы
                value = [item.strip() for item in value if isinstance(item, str) and item.strip()]
            # Если пустое, пропускаем
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
                    # Для wan/2-6-text-to-video duration должен быть строкой
                    if model_id == "wan/2-6-text-to-video":
                        normalized_input['duration'] = str(int(duration))
                    else:
                        normalized_input['duration'] = duration
            
            # Парсим resolution из notes
            if 'resolution' not in normalized_input:
                resolution = _parse_resolution_from_notes(mode.notes)
                if resolution is not None:
                    normalized_input['resolution'] = resolution
    
    # Специфичная валидация для wan/2-6-text-to-video
    is_valid, error_msg = _validate_wan_2_6_text_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для wan/2-6-image-to-video
    is_valid, error_msg = _validate_wan_2_6_image_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для wan/2-6-video-to-video
    is_valid, error_msg = _validate_wan_2_6_video_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для seedream/4.5-text-to-image
    is_valid, error_msg = _validate_seedream_4_5_text_to_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для seedream/4.5-edit
    is_valid, error_msg = _validate_seedream_4_5_edit(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для kling-2.6/image-to-video
    is_valid, error_msg = _validate_kling_2_6_image_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Применяем дефолты для kling-2.6/image-to-video
    if model_id == "kling-2.6/image-to-video":
        if 'sound' not in normalized_input:
            normalized_input['sound'] = False  # Default согласно документации
        if 'duration' not in normalized_input:
            normalized_input['duration'] = "5"  # Default согласно документации
    
    # Применяем дефолты для seedream/4.5-text-to-image
    if model_id == "seedream/4.5-text-to-image":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'quality' not in normalized_input:
            normalized_input['quality'] = "basic"  # Default согласно документации
    
    # Применяем дефолты для seedream/4.5-edit
    if model_id == "seedream/4.5-edit":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'quality' not in normalized_input:
            normalized_input['quality'] = "basic"  # Default согласно документации
    
    # Применяем дефолты для wan/2-6-text-to-video
    if model_id == "wan/2-6-text-to-video":
        if 'duration' not in normalized_input:
            normalized_input['duration'] = "5"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1080p"  # Default согласно документации
    
    # Применяем дефолты для wan/2-6-image-to-video
    if model_id == "wan/2-6-image-to-video":
        if 'duration' not in normalized_input:
            normalized_input['duration'] = "5"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1080p"  # Default согласно документации
    
    # Применяем дефолты для wan/2-6-video-to-video
    if model_id == "wan/2-6-video-to-video":
        if 'duration' not in normalized_input:
            normalized_input['duration'] = "5"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1080p"  # Default согласно документации
    
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

