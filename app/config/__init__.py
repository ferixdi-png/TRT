"""
Конфигурация приложения.
"""

from .validation import ConfigValidator, ConfigValidationError, validate_config_on_startup

# Прямой импорт оригинальной функции для избежания рекурсии
import sys
import os

# Добавляем путь к корню проекта для прямого импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Импортируем оригинальный модуль config напрямую
try:
    import config as original_config_module
    _original_get_settings = original_config_module.get_settings
except ImportError:
    # Fallback если прямой импорт не сработал
    _original_get_settings = None

def get_settings(validate: bool = False):
    """Получить глобальный экземпляр Settings (singleton)"""
    if _original_get_settings is not None:
        return _original_get_settings(validate)
    # Fallback - пробуем импортировать при вызове
    from ..config import get_settings as _fallback_get_settings
    return _fallback_get_settings(validate)

__all__ = [
    "ConfigValidator",
    "ConfigValidationError", 
    "validate_config_on_startup",
    "get_settings"
]
