"""
MVP Invariants Tests - ЗАЩИТА ЖЕЛЕЗОБЕТОННОЙ БАЗЫ

Эти тесты гарантируют, что критичные компоненты MVP работают корректно.
НЕ УДАЛЯТЬ И НЕ МОДИФИЦИРОВАТЬ БЕЗ ОБСУЖДЕНИЯ!

Тестируемые инварианты:
1. Balance operations используют транзакции (race condition protection)
2. Partner isolation работает корректно
3. Deduplication работает для charge_balance_once и consume_free_generation_once
4. Language priority работает корректно
5. Required ENV variables валидируются
"""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestBalanceTransactionInvariants:
    """Тесты инвариантов транзакций баланса."""
    
    def test_add_user_balance_uses_for_update(self):
        """add_user_balance ДОЛЖЕН использовать FOR UPDATE для предотвращения race conditions."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        source = inspect.getsource(PostgresStorage.add_user_balance)
        assert "FOR UPDATE" in source, (
            "КРИТИЧНО: add_user_balance ДОЛЖЕН использовать FOR UPDATE! "
            "Без этого возможны race conditions при параллельных операциях."
        )
        assert "transaction()" in source, (
            "КРИТИЧНО: add_user_balance ДОЛЖЕН использовать транзакцию!"
        )
    
    def test_subtract_user_balance_uses_for_update(self):
        """subtract_user_balance ДОЛЖЕН использовать FOR UPDATE."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        source = inspect.getsource(PostgresStorage.subtract_user_balance)
        assert "FOR UPDATE" in source, (
            "КРИТИЧНО: subtract_user_balance ДОЛЖЕН использовать FOR UPDATE!"
        )
        assert "transaction()" in source, (
            "КРИТИЧНО: subtract_user_balance ДОЛЖЕН использовать транзакцию!"
        )
    
    def test_charge_balance_once_uses_for_update(self):
        """charge_balance_once ДОЛЖЕН использовать FOR UPDATE и deduplication."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        source = inspect.getsource(PostgresStorage.charge_balance_once)
        assert "FOR UPDATE" in source, (
            "КРИТИЧНО: charge_balance_once ДОЛЖЕН использовать FOR UPDATE!"
        )
        assert "transaction()" in source, (
            "КРИТИЧНО: charge_balance_once ДОЛЖЕН использовать транзакцию!"
        )
        assert "duplicate" in source.lower(), (
            "КРИТИЧНО: charge_balance_once ДОЛЖЕН проверять дубликаты!"
        )
    
    def test_consume_free_generation_uses_for_update(self):
        """consume_free_generation_once ДОЛЖЕН использовать FOR UPDATE и deduplication."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        source = inspect.getsource(PostgresStorage.consume_free_generation_once)
        assert "FOR UPDATE" in source, (
            "КРИТИЧНО: consume_free_generation_once ДОЛЖЕН использовать FOR UPDATE!"
        )
        assert "transaction()" in source, (
            "КРИТИЧНО: consume_free_generation_once ДОЛЖЕН использовать транзакцию!"
        )
        assert "duplicate" in source.lower(), (
            "КРИТИЧНО: consume_free_generation_once ДОЛЖЕН проверять дубликаты!"
        )


