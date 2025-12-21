"""
DEPRECATED: Этот модуль существует только для обратной совместимости.
Используйте app.config.get_settings() вместо этого.

Thin wrapper вокруг app.config для runtime режимов.
"""

from app.config import get_settings


def is_test_mode() -> bool:
    """Проверяет, включен ли тестовый режим."""
    settings = get_settings()
    return settings.test_mode


def is_dry_run() -> bool:
    """Проверяет, включен ли режим dry-run (симуляция без реальных операций)."""
    settings = get_settings()
    return settings.dry_run


def allow_real_generation() -> bool:
    """
    Проверяет, разрешены ли реальные генерации.
    """
    settings = get_settings()
    return settings.allow_real_generation


def should_use_mock_gateway() -> bool:
    """
    Определяет, нужно ли использовать mock gateway вместо реального.
    Использует mock если:
    - TEST_MODE=1, или
    - ALLOW_REAL_GENERATION=0
    """
    return is_test_mode() or not allow_real_generation()


def get_config_summary() -> dict:
    """Возвращает словарь с текущей конфигурацией для отладки."""
    settings = get_settings()
    return {
        'TEST_MODE': settings.test_mode,
        'DRY_RUN': settings.dry_run,
        'ALLOW_REAL_GENERATION': settings.allow_real_generation,
        'USE_MOCK_GATEWAY': should_use_mock_gateway(),
    }

