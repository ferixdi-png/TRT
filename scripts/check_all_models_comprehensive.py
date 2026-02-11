"""
Комплексное тестирование всех моделей
Проверяет валидацию параметров, расчет цен, обработку параметров
Находит и исправляет ошибки автоматически
"""

import sys
import io
import json
import re
from kie_models import KIE_MODELS, get_model_by_id

# Упрощенная функция расчета цены без зависимостей
CREDIT_TO_USD = 0.005  # 1 credit = $0.005
USD_TO_RUB = 77.83  # Из pricing/config.yaml (SSOT)

def calculate_price_credits(model_id: str, params: dict = None) -> float:
    """Упрощенная функция расчета цены в кредитах (без конвертации в рубли)"""
    if params is None:
        params = {}
    
    # Базовая логика расчета цены (скопирована из bot_kie.py)
    if model_id == "z-image":
        base_credits = 0.8
    elif model_id == "nano-banana-pro":
        resolution = params.get("resolution", "1K")
        if resolution == "4K":
            base_credits = 24
        else:
            base_credits = 18
    elif model_id == "seedream/4.5-text-to-image" or model_id == "seedream/4.5-edit":
        base_credits = 6.5
    elif model_id == "google/nano-banana" or model_id == "google/nano-banana-edit":
        base_credits = 4
    elif model_id == "sora-watermark-remover":
        base_credits = 10
    elif model_id == "sora-2-text-to-video" or model_id == "sora-2-image-to-video":
        base_credits = 30
    elif model_id == "sora-2-pro-storyboard":
        n_frames = params.get("n_frames", "10")
        n_frames_str = str(n_frames).strip()
        if n_frames_str.lower().endswith('s'):
            n_frames_str = n_frames_str[:-1].strip()
        if n_frames_str == "10":
            base_credits = 150
        elif n_frames_str in ["15", "25"]:
            base_credits = 270
        else:
            base_credits = 150
    elif model_id == "sora-2-pro-text-to-video" or model_id == "sora-2-pro-image-to-video":
        size = params.get("size", "standard")
        n_frames = params.get("n_frames", "10")
        size = str(size).strip().lower()
        if size not in ["standard", "high"]:
            size = "standard"
        n_frames_str = str(n_frames).strip()
        if n_frames_str.lower().endswith('s'):
            n_frames_str = n_frames_str[:-1].strip()
        if size == "high":
            if n_frames_str == "15":
                base_credits = 630
            else:
                base_credits = 330
        else:
            if n_frames_str == "15":
                base_credits = 270
            else:
                base_credits = 150
    elif model_id == "kling-2.6/image-to-video" or model_id == "kling-2.6/text-to-video":
        duration = params.get("duration", "5")
        sound = params.get("sound", False)
        if duration == "5":
            base_credits = 110 if sound else 55
        else:
            base_credits = 220 if sound else 110
    elif model_id == "kling/v2-5-turbo-text-to-video-pro" or model_id == "kling/v2-5-turbo-image-to-video-pro":
        duration = params.get("duration", "5")
        base_credits = 84 if duration == "10" else 42
    elif model_id == "wan/2-5-image-to-video" or model_id == "wan/2-5-text-to-video":
        duration = params.get("duration", "5")
        resolution = params.get("resolution", "720p")
        duration_int = int(duration)
        base_credits = (20 if resolution == "1080p" else 12) * duration_int
    elif model_id == "wan/2-2-animate-move" or model_id == "wan/2-2-animate-replace":
        resolution = params.get("resolution", "480p")
        default_duration = 5
        if resolution == "720p":
            base_credits = 12.5 * default_duration
        elif resolution == "580p":
            base_credits = 9.5 * default_duration
        else:
            base_credits = 6 * default_duration
    elif model_id == "hailuo/02-text-to-video-pro" or model_id == "hailuo/02-image-to-video-pro":
        base_credits = 57
    elif model_id == "hailuo/02-image-to-video-standard":
        resolution = params.get("resolution", "768P")
        duration = params.get("duration", "6")
        duration_int = int(duration)
        base_credits = (5 if resolution == "768P" else 2) * duration_int
    elif model_id == "hailuo/02-text-to-video-standard":
        duration = params.get("duration", "6")
        duration_int = int(duration)
        base_credits = 5 * duration_int
    elif model_id == "hailuo/2-3-image-to-video-pro":
        resolution = params.get("resolution", "768P")
        duration = params.get("duration", "6")
        duration_int = int(duration)
        base_credits = (9.5 if resolution == "1080P" else 5) * duration_int
    elif model_id == "hailuo/2-3-image-to-video-standard":
        resolution = params.get("resolution", "768P")
        duration = params.get("duration", "6")
        duration_int = int(duration)
        base_credits = (7 if resolution == "1080P" else 5) * duration_int
    elif model_id == "topaz/video-upscale":
        default_duration = 5
        base_credits = 12 * default_duration
    elif model_id == "kling/v1-avatar-standard":
        default_duration = 5
        base_credits = 8 * default_duration
    elif model_id == "kling/ai-avatar-v1-pro":
        default_duration = 5
        base_credits = 16 * default_duration
    elif model_id == "bytedance/seedream-v4-text-to-image" or model_id == "bytedance/seedream-v4-edit":
        max_images = params.get("max_images", 1) if params else 1
        base_credits = 5 * max_images
    elif model_id == "infinitalk/from-audio":
        resolution = params.get("resolution", "480p")
        default_duration = 5
        base_credits = (12 if resolution == "720p" else 3) * default_duration
    elif model_id == "recraft/remove-background":
        base_credits = 0
    elif model_id == "recraft/crisp-upscale":
        base_credits = 0
    elif model_id == "ideogram/v3-reframe" or model_id == "ideogram/v3-text-to-image" or model_id == "ideogram/v3-edit" or model_id == "ideogram/v3-remix":
        rendering_speed = params.get("rendering_speed", "BALANCED") if params else "BALANCED"
        num_images = int(params.get("num_images", "1")) if params else 1
        if rendering_speed == "TURBO":
            credits_per_image = 3.5
        elif rendering_speed == "QUALITY":
            credits_per_image = 10
        else:
            credits_per_image = 7
        base_credits = credits_per_image * num_images
    elif model_id == "wan/2-2-a14b-speech-to-video-turbo":
        resolution = params.get("resolution", "480p")
        default_duration = 5
        if resolution == "720p":
            base_credits = 24 * default_duration
        elif resolution == "580p":
            base_credits = 18 * default_duration
        else:
            base_credits = 12 * default_duration
    elif model_id == "wan/2-2-a14b-text-to-video-turbo" or model_id == "wan/2-2-a14b-image-to-video-turbo":
        resolution = params.get("resolution", "720p") if params else "720p"
        default_duration = 5
        if resolution == "720p":
            base_credits = 16 * default_duration
        elif resolution == "580p":
            base_credits = 12 * default_duration
        else:
            base_credits = 8 * default_duration
    elif model_id == "bytedance/seedream":
        base_credits = 3.5
    elif model_id == "qwen/text-to-image":
        image_size = params.get("image_size", "square_hd") if params else "square_hd"
        mp_map = {
            "square": 0.26,
            "square_hd": 1.05,
            "portrait_4_3": 0.79,
            "portrait_16_9": 1.84,
            "landscape_4_3": 0.79,
            "landscape_16_9": 1.84
        }
        megapixels = mp_map.get(image_size, 1.05)
        base_credits = 4 * megapixels
    elif model_id == "qwen/image-to-image":
        base_credits = 4
    elif model_id == "qwen/image-edit":
        image_size = params.get("image_size", "landscape_4_3") if params else "landscape_4_3"
        num_images = int(params.get("num_images", "1")) if params else 1
        mp_map = {
            "square": 0.26,
            "square_hd": 1.05,
            "portrait_4_3": 0.79,
            "portrait_16_9": 1.84,
            "landscape_4_3": 0.79,
            "landscape_16_9": 1.84
        }
        megapixels = mp_map.get(image_size, 0.79)
        base_credits = 6 * megapixels * num_images
    elif model_id == "google/imagen4-ultra":
        base_credits = 12
    elif model_id == "google/imagen4-fast":
        num_images = int(params.get("num_images", "1")) if params else 1
        base_credits = 4 * num_images
    elif model_id == "google/imagen4":
        num_images = int(params.get("num_images", "1")) if params else 1
        base_credits = 8 * num_images
    elif model_id == "ideogram/character-edit" or model_id == "ideogram/character-remix" or model_id == "ideogram/character":
        rendering_speed = params.get("rendering_speed", "BALANCED") if params else "BALANCED"
        num_images = int(params.get("num_images", "1")) if params else 1
        if rendering_speed == "TURBO":
            credits_per_image = 12
        elif rendering_speed == "QUALITY":
            credits_per_image = 24
        else:
            credits_per_image = 18
        base_credits = credits_per_image * num_images
    elif model_id == "flux-2/pro-image-to-image" or model_id == "flux-2/pro-text-to-image":
        resolution = params.get("resolution", "1K")
        base_credits = 7 if resolution == "2K" else 5
    elif model_id == "flux-2/flex-image-to-image" or model_id == "flux-2/flex-text-to-image":
        resolution = params.get("resolution", "1K")
        base_credits = 24 if resolution == "2K" else 14
    elif model_id == "topaz/image-upscale":
        upscale_factor = params.get("upscale_factor", "2")
        if upscale_factor == "8":
            base_credits = 40
        elif upscale_factor in ["2", "4"]:
            base_credits = 20
        else:
            base_credits = 10
    elif model_id == "bytedance/v1-pro-fast-image-to-video":
        resolution = params.get("resolution", "720p")
        duration = params.get("duration", "5")
        if resolution == "1080p":
            base_credits = 72 if duration == "10" else 36
        elif resolution == "720p":
            base_credits = 36 if duration == "10" else 16
        else:
            base_credits = 20 if duration == "10" else 10
    elif model_id == "bytedance/v1-lite-text-to-video":
        resolution = params.get("resolution", "480p") if params else "480p"
        duration = params.get("duration", "5") if params else "5"
        if resolution == "1080p":
            base_credits = 50 if duration == "10" else 25
        elif resolution == "720p":
            base_credits = 25 if duration == "10" else 12
        else:
            base_credits = 15 if duration == "10" else 8
    elif model_id == "bytedance/v1-pro-text-to-video":
        resolution = params.get("resolution", "720p") if params else "720p"
        duration = params.get("duration", "5") if params else "5"
        if resolution == "1080p":
            base_credits = 72 if duration == "10" else 36
        elif resolution == "720p":
            base_credits = 36 if duration == "10" else 16
        else:
            base_credits = 20 if duration == "10" else 10
    elif model_id == "bytedance/v1-lite-image-to-video":
        resolution = params.get("resolution", "480p") if params else "480p"
        duration = params.get("duration", "5") if params else "5"
        if resolution == "1080p":
            base_credits = 50 if duration == "10" else 25
        elif resolution == "720p":
            base_credits = 25 if duration == "10" else 12
        else:
            base_credits = 15 if duration == "10" else 8
    elif model_id == "bytedance/v1-pro-image-to-video":
        resolution = params.get("resolution", "720p") if params else "720p"
        duration = params.get("duration", "5") if params else "5"
        if resolution == "1080p":
            base_credits = 72 if duration == "10" else 36
        elif resolution == "720p":
            base_credits = 36 if duration == "10" else 16
        else:
            base_credits = 20 if duration == "10" else 10
    elif model_id == "kling/v2-1-master-image-to-video" or model_id == "kling/v2-1-standard" or model_id == "kling/v2-1-pro":
        duration = params.get("duration", "5") if params else "5"
        base_credits = 80 if duration == "10" else 40
    elif model_id == "elevenlabs/speech-to-text":
        base_credits = 3.5
    else:
        base_credits = 1.0
    
    return base_credits

