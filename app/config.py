"""
Централизованная конфигурация из ENV переменных.
ВСЕ секреты ТОЛЬКО из ENV, никаких .env файлов в репо.
"""

import os
from typing import Optional


def must_env(name: str) -> str:
    """
    Получает обязательную переменную окружения.
    
    Args:
        name: Имя переменной окружения
    
    Returns:
        Значение переменной
    
    Raises:
        RuntimeError: Если переменная не установлена
    """
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env: {name}")
    return v


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Получает опциональную переменную окружения.
    
    Args:
        name: Имя переменной окружения
        default: Значение по умолчанию
    
    Returns:
        Значение переменной или default
    """
    return os.getenv(name, default)


# ==================== ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ====================

# Telegram Bot Token (обязательно)
BOT_TOKEN = must_env("TELEGRAM_BOT_TOKEN")

# Database URL (обязательно для продакшн)
DATABASE_URL = get_env("DATABASE_URL")

# ==================== ОПЦИОНАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================

# Окружение (prod, dev, test)
ENV = get_env("ENV", "prod")

# Режим работы бота (polling | webhook)
BOT_MODE = get_env("BOT_MODE", "polling")

# Webhook URL (только если BOT_MODE=webhook)
WEBHOOK_URL = get_env("WEBHOOK_URL")

# Порт для webhook (только если BOT_MODE=webhook)
PORT = int(get_env("PORT", "10000"))

# KIE API
KIE_API_KEY = get_env("KIE_API_KEY")
KIE_API_URL = get_env("KIE_API_URL", "https://api.kie.ai")

# Admin
ADMIN_ID = int(get_env("ADMIN_ID", "0")) if get_env("ADMIN_ID") else None

# Режимы работы
ALLOW_REAL_GENERATION = get_env("ALLOW_REAL_GENERATION", "1") == "1"
TEST_MODE = get_env("TEST_MODE", "0") == "1"
DRY_RUN = get_env("DRY_RUN", "0") == "1"

# Database
DB_MAXCONN = int(get_env("DB_MAXCONN", "3"))

# Другие настройки
CREDIT_TO_RUB_RATE = float(get_env("CREDIT_TO_RUB_RATE", "0.1"))
KIE_TIMEOUT_SECONDS = int(get_env("KIE_TIMEOUT_SECONDS", "30"))
MAX_CONCURRENT_GENERATIONS_PER_USER = int(get_env("MAX_CONCURRENT_GENERATIONS_PER_USER", "3"))

# Платежи (опционально)
PAYMENT_BANK = get_env("PAYMENT_BANK")
PAYMENT_CARD_HOLDER = get_env("PAYMENT_CARD_HOLDER")
PAYMENT_PHONE = get_env("PAYMENT_PHONE")

# Поддержка (опционально)
SUPPORT_TELEGRAM = get_env("SUPPORT_TELEGRAM")
SUPPORT_TEXT = get_env("SUPPORT_TEXT")





