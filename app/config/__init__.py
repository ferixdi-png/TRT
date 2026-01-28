"""
Конфигурация приложения.
"""

import os
from .validation import ConfigValidator, ConfigValidationError, validate_config_on_startup

# Глобальные переменные для кэша
_original_get_settings = None
_Settings_class = None

# Экспорт переменных окружения для совместимости с bot_kie.py
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
BOT_MODE = os.getenv('BOT_MODE', 'polling').lower()
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '').strip()

def get_settings(validate: bool = False):
    """Получить глобальный экземпляр Settings (singleton)"""
    global _original_get_settings
    if _original_get_settings is None:
        # Отложенный импорт только при вызове функции
        # Импортируем НАПРЯМУЮ из app/config.py, минуя deprecated config.py
        import importlib.util
        import os
        
        # Импортируем app/config.py (не корневой config.py!)
        app_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
        spec = importlib.util.spec_from_file_location("app_config_module", app_config_path)
        app_config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_config_module)
        _original_get_settings = app_config_module.get_settings
    
    return _original_get_settings(validate)

def get_Settings_class():
    """Получить класс Settings для импорта"""
    global _Settings_class
    if _Settings_class is None:
        # Отложенный импорт только при вызове функции
        import importlib.util
        import os
        
        # Импортируем app/config.py (не корневой config.py)
        app_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
        spec = importlib.util.spec_from_file_location("app_config_module", app_config_path)
        app_config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_config_module)
        _Settings_class = app_config_module.Settings
    
    return _Settings_class

# Создаем alias для Settings
Settings = get_Settings_class()

def reset_settings():
    """Сбросить кэшированные настройки (для тестов)"""
    global _original_get_settings, _Settings_class
    _original_get_settings = None
    _Settings_class = None

__all__ = [
    "ConfigValidator",
    "ConfigValidationError", 
    "validate_config_on_startup",
    "get_settings",
    "Settings",
    "reset_settings",
    "BOT_TOKEN",
    "BOT_MODE",
    "WEBHOOK_URL",
]