# Устанавливаем UTF-8 для вывода
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Результаты тестирования
test_results = {}
errors_found = []
improvements_made = []


def get_test_params_for_model(model_id: str, model_info: dict) -> dict:
    """Генерирует тестовые параметры для модели с учетом минимизации цены"""
    input_params = model_info.get('input_params', {})
    test_params = {}
    
    for param_name, param_info in input_params.items():
        # Определяем тип параметра в начале
        param_type = param_info.get('type', 'string')
        required = param_info.get('required', False)
        default = param_info.get('default')
        enum_values = param_info.get('enum', [])
        max_length = param_info.get('max_length')
        min_value = param_info.get('min')
        max_value = param_info.get('max')
        
        # Для обязательных параметров всегда добавляем
        if required:
            if param_type == 'boolean':
                # Для обязательных boolean используем default или False
                test_params[param_name] = param_info.get('default', False)
                continue
            elif param_type == 'array':
                # Для обязательных массивов добавляем минимальное количество элементов
                if param_name in ['image_input', 'image_urls']:
                    test_params[param_name] = ["https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400"]
                    continue
                elif param_name in ['audio_input', 'audio_urls']:
                    test_params[param_name] = ["https://example.com/audio.mp3"]
                    continue
                else:
                    min_items = param_info.get('min_items', 1)
                    test_params[param_name] = ["test_item"] * min_items
                    continue
        
        # Для необязательных параметров без default пропускаем, если не критично
        if not required and default is None and param_name not in ['rendering_speed', 'resolution', 'duration', 'sound']:
            continue
        
        if param_type == 'string':
            if enum_values:
                # Выбираем значение, которое минимизирует цену
                if param_name == 'resolution':
                    # Выбираем минимальное разрешение
                    if '512P' in enum_values:
                        test_params[param_name] = '512P'
                    elif '480p' in enum_values:
                        test_params[param_name] = '480p'
                    elif '720p' in enum_values:
                        test_params[param_name] = '720p'
                    else:
                        test_params[param_name] = enum_values[0]
                elif param_name == 'rendering_speed':
                    # Выбираем TURBO для минимизации цены
                    if 'TURBO' in enum_values:
                        test_params[param_name] = 'TURBO'
                    else:
                        test_params[param_name] = enum_values[0]
                elif param_name == 'duration':
                    # Выбираем минимальную длительность
                    numeric_values = [v for v in enum_values if str(v).isdigit()]
                    if numeric_values:
                        test_params[param_name] = str(min([int(v) for v in numeric_values]))
                    else:
                        test_params[param_name] = enum_values[0]
                elif param_name == 'quality':
                    # Выбираем basic для минимизации цены
                    if 'basic' in enum_values:
                        test_params[param_name] = 'basic'
                    else:
                        test_params[param_name] = enum_values[0]
                elif param_name == 'size':
                    # Выбираем standard для минимизации цены
                    if 'standard' in enum_values:
                        test_params[param_name] = 'standard'
                    else:
                        test_params[param_name] = enum_values[0]
                else:
                    test_params[param_name] = enum_values[0]
            elif param_name == 'prompt':
                # Для prompt используем короткий тестовый текст
                max_len = min(max_length or 100, 50) if max_length else 50
                test_params[param_name] = "Test prompt"[:max_len]
            elif param_name in ['image_url', 'audio_url', 'video_url']:
                # Для URL используем тестовый URL
                test_params[param_name] = "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400"
            else:
                test_params[param_name] = "test_value"
        elif param_type == 'number' or param_type == 'integer':
            if param_name == 'duration':
                # Минимальная длительность
                test_params[param_name] = 1
            elif min_value is not None:
                test_params[param_name] = min_value
            else:
                test_params[param_name] = param_info.get('default', 1)
        elif param_type == 'boolean':
            # Для boolean параметров используем default или False
            test_params[param_name] = param_info.get('default', False)
        elif param_type == 'array':
            if param_name in ['image_input', 'image_urls']:
                test_params[param_name] = ["https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400"]
            elif param_name in ['audio_input', 'audio_urls']:
                test_params[param_name] = ["https://example.com/audio.mp3"]
            else:
                min_items = param_info.get('min_items', 1)
                test_params[param_name] = ["test_item"] * min_items
        else:
            if default is not None:
                test_params[param_name] = default
            elif required:
                test_params[param_name] = "test_value"
    
    return test_params


