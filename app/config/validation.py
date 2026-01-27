"""
Валидация конфигурации на старте.
Проверяет все обязательные ENV переменные и валидирует их значения.
"""

import os
import re
import logging
from typing import List, Tuple, Optional
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Ошибка валидации конфигурации."""
    pass


class ConfigValidator:
    """Валидатор конфигурации приложения."""
    
    REQUIRED_VARS = {
        "TELEGRAM_BOT_TOKEN": {
            "pattern": r"^\d+:[A-Za-z0-9_-]+$",
            "description": "Telegram bot token (format: 123456:ABC-DEF)"
        },
        "DATABASE_URL": {
            "pattern": r"^postgres://",
            "description": "PostgreSQL connection URL"
        },
        "REDIS_URL": {
            "pattern": r"^redis://",
            "description": "Redis connection URL"
        }
    }
    
    OPTIONAL_VARS = {
        "KIE_API_KEY": {
            "pattern": r"^[A-Za-z0-9_-]+$",
            "description": "KIE AI API key"
        },
        "KIE_API_URL": {
            "pattern": r"^https?://",
            "description": "KIE AI API URL"
        },
        "PARTNER_ID": {
            "pattern": r"^[a-zA-Z0-9_-]+$",
            "description": "Partner identifier"
        }
    }
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """Валидирует всю конфигурацию."""
        self.errors.clear()
        self.warnings.clear()
        
        self._validate_required()
        self._validate_optional()
        self._validate_urls()
        self._validate_tokens()
        self._validate_numeric_vars()
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings
    
    def _validate_required(self) -> None:
        """Проверяет обязательные переменные."""
        for var_name, config in self.REQUIRED_VARS.items():
            value = os.getenv(var_name, "").strip()
            
            if not value:
                self.errors.append(f"❌ {var_name}: обязательная переменная не установлена")
                continue
            
            if config.get("pattern") and not re.match(config["pattern"], value):
                self.errors.append(
                    f"❌ {var_name}: неверный формат. Ожидается: {config['description']}"
                )
    
    def _validate_optional(self) -> None:
        """Проверяет опциональные переменные."""
        for var_name, config in self.OPTIONAL_VARS.items():
            value = os.getenv(var_name, "").strip()
            
            if value and config.get("pattern") and not re.match(config["pattern"], value):
                self.warnings.append(
                    f"⚠️ {var_name}: неверный формат. Ожидается: {config['description']}"
                )
    
    def _validate_urls(self) -> None:
        """Валидирует URL переменные."""
        url_vars = ["DATABASE_URL", "REDIS_URL", "KIE_API_URL"]
        
        for var_name in url_vars:
            url = os.getenv(var_name, "").strip()
            if url:
                try:
                    parsed = urlparse(url)
                    if not parsed.scheme or not parsed.netloc:
                        self.errors.append(f"❌ {var_name}: невалидный URL")
                except Exception as e:
                    self.errors.append(f"❌ {var_name}: ошибка парсинга URL: {e}")
    
    def _validate_tokens(self) -> None:
        """Проверяет токены на безопасность."""
        token_vars = ["TELEGRAM_BOT_TOKEN", "KIE_API_KEY"]
        
        for var_name in token_vars:
            token = os.getenv(var_name, "").strip()
            if token:
                # Проверка на очевидно небезопасные значения
                dangerous_patterns = [
                    "test", "demo", "example", "sample", "xxx",
                    "123", "000", "111", "fake", "mock"
                ]
                
                if any(pattern in token.lower() for pattern in dangerous_patterns):
                    self.warnings.append(
                        f"⚠️ {var_name}: похоже на тестовый/небезопасный токен"
                    )
                
                # Проверка длины токена
                if len(token) < 10:
                    self.warnings.append(
                        f"⚠️ {var_name}: слишком короткий токен"
                    )
    
    def _validate_numeric_vars(self) -> None:
        """Проверяет числовые переменные."""
        numeric_vars = {
            "BOOT_WARMUP_BUDGET_SECONDS": (1, 300),
            "REDIS_CONNECT_TIMEOUT_SECONDS": (0.5, 10),
            "WEBHOOK_SETTER_TIMEOUT_SECONDS": (1, 30)
        }
        
        for var_name, (min_val, max_val) in numeric_vars.items():
            value_str = os.getenv(var_name, "").strip()
            
            if value_str:
                try:
                    value = float(value_str)
                    if not (min_val <= value <= max_val):
                        self.warnings.append(
                            f"⚠️ {var_name}: значение {value} вне диапазона [{min_val}, {max_val}]"
                        )
                except ValueError:
                    self.warnings.append(
                        f"⚠️ {var_name}: должно быть числом, получено '{value_str}'"
                    )
    
    def get_safe_config_summary(self) -> dict:
        """Возвращает безопасную сводку конфигурации (без секретов)."""
        return {
            "required_vars_set": len([
                var for var in self.REQUIRED_VARS 
                if os.getenv(var, "").strip()
            ]),
            "total_required": len(self.REQUIRED_VARS),
            "optional_vars_set": len([
                var for var in self.OPTIONAL_VARS 
                if os.getenv(var, "").strip()
            ]),
            "database_url_set": bool(os.getenv("DATABASE_URL", "").strip()),
            "redis_url_set": bool(os.getenv("REDIS_URL", "").strip()),
            "kie_api_configured": bool(
                os.getenv("KIE_API_KEY", "").strip() and 
                os.getenv("KIE_API_URL", "").strip()
            )
        }


def validate_config_on_startup() -> None:
    """Валидирует конфигурацию при старте приложения."""
    validator = ConfigValidator()
    is_valid, errors, warnings = validator.validate_all()
    
    if not is_valid:
        error_msg = "❌ ОШИБКИ КОНФИГУРАЦИИ:\n" + "\n".join(errors)
        logger.error(error_msg)
        raise ConfigValidationError(error_msg)
    
    if warnings:
        warning_msg = "⚠️ ПРЕДУПРЕЖДЕНИЯ КОНФИГУРАЦИИ:\n" + "\n".join(warnings)
        logger.warning(warning_msg)
    
    summary = validator.get_safe_config_summary()
    logger.info(f"✅ Конфигурация валидна: {summary}")
    
    return summary


if __name__ == "__main__":
    # Тестирование валидатора
    validate_config_on_startup()
