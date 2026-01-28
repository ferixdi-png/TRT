"""
Конфигурация приложения.
"""

from .validation import ConfigValidator, ConfigValidationError, validate_config_on_startup

# Отложенный импорт для избежания circular import
def get_settings(validate: bool = False):
    """Получить глобальный экземпляр Settings (singleton)"""
    from ..config import get_settings as _get_settings
    return _get_settings(validate)

__all__ = [
    "ConfigValidator",
    "ConfigValidationError", 
    "validate_config_on_startup",
    "get_settings"
]