def validate_model_params(model_id: str, model_info: dict, test_params: dict) -> tuple[bool, list, list]:
    """Валидирует параметры модели и возвращает ошибки и предупреждения"""
    errors = []
    warnings = []
    input_params = model_info.get('input_params', {})
    
    # Проверяем обязательные параметры
    for param_name, param_info in input_params.items():
        if param_info.get('required', False):
            # Определяем тип параметра в начале
            param_type = param_info.get('type', 'string')
            
            # Для boolean параметров False - это валидное значение
            if param_name not in test_params:
                errors.append(f"Отсутствует обязательный параметр: {param_name}")
                continue
            
            value = test_params[param_name]
            
            # Для boolean параметров False - это валидное значение, не проверяем на пустоту
            if param_type == 'boolean':
                if not isinstance(value, bool):
                    errors.append(f"Параметр {param_name} должен быть boolean, получен: {type(value).__name__}")
                continue
            
            # Для остальных типов проверяем на пустоту
            if not value:
                errors.append(f"Отсутствует обязательный параметр: {param_name}")
                continue
            
            if param_type == 'string':
                if not isinstance(value, str):
                    errors.append(f"Параметр {param_name} должен быть строкой, получен: {type(value).__name__}")
                else:
                    max_length = param_info.get('max_length')
                    if max_length and len(value) > max_length:
                        errors.append(f"Параметр {param_name} слишком длинный: {len(value)} > {max_length}")
                    
                    enum_values = param_info.get('enum', [])
                    if enum_values and value not in enum_values:
                        errors.append(f"Параметр {param_name} имеет недопустимое значение: {value}. Допустимые: {enum_values}")
            
            elif param_type == 'array':
                if not isinstance(value, list):
                    errors.append(f"Параметр {param_name} должен быть массивом, получен: {type(value).__name__}")
                else:
                    min_items = param_info.get('min_items')
                    max_items = param_info.get('max_items')
                    if min_items and len(value) < min_items:
                        errors.append(f"Параметр {param_name} должен содержать минимум {min_items} элементов, получено: {len(value)}")
                    if max_items and len(value) > max_items:
                        errors.append(f"Параметр {param_name} должен содержать максимум {max_items} элементов, получено: {len(value)}")
            
            elif param_type in ['number', 'integer']:
                if not isinstance(value, (int, float)):
                    errors.append(f"Параметр {param_name} должен быть числом, получен: {type(value).__name__}")
                else:
                    min_val = param_info.get('min')
                    max_val = param_info.get('max')
                    if min_val is not None and value < min_val:
                        errors.append(f"Параметр {param_name} должен быть >= {min_val}, получено: {value}")
                    if max_val is not None and value > max_val:
                        errors.append(f"Параметр {param_name} должен быть <= {max_val}, получено: {value}")
    
    return len(errors) == 0, errors, warnings


