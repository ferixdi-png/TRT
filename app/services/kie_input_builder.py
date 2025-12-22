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


def _normalize_aspect_ratio_for_kling_2_6(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для kling-2.6/text-to-video.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для kling-2.6 поддерживаются только "1:1", "16:9", "9:16"!
    
    Args:
        value: Значение aspect_ratio (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Проверяем что это валидное значение (только 3 значения для kling-2.6!)
    valid_values = ["1:1", "16:9", "9:16"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    str_lower = str_value.lower()
    if str_lower in ["1:1", "1/1", "1x1", "square"]:
        return "1:1"
    elif str_lower in ["16:9", "16/9", "16x9", "landscape", "wide"]:
        return "16:9"
    elif str_lower in ["9:16", "9/16", "9x16", "portrait", "vertical"]:
        return "9:16"
    
    return None


def _validate_kling_2_6_text_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для kling-2.6/text-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "kling-2.6/text-to-video":
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
    
    # Валидация sound: обязательный boolean
    sound = normalized_input.get('sound')
    if sound is None:
        return False, "Поле 'sound' обязательно для генерации видео"
    
    normalized_sound = _normalize_sound_for_kling_2_6(sound)
    if normalized_sound is None:
        return False, f"Поле 'sound' должно быть boolean (true/false) (получено: {sound})"
    normalized_input['sound'] = normalized_sound
    
    # Валидация aspect_ratio: обязательный, "1:1" | "16:9" | "9:16"
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации видео"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_kling_2_6(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "16:9", "9:16"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация duration: обязательный, "5" | "10", default "5"
    duration = normalized_input.get('duration')
    if not duration:
        return False, "Поле 'duration' обязательно для генерации видео"
    
    normalized_duration = _normalize_duration_for_kling_2_6(duration)
    if normalized_duration is None:
        return False, f"Поле 'duration' должно быть '5' или '10' (получено: {duration})"
    normalized_input['duration'] = normalized_duration
    
    return True, None


def _normalize_aspect_ratio_for_z_image(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для z-image.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для z-image поддерживаются только "1:1", "4:3", "3:4", "16:9", "9:16" (5 значений)!
    
    Args:
        value: Значение aspect_ratio (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Проверяем что это валидное значение (только 5 значений для z-image!)
    valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    str_lower = str_value.lower()
    if str_lower in ["1:1", "1/1", "1x1", "square"]:
        return "1:1"
    elif str_lower in ["4:3", "4/3", "4x3"]:
        return "4:3"
    elif str_lower in ["3:4", "3/4", "3x4"]:
        return "3:4"
    elif str_lower in ["16:9", "16/9", "16x9", "landscape", "wide"]:
        return "16:9"
    elif str_lower in ["9:16", "9/16", "9x16", "portrait", "vertical"]:
        return "9:16"
    
    return None


def _validate_z_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для z-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "z-image":
        return True, None
    
    # Валидация prompt: обязательный, максимум 1000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 1000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 1000)"
    
    # Валидация aspect_ratio: обязательный, "1:1" | "4:3" | "3:4" | "16:9" | "9:16"
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_z_image(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    return True, None


def _normalize_input_urls_for_flux_2_pro(value: Any) -> Optional[List[str]]:
    """
    Нормализует input_urls для flux-2/pro-image-to-image.
    Принимает строку, массив строк или None и возвращает массив строк.
    ВАЖНО: Для Flux моделей используется input_urls, а не image_urls!
    
    Args:
        value: Значение input_urls (может быть str, list, None)
    
    Returns:
        Нормализованный массив строк или None
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


def _normalize_aspect_ratio_for_flux_2_pro(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для flux-2/pro-image-to-image.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для flux-2/pro поддерживаются "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"!
    
    Args:
        value: Значение aspect_ratio (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Извлекаем только соотношение сторон, если есть дополнительные символы (например, "1:1 (Square)")
    if ' ' in str_value:
        str_value = str_value.split()[0].strip()
    
    # Проверяем что это валидное значение
    valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    str_lower = str_value.lower()
    if str_lower in ["1:1", "1/1", "1x1", "square"]:
        return "1:1"
    elif str_lower in ["4:3", "4/3", "4x3"]:
        return "4:3"
    elif str_lower in ["3:4", "3/4", "3x4"]:
        return "3:4"
    elif str_lower in ["16:9", "16/9", "16x9", "landscape", "widescreen"]:
        return "16:9"
    elif str_lower in ["9:16", "9/16", "9x16", "portrait", "vertical"]:
        return "9:16"
    elif str_lower in ["3:2", "3/2", "3x2", "classic"]:
        return "3:2"
    elif str_lower in ["2:3", "2/3", "2x3", "classic portrait"]:
        return "2:3"
    elif str_lower == "auto":
        return "auto"
    
    return None


def _normalize_resolution_for_flux_2_pro(value: Any) -> Optional[str]:
    """
    Нормализует resolution для flux-2/pro-image-to-image.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для flux-2/pro поддерживаются только "1K" и "2K"!
    
    Args:
        value: Значение resolution (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы, конвертируем в верхний регистр
    str_value = str(value).strip().upper()
    
    # Проверяем что это валидное значение
    valid_values = ["1K", "2K"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    if str_value in ["1", "1k", "1000", "1k resolution"]:
        return "1K"
    elif str_value in ["2", "2k", "2000", "2k resolution"]:
        return "2K"
    
    return None


def _validate_flux_2_pro_image_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для flux-2/pro-image-to-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "flux-2/pro-image-to-image":
        return True, None
    
    # Валидация input_urls: обязательный массив (1-8 изображений)
    # ВАЖНО: Для Flux моделей используется input_urls, а не image_urls!
    input_urls = None
    if 'input_urls' in normalized_input:
        input_urls = normalized_input['input_urls']
    elif 'image_input' in normalized_input:
        # Конвертируем image_input в input_urls
        input_urls = normalized_input['image_input']
    elif 'image_urls' in normalized_input:
        # Конвертируем image_urls в input_urls
        input_urls = normalized_input['image_urls']
    
    if not input_urls:
        return False, "Поле 'input_urls' обязательно для генерации изображения"
    
    # Нормализуем input_urls
    normalized_input_urls = _normalize_input_urls_for_flux_2_pro(input_urls)
    if not normalized_input_urls:
        return False, "Поле 'input_urls' должно содержать хотя бы один валидный URL изображения"
    
    # Проверяем количество изображений (1-8)
    if len(normalized_input_urls) > 8:
        return False, f"Поле 'input_urls' содержит слишком много изображений: {len(normalized_input_urls)} (максимум 8)"
    
    # Проверяем что все URL начинаются с http:// или https://
    for idx, url in enumerate(normalized_input_urls):
        if not (url.startswith('http://') or url.startswith('https://')):
            return False, f"URL изображения #{idx + 1} должен начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['input_urls'] = normalized_input_urls
    
    # Валидация prompt: обязательный, от 3 до 5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len < 3:
        return False, f"Поле 'prompt' слишком короткое: {prompt_len} символов (минимум 3)"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_flux_2_pro(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация resolution: обязательный, "1K" | "2K"
    resolution = normalized_input.get('resolution')
    if not resolution:
        return False, "Поле 'resolution' обязательно для генерации изображения"
    
    normalized_resolution = _normalize_resolution_for_flux_2_pro(resolution)
    if normalized_resolution is None:
        return False, f"Поле 'resolution' должно быть '1K' или '2K' (получено: {resolution})"
    normalized_input['resolution'] = normalized_resolution
    
    return True, None


def _validate_flux_2_pro_text_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для flux-2/pro-text-to-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "flux-2/pro-text-to-image":
        return True, None
    
    # Валидация prompt: обязательный, от 3 до 5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len < 3:
        return False, f"Поле 'prompt' слишком короткое: {prompt_len} символов (минимум 3)"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_flux_2_pro(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация resolution: обязательный, "1K" | "2K"
    resolution = normalized_input.get('resolution')
    if not resolution:
        return False, "Поле 'resolution' обязательно для генерации изображения"
    
    normalized_resolution = _normalize_resolution_for_flux_2_pro(resolution)
    if normalized_resolution is None:
        return False, f"Поле 'resolution' должно быть '1K' или '2K' (получено: {resolution})"
    normalized_input['resolution'] = normalized_resolution
    
    return True, None


def _validate_flux_2_flex_image_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для flux-2/flex-image-to-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "flux-2/flex-image-to-image":
        return True, None
    
    # Валидация input_urls: обязательный массив (1-8 изображений)
    # ВАЖНО: Для Flux моделей используется input_urls, а не image_urls!
    input_urls = None
    if 'input_urls' in normalized_input:
        input_urls = normalized_input['input_urls']
    elif 'image_input' in normalized_input:
        # Конвертируем image_input в input_urls
        input_urls = normalized_input['image_input']
    elif 'image_urls' in normalized_input:
        # Конвертируем image_urls в input_urls
        input_urls = normalized_input['image_urls']
    
    if not input_urls:
        return False, "Поле 'input_urls' обязательно для генерации изображения"
    
    # Нормализуем input_urls
    normalized_input_urls = _normalize_input_urls_for_flux_2_pro(input_urls)
    if not normalized_input_urls:
        return False, "Поле 'input_urls' должно содержать хотя бы один валидный URL изображения"
    
    # Проверяем количество изображений (1-8)
    if len(normalized_input_urls) > 8:
        return False, f"Поле 'input_urls' содержит слишком много изображений: {len(normalized_input_urls)} (максимум 8)"
    
    # Проверяем что все URL начинаются с http:// или https://
    for idx, url in enumerate(normalized_input_urls):
        if not (url.startswith('http://') or url.startswith('https://')):
            return False, f"URL изображения #{idx + 1} должен начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['input_urls'] = normalized_input_urls
    
    # Валидация prompt: обязательный, от 3 до 5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len < 3:
        return False, f"Поле 'prompt' слишком короткое: {prompt_len} символов (минимум 3)"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_flux_2_pro(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация resolution: обязательный, "1K" | "2K"
    resolution = normalized_input.get('resolution')
    if not resolution:
        return False, "Поле 'resolution' обязательно для генерации изображения"
    
    normalized_resolution = _normalize_resolution_for_flux_2_pro(resolution)
    if normalized_resolution is None:
        return False, f"Поле 'resolution' должно быть '1K' или '2K' (получено: {resolution})"
    normalized_input['resolution'] = normalized_resolution
    
    return True, None


def _validate_flux_2_flex_text_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для flux-2/flex-text-to-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "flux-2/flex-text-to-image":
        return True, None
    
    # Валидация prompt: обязательный, от 3 до 5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len < 3:
        return False, f"Поле 'prompt' слишком короткое: {prompt_len} символов (минимум 3)"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация aspect_ratio: обязательный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if not aspect_ratio:
        return False, "Поле 'aspect_ratio' обязательно для генерации изображения"
    
    normalized_aspect_ratio = _normalize_aspect_ratio_for_flux_2_pro(aspect_ratio)
    if normalized_aspect_ratio is None:
        valid_values = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
        return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
    normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация resolution: обязательный, "1K" | "2K"
    resolution = normalized_input.get('resolution')
    if not resolution:
        return False, "Поле 'resolution' обязательно для генерации изображения"
    
    normalized_resolution = _normalize_resolution_for_flux_2_pro(resolution)
    if normalized_resolution is None:
        return False, f"Поле 'resolution' должно быть '1K' или '2K' (получено: {resolution})"
    normalized_input['resolution'] = normalized_resolution
    
    return True, None


def _normalize_aspect_ratio_for_nano_banana_pro(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для nano-banana-pro.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для nano-banana-pro поддерживаются 11 значений (включая "auto")!
    
    Args:
        value: Значение aspect_ratio (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Извлекаем только соотношение сторон, если есть дополнительные символы
    if ' ' in str_value:
        str_value = str_value.split()[0].strip()
    
    # Проверяем что это валидное значение
    valid_values = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    str_lower = str_value.lower()
    if str_lower in ["1:1", "1/1", "1x1", "square"]:
        return "1:1"
    elif str_lower in ["2:3", "2/3", "2x3"]:
        return "2:3"
    elif str_lower in ["3:2", "3/2", "3x2"]:
        return "3:2"
    elif str_lower in ["3:4", "3/4", "3x4"]:
        return "3:4"
    elif str_lower in ["4:3", "4/3", "4x3"]:
        return "4:3"
    elif str_lower in ["4:5", "4/5", "4x5"]:
        return "4:5"
    elif str_lower in ["5:4", "5/4", "5x4"]:
        return "5:4"
    elif str_lower in ["9:16", "9/16", "9x16", "portrait", "vertical"]:
        return "9:16"
    elif str_lower in ["16:9", "16/9", "16x9", "landscape", "widescreen"]:
        return "16:9"
    elif str_lower in ["21:9", "21/9", "21x9", "ultrawide"]:
        return "21:9"
    elif str_lower == "auto":
        return "auto"
    
    return None


def _normalize_resolution_for_nano_banana_pro(value: Any) -> Optional[str]:
    """
    Нормализует resolution для nano-banana-pro.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для nano-banana-pro поддерживаются "1K", "2K" и "4K" (3 значения, не 2!)!
    
    Args:
        value: Значение resolution (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы, конвертируем в верхний регистр
    str_value = str(value).strip().upper()
    
    # Проверяем что это валидное значение
    valid_values = ["1K", "2K", "4K"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    if str_value in ["1", "1k", "1000", "1k resolution"]:
        return "1K"
    elif str_value in ["2", "2k", "2000", "2k resolution"]:
        return "2K"
    elif str_value in ["4", "4k", "4000", "4k resolution"]:
        return "4K"
    
    return None


def _normalize_output_format_for_nano_banana_pro(value: Any) -> Optional[str]:
    """
    Нормализует output_format для nano-banana-pro.
    Принимает строку и возвращает нормализованное значение в нижнем регистре.
    ВАЖНО: Для nano-banana-pro поддерживаются только "png" и "jpg"!
    
    Args:
        value: Значение output_format (может быть str)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы, конвертируем в нижний регистр
    str_value = str(value).strip().lower()
    
    # Маппинг jpeg -> jpg
    if str_value == "jpeg":
        str_value = "jpg"
    
    # Проверяем что это валидное значение
    valid_values = ["png", "jpg"]
    if str_value in valid_values:
        return str_value
    
    return None


def _validate_nano_banana_pro(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для nano-banana-pro согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    # Проверяем оба возможных ID модели
    if model_id not in ["nano-banana-pro", "google/nano-banana-pro"]:
        return True, None
    
    # Валидация prompt: обязательный, максимум 10000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 10000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 10000)"
    
    # Валидация image_input: опциональный массив (до 8 изображений)
    image_input = normalized_input.get('image_input')
    if image_input is not None:
        # Нормализуем image_input (используем функцию для Flux, так как логика похожа)
        normalized_image_input = _normalize_input_urls_for_flux_2_pro(image_input)
        if normalized_image_input is not None:
            # Проверяем количество изображений (до 8)
            if len(normalized_image_input) > 8:
                return False, f"Поле 'image_input' содержит слишком много изображений: {len(normalized_image_input)} (максимум 8)"
            
            # Проверяем что все URL начинаются с http:// или https://
            for idx, url in enumerate(normalized_image_input):
                if not (url.startswith('http://') or url.startswith('https://')):
                    return False, f"URL изображения #{idx + 1} должен начинаться с http:// или https://"
            
            # Сохраняем нормализованное значение
            normalized_input['image_input'] = normalized_image_input
        else:
            # Если image_input пустой или невалидный, устанавливаем пустой массив
            normalized_input['image_input'] = []
    
    # Валидация aspect_ratio: опциональный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if aspect_ratio is not None:
        normalized_aspect_ratio = _normalize_aspect_ratio_for_nano_banana_pro(aspect_ratio)
        if normalized_aspect_ratio is None:
            valid_values = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"]
            return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
        normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация resolution: опциональный, "1K" | "2K" | "4K"
    resolution = normalized_input.get('resolution')
    if resolution is not None:
        normalized_resolution = _normalize_resolution_for_nano_banana_pro(resolution)
        if normalized_resolution is None:
            return False, f"Поле 'resolution' должно быть '1K', '2K' или '4K' (получено: {resolution})"
        normalized_input['resolution'] = normalized_resolution
    
    # Валидация output_format: опциональный, "png" | "jpg"
    output_format = normalized_input.get('output_format')
    if output_format is not None:
        normalized_output_format = _normalize_output_format_for_nano_banana_pro(output_format)
        if normalized_output_format is None:
            return False, f"Поле 'output_format' должно быть 'png' или 'jpg' (получено: {output_format})"
        normalized_input['output_format'] = normalized_output_format
    
    return True, None


def _normalize_resolution_for_v1_pro_fast(value: Any) -> Optional[str]:
    """
    Нормализует resolution для bytedance/v1-pro-fast-image-to-video.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для v1-pro-fast поддерживаются только "720p" и "1080p" (не "480p"!)!
    
    Args:
        value: Значение resolution (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы, конвертируем в нижний регистр
    str_value = str(value).strip().lower()
    
    # Проверяем что это валидное значение
    valid_values = ["720p", "1080p"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    if str_value in ["720", "720p", "hd"]:
        return "720p"
    elif str_value in ["1080", "1080p", "full hd", "fhd"]:
        return "1080p"
    
    return None


def _normalize_duration_for_v1_pro_fast(value: Any) -> Optional[str]:
    """
    Нормализует duration для bytedance/v1-pro-fast-image-to-video.
    Принимает числа (5, 10) или строки ("5", "10", "5s", "10s") и возвращает строку.
    ВАЖНО: Для v1-pro-fast поддерживаются только "5" и "10"!
    
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
    
    # Проверяем что это валидное значение (только 5 и 10 для v1-pro-fast!)
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


def _validate_bytedance_v1_pro_fast_image_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для bytedance/v1-pro-fast-image-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    if model_id != "bytedance/v1-pro-fast-image-to-video":
        return True, None
    
    # Валидация prompt: обязательный, максимум 10000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 10000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 10000)"
    
    # Валидация image_url: обязательный (строка, не массив!)
    # ВАЖНО: Для v1-pro-fast используется image_url (строка), а не image_urls (массив)!
    image_url = None
    if 'image_url' in normalized_input:
        image_url = normalized_input['image_url']
    elif 'image_urls' in normalized_input:
        # Если передан массив, берем первый элемент
        image_urls = normalized_input['image_urls']
        if isinstance(image_urls, list) and len(image_urls) > 0:
            image_url = image_urls[0]
        elif isinstance(image_urls, str):
            image_url = image_urls
    elif 'image_input' in normalized_input:
        # Если передан image_input, берем первый элемент если это массив
        image_input = normalized_input['image_input']
        if isinstance(image_input, list) and len(image_input) > 0:
            image_url = image_input[0]
        elif isinstance(image_input, str):
            image_url = image_input
    
    if not image_url:
        return False, "Поле 'image_url' обязательно для генерации видео из изображения"
    
    # Проверяем что это строка
    if not isinstance(image_url, str):
        image_url = str(image_url)
    
    image_url = image_url.strip()
    if not image_url:
        return False, "Поле 'image_url' не может быть пустым"
    
    # Проверяем что URL начинается с http:// или https://
    if not (image_url.startswith('http://') or image_url.startswith('https://')):
        return False, "Поле 'image_url' должно начинаться с http:// или https://"
    
    # Сохраняем нормализованное значение
    normalized_input['image_url'] = image_url
    
    # Валидация resolution: опциональный, "720p" | "1080p"
    resolution = normalized_input.get('resolution')
    if resolution is not None:
        normalized_resolution = _normalize_resolution_for_v1_pro_fast(resolution)
        if normalized_resolution is None:
            return False, f"Поле 'resolution' должно быть '720p' или '1080p' (получено: {resolution})"
        normalized_input['resolution'] = normalized_resolution
    
    # Валидация duration: опциональный, "5" | "10"
    duration = normalized_input.get('duration')
    if duration is not None:
        normalized_duration = _normalize_duration_for_v1_pro_fast(duration)
        if normalized_duration is None:
            return False, f"Поле 'duration' должно быть '5' или '10' (получено: {duration})"
        normalized_input['duration'] = normalized_duration
    
    return True, None


def _normalize_mode_for_grok_imagine(value: Any) -> Optional[str]:
    """
    Нормализует mode для grok-imagine/image-to-video.
    Принимает строку и возвращает нормализованное значение в нижнем регистре.
    ВАЖНО: Для grok-imagine поддерживаются только "fun", "normal", "spicy"!
    
    Args:
        value: Значение mode (может быть str)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы, конвертируем в нижний регистр
    str_value = str(value).strip().lower()
    
    # Проверяем что это валидное значение
    valid_values = ["fun", "normal", "spicy"]
    if str_value in valid_values:
        return str_value
    
    return None


def _validate_grok_imagine_image_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для grok-imagine/image-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    # Проверяем оба возможных ID модели
    if model_id not in ["grok-imagine/image-to-video", "grok/imagine"]:
        return True, None
    
    # ВАЖНО: Все параметры опциональны! Но должны быть валидными если указаны.
    
    # Валидация image_urls: опциональный массив (только одно изображение)
    image_urls = normalized_input.get('image_urls')
    if image_urls is not None:
        # Нормализуем image_urls
        normalized_image_urls = _normalize_image_urls_for_wan_2_6(image_urls)
        if normalized_image_urls is not None:
            # Проверяем количество изображений (только одно!)
            if len(normalized_image_urls) > 1:
                return False, f"Поле 'image_urls' должно содержать только одно изображение (получено: {len(normalized_image_urls)})"
            
            # Проверяем что URL начинается с http:// или https://
            url = normalized_image_urls[0]
            if not (url.startswith('http://') or url.startswith('https://')):
                return False, "URL изображения должен начинаться с http:// или https://"
            
            # Сохраняем нормализованное значение
            normalized_input['image_urls'] = normalized_image_urls
    
    # Валидация task_id: опциональный string (максимум 100 символов)
    task_id = normalized_input.get('task_id')
    if task_id is not None:
        if not isinstance(task_id, str):
            task_id = str(task_id)
        
        task_id = task_id.strip()
        if len(task_id) > 100:
            return False, f"Поле 'task_id' слишком длинное: {len(task_id)} символов (максимум 100)"
        
        normalized_input['task_id'] = task_id
    
    # Валидация index: опциональный number (0-5, 0-based)
    index = normalized_input.get('index')
    if index is not None:
        try:
            index_num = int(index)
            if index_num < 0 or index_num > 5:
                return False, f"Поле 'index' должно быть числом от 0 до 5 (получено: {index})"
            normalized_input['index'] = index_num
        except (ValueError, TypeError):
            return False, f"Поле 'index' должно быть числом от 0 до 5 (получено: {index})"
    
    # Валидация prompt: опциональный string (максимум 5000 символов)
    prompt = normalized_input.get('prompt')
    if prompt is not None:
        if not isinstance(prompt, str):
            prompt = str(prompt)
        
        prompt_len = len(prompt.strip())
        if prompt_len > 5000:
            return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
        
        normalized_input['prompt'] = prompt.strip() if prompt_len > 0 else None
    
    # Валидация mode: опциональный string ("fun", "normal", "spicy")
    mode = normalized_input.get('mode')
    if mode is not None:
        normalized_mode = _normalize_mode_for_grok_imagine(mode)
        if normalized_mode is None:
            return False, f"Поле 'mode' должно быть 'fun', 'normal' или 'spicy' (получено: {mode})"
        normalized_input['mode'] = normalized_mode
    
    # ВАЖНО: Проверяем взаимоисключающие параметры
    # image_urls и task_id не должны использоваться одновременно
    has_image_urls = normalized_input.get('image_urls') is not None and len(normalized_input.get('image_urls', [])) > 0
    has_task_id = normalized_input.get('task_id') is not None and normalized_input.get('task_id')
    
    if has_image_urls and has_task_id:
        return False, "Поля 'image_urls' и 'task_id' не могут использоваться одновременно. Используйте либо 'image_urls', либо 'task_id'"
    
    # index работает только с task_id
    has_index = normalized_input.get('index') is not None
    if has_index and not has_task_id:
        return False, "Поле 'index' может использоваться только вместе с 'task_id'"
    
    # mode "spicy" не поддерживается с внешними изображениями (image_urls)
    if has_image_urls and normalized_input.get('mode') == 'spicy':
        return False, "Режим 'spicy' не поддерживается с внешними изображениями (image_urls). Используйте 'task_id' для режима 'spicy'"
    
    return True, None


def _normalize_aspect_ratio_for_grok_imagine_text_to_video(value: Any) -> Optional[str]:
    """
    Нормализует aspect_ratio для grok-imagine/text-to-video.
    Принимает строку и возвращает нормализованное значение.
    ВАЖНО: Для grok-imagine/text-to-video поддерживаются только "2:3", "3:2", "1:1" (3 значения)!
    
    Args:
        value: Значение aspect_ratio (может быть str, int, float)
    
    Returns:
        Нормализованная строка или None
    """
    if value is None:
        return None
    
    # Конвертируем в строку и убираем пробелы
    str_value = str(value).strip()
    
    # Проверяем что это валидное значение
    valid_values = ["2:3", "3:2", "1:1"]
    if str_value in valid_values:
        return str_value
    
    # Пробуем нормализовать варианты написания
    str_lower = str_value.lower()
    if str_lower in ["2:3", "2/3", "2x3"]:
        return "2:3"
    elif str_lower in ["3:2", "3/2", "3x2"]:
        return "3:2"
    elif str_lower in ["1:1", "1/1", "1x1", "square"]:
        return "1:1"
    
    return None


def _validate_grok_imagine_text_to_video(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для grok-imagine/text-to-video согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    # Проверяем оба возможных ID модели
    if model_id not in ["grok-imagine/text-to-video", "grok/imagine-text-to-video"]:
        return True, None
    
    # Валидация prompt: обязательный, максимум 5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации видео"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация aspect_ratio: опциональный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if aspect_ratio is not None:
        normalized_aspect_ratio = _normalize_aspect_ratio_for_grok_imagine_text_to_video(aspect_ratio)
        if normalized_aspect_ratio is None:
            valid_values = ["2:3", "3:2", "1:1"]
            return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
        normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # Валидация mode: опциональный, enum
    mode = normalized_input.get('mode')
    if mode is not None:
        normalized_mode = _normalize_mode_for_grok_imagine(mode)
        if normalized_mode is None:
            return False, f"Поле 'mode' должно быть 'fun', 'normal' или 'spicy' (получено: {mode})"
        normalized_input['mode'] = normalized_mode
    
    return True, None


def _validate_grok_imagine_text_to_image(
    model_id: str,
    normalized_input: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Специфичная валидация для grok-imagine/text-to-image согласно документации API.
    
    Args:
        model_id: ID модели
        normalized_input: Нормализованные входные данные
    
    Returns:
        (is_valid, error_message)
    """
    # Проверяем оба возможных ID модели
    if model_id not in ["grok-imagine/text-to-image", "grok/imagine-text-to-image"]:
        return True, None
    
    # Валидация prompt: обязательный, максимум 5000 символов
    prompt = normalized_input.get('prompt')
    if not prompt:
        return False, "Поле 'prompt' обязательно для генерации изображения"
    
    if not isinstance(prompt, str):
        prompt = str(prompt)
    
    prompt_len = len(prompt.strip())
    if prompt_len == 0:
        return False, "Поле 'prompt' не может быть пустым"
    if prompt_len > 5000:
        return False, f"Поле 'prompt' слишком длинное: {prompt_len} символов (максимум 5000)"
    
    # Валидация aspect_ratio: опциональный, enum
    aspect_ratio = normalized_input.get('aspect_ratio')
    if aspect_ratio is not None:
        # Переиспользуем функцию нормализации из text-to-video (те же 3 значения)
        normalized_aspect_ratio = _normalize_aspect_ratio_for_grok_imagine_text_to_video(aspect_ratio)
        if normalized_aspect_ratio is None:
            valid_values = ["2:3", "3:2", "1:1"]
            return False, f"Поле 'aspect_ratio' должно быть одним из: {', '.join(valid_values)} (получено: {aspect_ratio})"
        normalized_input['aspect_ratio'] = normalized_aspect_ratio
    
    # ВАЖНО: Нет параметра mode для text-to-image (в отличие от text-to-video и image-to-video)
    
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
    
    # Специфичная валидация для kling-2.6/text-to-video
    is_valid, error_msg = _validate_kling_2_6_text_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для z-image
    is_valid, error_msg = _validate_z_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для flux-2/pro-image-to-image
    is_valid, error_msg = _validate_flux_2_pro_image_to_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для flux-2/pro-text-to-image
    is_valid, error_msg = _validate_flux_2_pro_text_to_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для flux-2/flex-image-to-image
    is_valid, error_msg = _validate_flux_2_flex_image_to_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для flux-2/flex-text-to-image
    is_valid, error_msg = _validate_flux_2_flex_text_to_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для nano-banana-pro
    is_valid, error_msg = _validate_nano_banana_pro(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для bytedance/v1-pro-fast-image-to-video
    is_valid, error_msg = _validate_bytedance_v1_pro_fast_image_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для grok-imagine/image-to-video
    is_valid, error_msg = _validate_grok_imagine_image_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для grok-imagine/text-to-video
    is_valid, error_msg = _validate_grok_imagine_text_to_video(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Специфичная валидация для grok-imagine/text-to-image
    is_valid, error_msg = _validate_grok_imagine_text_to_image(model_id, normalized_input)
    if not is_valid:
        return {}, error_msg
    
    # Применяем дефолты для z-image
    if model_id == "z-image":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
    
    # Применяем дефолты для flux-2/pro-image-to-image
    if model_id == "flux-2/pro-image-to-image":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1K"  # Default согласно документации
    
    # Применяем дефолты для flux-2/pro-text-to-image
    if model_id == "flux-2/pro-text-to-image":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1K"  # Default согласно документации
    
    # Применяем дефолты для flux-2/flex-image-to-image
    if model_id == "flux-2/flex-image-to-image":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1K"  # Default согласно документации
    
    # Применяем дефолты для flux-2/flex-text-to-image
    if model_id == "flux-2/flex-text-to-image":
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1K"  # Default согласно документации
    
    # Применяем дефолты для nano-banana-pro
    if model_id in ["nano-banana-pro", "google/nano-banana-pro"]:
        if 'image_input' not in normalized_input:
            normalized_input['image_input'] = []  # Default согласно документации
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "1K"  # Default согласно документации
        if 'output_format' not in normalized_input:
            normalized_input['output_format'] = "png"  # Default согласно документации
    
    # Применяем дефолты для bytedance/v1-pro-fast-image-to-video
    if model_id == "bytedance/v1-pro-fast-image-to-video":
        if 'resolution' not in normalized_input:
            normalized_input['resolution'] = "720p"  # Default согласно документации
        if 'duration' not in normalized_input:
            normalized_input['duration'] = "5"  # Default согласно документации
    
    # Применяем дефолты для grok-imagine/image-to-video
    if model_id in ["grok-imagine/image-to-video", "grok/imagine"]:
        if 'index' not in normalized_input:
            normalized_input['index'] = 0  # Default согласно документации
        if 'mode' not in normalized_input:
            normalized_input['mode'] = "normal"  # Default согласно документации
    
    # Применяем дефолты для grok-imagine/text-to-video
    if model_id in ["grok-imagine/text-to-video", "grok/imagine-text-to-video"]:
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "2:3"  # Default согласно документации
        if 'mode' not in normalized_input:
            normalized_input['mode'] = "normal"  # Default согласно документации
    
    # Применяем дефолты для grok-imagine/text-to-image
    if model_id in ["grok-imagine/text-to-image", "grok/imagine-text-to-image"]:
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "3:2"  # Default согласно документации (отличается от text-to-video!)
        # ВАЖНО: Нет параметра mode для text-to-image (в отличие от text-to-video и image-to-video)
    
    # Применяем дефолты для kling-2.6/image-to-video
    if model_id == "kling-2.6/image-to-video":
        if 'sound' not in normalized_input:
            normalized_input['sound'] = False  # Default согласно документации
        if 'duration' not in normalized_input:
            normalized_input['duration'] = "5"  # Default согласно документации
    
    # Применяем дефолты для kling-2.6/text-to-video
    if model_id == "kling-2.6/text-to-video":
        if 'sound' not in normalized_input:
            normalized_input['sound'] = False  # Default согласно документации
        if 'aspect_ratio' not in normalized_input:
            normalized_input['aspect_ratio'] = "1:1"  # Default согласно документации
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

