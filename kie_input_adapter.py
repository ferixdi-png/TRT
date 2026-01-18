"""
KIE Input Adapter - адаптация параметров для KIE API

Этот модуль обеспечивает:
1. Загрузку схемы из YAML
2. Применение дефолтных значений
3. Валидацию параметров по YAML (до адаптации)
4. Адаптацию внутренних параметров к формату API

Архитектура:
- Валидация работает с внутренними параметрами (как в YAML)
- Адаптация преобразует внутренние параметры в API формат
- Таблица маппингов для специальных случаев моделей
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

# Путь к YAML файлу
MODELS_YAML_PATH = Path("models/kie_models.yaml")

# Кэш загруженной схемы
_models_registry: Optional[Dict[str, Any]] = None


def load_models_registry() -> Dict[str, Any]:
    """Загружает реестр моделей из YAML."""
    global _models_registry
    if _models_registry is not None:
        return _models_registry
    
    # Определяем путь к YAML файлу
    yaml_path = MODELS_YAML_PATH
    if not yaml_path.exists():
        # Пытаемся найти относительно текущего файла
        current_file = Path(__file__)
        project_root = current_file.parent
        yaml_path = project_root / "models" / "kie_models.yaml"
        if not yaml_path.exists():
            logger.error(f"Models registry not found: {MODELS_YAML_PATH} or {yaml_path}")
            return {}
    
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            _models_registry = yaml.safe_load(f)
        return _models_registry
    except Exception as e:
        logger.error(f"Failed to load models registry: {e}", exc_info=True)
        return {}


def get_schema(model_id: str) -> Optional[Dict[str, Any]]:
    """
    Получает схему параметров модели из YAML.
    
    Returns:
        Словарь с параметрами (ключ = имя параметра, значение = схема параметра)
        или None если модель не найдена
    """
    registry = load_models_registry()
    model_info = registry.get('models', {}).get(model_id)
    if not model_info:
        return None
    return model_info.get('input', {})


API_PARAM_MAPPINGS: Dict[str, Dict[str, str]] = {}


def apply_defaults(schema: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Применяет дефолтные значения из схемы к параметрам.
    
    Args:
        schema: Схема параметров из YAML
        params: Текущие параметры
    
    Returns:
        Параметры с примененными дефолтами
    """
    result = params.copy()
    
    for param_name, param_schema in schema.items():
        if param_name not in result:
            # Проверяем default в схеме (может быть в разных форматах)
            default_value = param_schema.get('default')
            if default_value is not None:
                result[param_name] = default_value
    
    return result


def validate_params(schema: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Валидирует параметры по схеме из YAML.
    
    Использует kie_validator для валидации, но работает строго с внутренними параметрами
    (до адаптации к API).
    
    Args:
        schema: Схема параметров из YAML
        params: Параметры для валидации
    
    Returns:
        (is_valid, list_of_errors)
    """
    from kie_validator import validate
    
    # Создаем временный словарь model_id -> schema для валидатора
    # Валидатор ожидает model_id, но мы можем обойти это, создав mock модель
    # Для упрощения, используем прямое валидацию по схеме
    
    errors = []
    
    # Проверка обязательных полей
    for param_name, param_schema in schema.items():
        is_required = param_schema.get('required', False)
        param_value = params.get(param_name)
        
        if is_required and (param_value is None or param_value == ""):
            errors.append(f"Параметр '{param_name}' обязателен для заполнения")
            continue
        
        if param_value is None:
            continue  # Опциональный параметр не указан
        
        param_type = param_schema.get('type', 'string')
        
        # Валидация типа
        if param_type == 'string':
            if not isinstance(param_value, str):
                errors.append(f"Параметр '{param_name}' должен быть текстом")
                continue
            
            # Проверка длины
            if 'max' in param_schema:
                if len(param_value) > param_schema['max']:
                    errors.append(f"Параметр '{param_name}' не должен превышать {param_schema['max']} символов")
        
        elif param_type == 'enum':
            valid_values = param_schema.get('enum') or param_schema.get('values', [])
            if param_value not in valid_values:
                valid_str = ', '.join(map(str, valid_values))
                errors.append(f"Параметр '{param_name}' должен быть одним из: {valid_str} (указано: '{param_value}')")
        
        elif param_type == 'array':
            if not isinstance(param_value, list):
                errors.append(f"Параметр '{param_name}' должен быть списком")
                continue
            
            if len(param_value) == 0 and is_required:
                errors.append(f"Параметр '{param_name}' обязателен и не может быть пустым")
                continue
            
            # Валидация элементов массива
            item_type = param_schema.get('item_type', 'string')
            if item_type == 'string':
                for idx, item in enumerate(param_value):
                    if not isinstance(item, str):
                        errors.append(f"Элемент {idx+1} параметра '{param_name}' должен быть текстом")
                        continue
                    
                    # URL валидация
                    if 'url' in param_name.lower() or 'image' in param_name.lower() or 'video' in param_name.lower():
                        if not (item.startswith('http://') or item.startswith('https://')):
                            errors.append(f"Элемент {idx+1} параметра '{param_name}' должен быть валидным URL")
        
        elif param_type == 'boolean':
            if not isinstance(param_value, bool):
                # Попытка преобразовать строку в boolean
                if isinstance(param_value, str):
                    if param_value.lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
                        errors.append(f"Параметр '{param_name}' должен быть булевым значением")
                else:
                    errors.append(f"Параметр '{param_name}' должен быть булевым значением")
        
        elif param_type in ('number', 'integer', 'float'):
            try:
                float(param_value)
            except (ValueError, TypeError):
                errors.append(f"Параметр '{param_name}' должен быть числом")
    
    return len(errors) == 0, errors


def adapt_to_api(model_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Адаптирует внутренние параметры к формату API.
    Возвращает только параметры, описанные в schema.
    
    Args:
        model_id: ID модели
        params: Внутренние параметры (как в YAML)
    
    Returns:
        Параметры в формате API
    """
    schema = get_schema(model_id) or {}
    return {key: params[key] for key in schema if key in params}


def normalize_for_generation(model_id: str, params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Полный цикл нормализации параметров для генерации:
    1. Получает схему
    2. Применяет дефолты
    3. Валидирует
    4. Адаптирует к API
    
    Args:
        model_id: ID модели
        params: Сырые параметры
    
    Returns:
        (api_params, errors) где errors - список ошибок валидации (пустой если все ок)
    """
    # 1. Получаем схему
    schema = get_schema(model_id)
    if not schema:
        logger.warning(f"Model {model_id} not found in registry, skipping normalization")
        return params, []
    
    # 2. Применяем дефолты
    params_with_defaults = apply_defaults(schema, params)
    
    # 3. Валидируем внутренние параметры
    is_valid, errors = validate_params(schema, params_with_defaults)
    if not is_valid:
        return {}, errors
    
    # 4. Адаптируем к API
    api_params = adapt_to_api(model_id, params_with_defaults)
    
    return api_params, []