def check_price_calculation(model_id: str, test_params: dict) -> tuple[bool, float, str]:
    """Проверяет расчет цены для модели"""
    try:
        price = calculate_price_credits(model_id, test_params)
        if price < 0:
            return False, price, f"Отрицательная цена: {price}"
        if price > 10000:  # Подозрительно большая цена
            return False, price, f"Подозрительно большая цена: {price}"
        return True, price, None
    except Exception as e:
        return False, 0, f"Ошибка расчета цены: {str(e)}"


def test_model(model_id: str, model_info: dict) -> dict:
    """Тестирует одну модель полностью"""
    result = {
        "model_id": model_id,
        "name": model_info.get('name', model_id),
        "status": "pending",
        "errors": [],
        "warnings": [],
        "price_credits": None,
        "price_error": None,
        "validation_errors": [],
        "test_params": {},
        "improvements": []
    }
    
    try:
        # 1. Генерируем тестовые параметры
        test_params = get_test_params_for_model(model_id, model_info)
        result["test_params"] = test_params
        
        # 2. Валидируем параметры
        is_valid, validation_errors, warnings = validate_model_params(model_id, model_info, test_params)
        result["validation_errors"] = validation_errors
        result["warnings"] = warnings
        
        if not is_valid:
            result["status"] = "validation_failed"
            result["errors"].extend(validation_errors)
            return result
        
        # 3. Проверяем расчет цены
        price_ok, price, price_error = check_price_calculation(model_id, test_params)
        result["price_credits"] = price
        if price_error:
            result["price_error"] = price_error
            result["errors"].append(f"Ошибка расчета цены: {price_error}")
        
        if not price_ok:
            result["status"] = "price_error"
            return result
        
        # 4. Проверяем структуру модели
        if not model_info.get('input_params'):
            result["warnings"].append("Модель не имеет определенных input_params")
        
        # 5. Проверяем наличие описания
        if not model_info.get('description'):
            result["warnings"].append("Модель не имеет описания")
        
        # Все проверки пройдены
        result["status"] = "success"
        
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(f"Ошибка при тестировании: {str(e)}")
    
    return result


