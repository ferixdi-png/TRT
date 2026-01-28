"""
Конфигурация приложения.
"""

from .validation import ConfigValidator, ConfigValidationError, validate_config_on_startup

# Глобальная переменная для кэша функции
_original_get_settings = None

def get_settings(validate: bool = False):
    """Получить глобальный экземпляр Settings (singleton)"""
    global _original_get_settings
    if _original_get_settings is None:
        # Отложенный импорт только при вызове функции
        import importlib.util
        import os
        
        # Импортируем config.py из корня проекта
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "config.py")
        spec = importlib.util.spec_from_file_location("config_module", config_path)
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        _original_get_settings = config_module.get_settings
    
    return _original_get_settings(validate)

__all__ = [
    "ConfigValidator",
    "ConfigValidationError", 
    "validate_config_on_startup",
    "get_settings"
]
