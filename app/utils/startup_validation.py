"""
Startup validation - проверка обязательных ENV переменных при старте
"""

import os
import sys
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Обязательные ENV ключи (контракт)
REQUIRED_ENV_KEYS = [
    'ADMIN_ID',
    'BOT_MODE',
    'DATABASE_URL',
    'DB_MAXCONN',
    'KIE_API_KEY',
    'PAYMENT_BANK',
    'PAYMENT_CARD_HOLDER',
    'PAYMENT_PHONE',
    'PORT',
    'SUPPORT_TELEGRAM',
    'SUPPORT_TEXT',
    'TELEGRAM_BOT_TOKEN',
    'WEBHOOK_BASE_URL',
]


def validate_env_keys() -> Tuple[bool, List[str]]:
    """
    Валидирует наличие всех обязательных ENV ключей.
    
    Returns:
        Tuple[bool, List[str]]: (is_valid, missing_keys)
    """
    missing = []
    
    for key in REQUIRED_ENV_KEYS:
        value = os.getenv(key, '').strip()
        if not value:
            missing.append(key)
    
    return len(missing) == 0, missing


def validate_env_key_format(key: str) -> bool:
    """
    Валидирует формат значения ENV ключа (базовая проверка).
    
    Args:
        key: Имя ENV переменной
        
    Returns:
        True если значение валидно, False иначе
    """
    value = os.getenv(key, '').strip()
    
    if not value:
        return False
    
    # Специфичные проверки для некоторых ключей
    if key == 'ADMIN_ID':
        try:
            int(value)
            return True
        except ValueError:
            return False
    
    if key == 'PORT':
        try:
            port = int(value)
            return 1 <= port <= 65535
        except ValueError:
            return False
    
    if key == 'DB_MAXCONN':
        try:
            maxconn = int(value)
            return maxconn > 0
        except ValueError:
            return False
    
    if key == 'BOT_MODE':
        return value.lower() in ('polling', 'webhook', 'auto', 'passive')
    
    # Для остальных - просто проверяем что не пусто
    return True


def startup_validation() -> bool:
    """
    Выполняет полную валидацию при старте приложения.
    
    Returns:
        True если все проверки пройдены, иначе False (и выходит с sys.exit)
    """
    logger.info("=" * 60)
    logger.info("STARTUP VALIDATION")
    logger.info("=" * 60)
    
    # Проверка наличия ключей
    is_valid, missing = validate_env_keys()
    
    if not is_valid:
        logger.error("=" * 60)
        logger.error("MISSING REQUIRED ENVIRONMENT VARIABLES")
        logger.error("=" * 60)
        for key in missing:
            logger.error(f"  - {key}")
        logger.error("=" * 60)
        logger.error("Please set all required environment variables.")
        logger.error("See docs/env.md for details.")
        logger.error("=" * 60)
        sys.exit(1)
    
    # Проверка формата значений
    format_errors = []
    for key in REQUIRED_ENV_KEYS:
        if not validate_env_key_format(key):
            format_errors.append(key)
    
    if format_errors:
        logger.error("=" * 60)
        logger.error("INVALID ENVIRONMENT VARIABLE FORMATS")
        logger.error("=" * 60)
        for key in format_errors:
            value = os.getenv(key, '')
            # Маскируем значение для безопасности
            from app.utils.mask import mask
            masked_value = mask(value) if value else '[EMPTY]'
            logger.error(f"  - {key}: {masked_value}")
        logger.error("=" * 60)
        logger.error("Please check environment variable formats.")
        logger.error("See docs/env.md for details.")
        logger.error("=" * 60)
        sys.exit(1)
    
    # Логируем успех (без значений)
    logger.info("✅ All required environment variables are set")
    logger.info(f"✅ Validated {len(REQUIRED_ENV_KEYS)} environment variables")
    logger.info("=" * 60)
    
    return True