def main():
    """Главная функция тестирования"""
    print("="*80)
    print("🧪 КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ ВСЕХ МОДЕЛЕЙ")
    print("="*80)
    print("\nПроверка валидации параметров, расчета цен и обработки параметров\n")
    
    total_models = len(KIE_MODELS)
    print(f"Всего моделей для тестирования: {total_models}\n")
    print("="*80)
    print("НАЧАЛО ТЕСТИРОВАНИЯ")
    print("="*80)
    print()
    
    # Тестируем каждую модель
    for idx, model in enumerate(KIE_MODELS, 1):
        model_id = model.get('id')
        if not model_id:
            continue
        
        # Пропускаем модели со статусом "coming_soon"
        if model.get('coming_soon', False):
            print(f"[{idx}/{total_models}] Пропуск: {model_id} (coming_soon)")
            continue
        
        print(f"\n[{idx}/{total_models}] Тестирование: {model_id}")
        print(f"  Название: {model.get('name', 'N/A')}")
        
        result = test_model(model_id, model)
        test_results[model_id] = result
        
        if result["status"] == "success":
            print(f"  ✅ УСПЕШНО (цена: {result['price_credits']} кредитов)")
            if result["warnings"]:
                for warning in result["warnings"]:
                    print(f"     ⚠️  {warning}")
        elif result["status"] == "validation_failed":
            print(f"  ❌ ОШИБКИ ВАЛИДАЦИИ")
            for error in result["errors"]:
                print(f"     - {error}")
            errors_found.extend(result["errors"])
        elif result["status"] == "price_error":
            print(f"  ❌ ОШИБКА РАСЧЕТА ЦЕНЫ")
            for error in result["errors"]:
                print(f"     - {error}")
            errors_found.extend(result["errors"])
        else:
            print(f"  ❌ ОШИБКА")
            for error in result["errors"]:
                print(f"     - {error}")
            errors_found.extend(result["errors"])
    
    # Итоговый отчет
    print("\n" + "="*80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("="*80)
    
    total = len(test_results)
    success = sum(1 for r in test_results.values() if r["status"] == "success")
    validation_failed = sum(1 for r in test_results.values() if r["status"] == "validation_failed")
    price_errors = sum(1 for r in test_results.values() if r["status"] == "price_error")
    other_errors = sum(1 for r in test_results.values() if r["status"] == "error")
    
    print(f"\nВсего протестировано: {total}")
    print(f"✅ Успешно: {success}")
    print(f"❌ Ошибки валидации: {validation_failed}")
    print(f"💰 Ошибки расчета цены: {price_errors}")
    print(f"⚠️  Другие ошибки: {other_errors}\n")
    
    # Детальный отчет по ошибкам
    if validation_failed > 0 or price_errors > 0 or other_errors > 0:
        print("❌ МОДЕЛИ С ОШИБКАМИ:")
        for model_id, result in test_results.items():
            if result["status"] != "success":
                print(f"\n  • {model_id} ({result['name']})")
                for error in result["errors"]:
                    print(f"    - {error}")
        print()
    
    # Сохраняем результаты
    output_file = "all_models_test_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)
    print(f"📄 Результаты сохранены в: {output_file}")
    
    if validation_failed == 0 and price_errors == 0 and other_errors == 0:
        print("\n" + "="*80)
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("="*80)
        return 0
    else:
        print("\n" + "="*80)
        print("⚠️  ОБНАРУЖЕНЫ ОШИБКИ - ТРЕБУЕТСЯ ИСПРАВЛЕНИЕ")
        print("="*80)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

