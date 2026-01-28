"""
Конфигурация приложения.
"""

from .validation import ConfigValidator, ConfigValidationError, validate_config_on_startup

# Кэш для избежания повторных импортов
_get_settings_func = None

def get_settings(validate: bool = False):
    """Получить глобальный экземпляр Settings (singleton)"""
    global _get_settings_func
    if _get_settings_func is None:
        from ..config import get_settings as _get_settings_func
    return _get_settings_func(validate)

__all__ = [
    "ConfigValidator",
    "ConfigValidationError", 
    "validate_config_on_startup",
    "get_settings"
]
