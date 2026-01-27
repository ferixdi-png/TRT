"""
Конфигурация приложения.
"""

from .validation import ConfigValidator, ConfigValidationError, validate_config_on_startup

__all__ = [
    "ConfigValidator",
    "ConfigValidationError", 
    "validate_config_on_startup"
]
