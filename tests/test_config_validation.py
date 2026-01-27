"""
Тесты валидации конфигурации.
Проверяют корректность валидации ENV переменных.
"""

import os
import pytest
from unittest.mock import patch

from app.config.validation import (
    ConfigValidator,
    ConfigValidationError,
    validate_config_on_startup
)


class TestConfigValidator:
    """Тесты валидатора конфигурации."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.validator = ConfigValidator()
    
    def test_required_vars_missing(self):
        """Тест отсутствия обязательных переменных."""
        # Удаляем обязательные переменные
        with patch.dict(os.environ, {}, clear=True):
            is_valid, errors, warnings = self.validator.validate_all()
            
            assert not is_valid
            assert len(errors) >= 3  # TELEGRAM_BOT_TOKEN, DATABASE_URL, REDIS_URL
            assert any("TELEGRAM_BOT_TOKEN" in error for error in errors)
            assert any("DATABASE_URL" in error for error in errors)
            assert any("REDIS_URL" in error for error in errors)
    
    def test_required_vars_invalid_format(self):
        """Тест неверного формата обязательных переменных."""
        invalid_env = {
            "TELEGRAM_BOT_TOKEN": "invalid_token",
            "DATABASE_URL": "invalid_url",
            "REDIS_URL": "invalid_url"
        }
        
        with patch.dict(os.environ, invalid_env, clear=True):
            is_valid, errors, warnings = self.validator.validate_all()
            
            assert not is_valid
            assert len(errors) >= 3
            assert any("неверный формат" in error for error in errors)
    
    def test_required_vars_valid(self):
        """Тест корректных обязательных переменных."""
        valid_env = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234567890",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379"
        }
        
        with patch.dict(os.environ, valid_env, clear=True):
            is_valid, errors, warnings = self.validator.validate_all()
            
            assert is_valid
            assert len(errors) == 0
    
    def test_optional_vars_warnings(self):
        """Тест предупреждений для опциональных переменных."""
        env_with_invalid_optional = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234567890",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "KIE_API_KEY": "invalid key with spaces",
            "KIE_API_URL": "ftp://invalid.protocol"
        }
        
        with patch.dict(os.environ, env_with_invalid_optional, clear=True):
            is_valid, errors, warnings = self.validator.validate_all()
            
            assert is_valid  # Опциональные не блокируют валидацию
            assert len(warnings) >= 2
            assert any("KIE_API_KEY" in warning for warning in warnings)
            assert any("KIE_API_URL" in warning for warning in warnings)
    
    def test_token_security_warnings(self):
        """Тест предупреждений о небезопасных токенах."""
        env_with_dangerous_tokens = {
            "TELEGRAM_BOT_TOKEN": "123456:test_token",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "KIE_API_KEY": "demo_key"
        }
        
        with patch.dict(os.environ, env_with_dangerous_tokens, clear=True):
            is_valid, errors, warnings = self.validator.validate_all()
            
            assert is_valid
            assert len(warnings) >= 2
            assert any("тестовый" in warning.lower() for warning in warnings)
    
    def test_numeric_vars_validation(self):
        """Тест валидации числовых переменных."""
        env_with_invalid_numbers = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234567890",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "BOOT_WARMUP_BUDGET_SECONDS": "500",  # Слишком большое значение
            "REDIS_CONNECT_TIMEOUT_SECONDS": "0.1",  # Слишком маленькое значение
            "WEBHOOK_SETTER_TIMEOUT_SECONDS": "invalid"  # Не число
        }
        
        with patch.dict(os.environ, env_with_invalid_numbers, clear=True):
            is_valid, errors, warnings = self.validator.validate_all()
            
            assert is_valid
            assert len(warnings) >= 3
    
    def test_get_safe_config_summary(self):
        """Тест безопасной сводки конфигурации."""
        env = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234567890",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "KIE_API_KEY": "valid_key",
            "KIE_API_URL": "https://api.kie.ai"
        }
        
        with patch.dict(os.environ, env, clear=True):
            summary = self.validator.get_safe_config_summary()
            
            assert summary["required_vars_set"] == 3
            assert summary["total_required"] == 3
            assert summary["optional_vars_set"] == 2
            assert summary["database_url_set"] is True
            assert summary["redis_url_set"] is True
            assert summary["kie_api_configured"] is True
            
            # Проверяем отсутствие токенов в сводке
            assert "123456" not in str(summary)
            assert "valid_key" not in str(summary)


class TestValidateConfigOnStartup:
    """Тесты валидации при старте."""
    
    def test_successful_validation(self):
        """Тест успешной валидации."""
        valid_env = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234567890",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379"
        }
        
        with patch.dict(os.environ, valid_env, clear=True):
            # Не должно вызывать исключение
            summary = validate_config_on_startup()
            assert summary is not None
    
    def test_validation_failure(self):
        """Тест провальной валидации."""
        invalid_env = {}
        
        with patch.dict(os.environ, invalid_env, clear=True):
            with pytest.raises(ConfigValidationError) as exc_info:
                validate_config_on_startup()
            
            assert "ОШИБКИ КОНФИГУРАЦИИ" in str(exc_info.value)
    
    def test_validation_with_warnings(self):
        """Тест валидации с предупреждениями."""
        env_with_warnings = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234567890",
            "DATABASE_URL": "postgres://user:pass@localhost/db",
            "REDIS_URL": "redis://localhost:6379",
            "KIE_API_KEY": "test_token"
        }
        
        with patch.dict(os.environ, env_with_warnings, clear=True):
            # Предупреждения не должны блокировать запуск
            summary = validate_config_on_startup()
            assert summary is not None


if __name__ == "__main__":
    pytest.main([__file__])