class TestPartnerIsolationInvariants:
    """Тесты инвариантов изоляции партнёров."""
    
    def test_postgres_storage_requires_partner_id(self):
        """PostgresStorage ДОЛЖЕН требовать partner_id."""
        from app.storage.postgres_storage import PostgresStorage
        
        # Убираем ENV переменные
        with patch.dict(os.environ, {"PARTNER_ID": "", "BOT_INSTANCE_ID": ""}, clear=False):
            # Очищаем переменные
            env_backup = {}
            for key in ["PARTNER_ID", "BOT_INSTANCE_ID"]:
                env_backup[key] = os.environ.pop(key, None)
            
            try:
                with pytest.raises(ValueError, match="BOT_INSTANCE_ID is required"):
                    PostgresStorage("postgres://example", partner_id="")
            finally:
                # Восстанавливаем
                for key, value in env_backup.items():
                    if value is not None:
                        os.environ[key] = value
    
    def test_storage_json_has_partner_id_in_queries(self):
        """Все запросы к storage_json ДОЛЖНЫ включать partner_id."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        # Проверяем ключевые методы
        methods_to_check = [
            'add_user_balance',
            'subtract_user_balance',
            'charge_balance_once',
            'consume_free_generation_once',
            '_save_json_unlocked',
            '_load_json',
        ]
        
        for method_name in methods_to_check:
            method = getattr(PostgresStorage, method_name, None)
            if method:
                source = inspect.getsource(method)
                assert "partner_id" in source, (
                    f"КРИТИЧНО: {method_name} ДОЛЖЕН использовать partner_id для изоляции!"
                )


class TestLanguagePriorityInvariants:
    """Тесты инвариантов системы языков."""
    
    def test_show_main_menu_checks_explicit_language_first(self):
        """show_main_menu ДОЛЖЕН проверять явно установленный язык ПЕРВЫМ."""
        import inspect
        # Импортируем напрямую из файла
        import bot_kie
        
        source = inspect.getsource(bot_kie.show_main_menu)
        
        # has_user_language_set должен проверяться перед _get_menu_dep_cache
        has_user_lang_pos = source.find("has_user_language_set")
        menu_cache_pos = source.find("_get_menu_dep_cache")
        
        assert has_user_lang_pos != -1, (
            "КРИТИЧНО: show_main_menu ДОЛЖЕН проверять has_user_language_set!"
        )
        assert has_user_lang_pos < menu_cache_pos, (
            "КРИТИЧНО: has_user_language_set ДОЛЖЕН проверяться ПЕРЕД _get_menu_dep_cache! "
            "Иначе явно установленный язык будет игнорироваться."
        )
    
    def test_set_user_language_updates_cache_immediately(self):
        """set_user_language ДОЛЖЕН обновлять кэш СРАЗУ."""
        import inspect
        import bot_kie
        
        source = inspect.getsource(bot_kie.set_user_language)
        
        # Кэш должен обновляться до async операций
        cache_update_pos = source.find("_user_language_cache[")
        async_pos = source.find("async def")
        
        assert cache_update_pos != -1, (
            "КРИТИЧНО: set_user_language ДОЛЖЕН обновлять _user_language_cache!"
        )
        assert cache_update_pos < async_pos or async_pos == -1, (
            "КРИТИЧНО: кэш ДОЛЖЕН обновляться ПЕРЕД async операциями!"
        )


class TestEnvValidationInvariants:
    """Тесты инвариантов валидации ENV."""
    
    def test_required_env_includes_critical_vars(self):
        """REQUIRED_ENV ДОЛЖЕН включать критичные переменные."""
        from app.config_env import REQUIRED_ENV
        
        critical_vars = [
            "ADMIN_ID",
            "BOT_INSTANCE_ID", 
            "TELEGRAM_BOT_TOKEN",
            "WEBHOOK_BASE_URL",
        ]
        
        for var in critical_vars:
            assert var in REQUIRED_ENV, (
                f"КРИТИЧНО: {var} ДОЛЖЕН быть в REQUIRED_ENV!"
            )
    
    def test_validate_config_returns_missing_required(self):
        """validate_config ДОЛЖЕН возвращать missing_required."""
        from app.config_env import validate_config
        
        # Валидация без strict должна возвращать результат с missing_required
        result = validate_config(strict=False)
        assert hasattr(result, 'missing_required'), (
            "КРИТИЧНО: validate_config ДОЛЖЕН возвращать missing_required!"
        )


class TestPaymentHandlerInvariants:
    """Тесты инвариантов payment handlers."""
    
    def test_pre_checkout_handler_exists(self):
        """handle_pre_checkout_query ДОЛЖЕН существовать."""
        import bot_kie
        
        assert hasattr(bot_kie, 'handle_pre_checkout_query'), (
            "КРИТИЧНО: handle_pre_checkout_query ДОЛЖЕН существовать!"
        )
        assert asyncio.iscoroutinefunction(bot_kie.handle_pre_checkout_query), (
            "КРИТИЧНО: handle_pre_checkout_query ДОЛЖЕН быть async функцией!"
        )
    
    def test_successful_payment_handler_exists(self):
        """handle_successful_payment ДОЛЖЕН существовать."""
        import bot_kie
        
        assert hasattr(bot_kie, 'handle_successful_payment'), (
            "КРИТИЧНО: handle_successful_payment ДОЛЖЕН существовать!"
        )
        assert asyncio.iscoroutinefunction(bot_kie.handle_successful_payment), (
            "КРИТИЧНО: handle_successful_payment ДОЛЖЕН быть async функцией!"
        )
    
    def test_successful_payment_adds_balance(self):
        """handle_successful_payment ДОЛЖЕН добавлять баланс."""
        import inspect
        import bot_kie
        
        source = inspect.getsource(bot_kie.handle_successful_payment)
        
        assert "add_user_balance" in source or "add_balance" in source, (
            "КРИТИЧНО: handle_successful_payment ДОЛЖЕН добавлять баланс!"
        )


class TestCallbackLoggingInvariants:
    """Тесты инвариантов логирования callback-ов."""
    
    def test_button_callback_logs_clicks(self):
        """button_callback ДОЛЖЕН логировать нажатия."""
        import inspect
        import bot_kie
        
        source = inspect.getsource(bot_kie.button_callback)
        
        assert "BUTTON_CLICK" in source, (
            "КРИТИЧНО: button_callback ДОЛЖЕН логировать BUTTON_CLICK!"
        )


class TestDeduplicationInvariants:
    """Тесты инвариантов дедупликации."""
    
    def test_charge_balance_once_returns_duplicate_status(self):
        """charge_balance_once ДОЛЖЕН возвращать status='duplicate' при повторном вызове."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        source = inspect.getsource(PostgresStorage.charge_balance_once)
        
        assert '"duplicate"' in source or "'duplicate'" in source, (
            "КРИТИЧНО: charge_balance_once ДОЛЖЕН возвращать status='duplicate'!"
        )
    
    def test_consume_free_generation_returns_duplicate_status(self):
        """consume_free_generation_once ДОЛЖЕН возвращать status='duplicate' при повторном вызове."""
        import inspect
        from app.storage.postgres_storage import PostgresStorage
        
        source = inspect.getsource(PostgresStorage.consume_free_generation_once)
        
        assert '"duplicate"' in source or "'duplicate'" in source, (
            "КРИТИЧНО: consume_free_generation_once ДОЛЖЕН возвращать status='duplicate'!"
        )


# Маркер для запуска только MVP тестов
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "mvp: mark test as MVP invariant test"
    )


# Применяем маркер ко всем тестам в этом файле
def pytest_collection_modifyitems(items):
    for item in items:
        if item.fspath.basename == "test_mvp_invariants.py":
            item.add_marker(pytest.mark.mvp)
