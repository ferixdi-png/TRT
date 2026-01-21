#!/usr/bin/env python3
"""
Комплексный smoke тест критических флоу бота.
Проверяет end-to-end сценарии без реальных API вызовов.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ContextTypes
import asyncio


class TestCriticalFlows:
    """Тесты критических флоу."""
    
    @pytest.mark.asyncio
    async def test_start_command_flow(self):
        """Тест команды /start - должна показать главное меню."""
        from bot_kie import start
        
        # Mock update
        update = Mock(spec=Update)
        update.effective_user = Mock(spec=User)
        update.effective_user.id = 123456
        update.effective_user.username = "testuser"
        update.effective_user.first_name = "Test"
        update.effective_user.language_code = "ru"
        update.effective_user.is_bot = False
        
        update.message = Mock(spec=Message)
        update.message.chat = Mock(spec=Chat)
        update.message.chat.id = 123456
        update.message.chat.type = "private"
        update.message.reply_text = AsyncMock()
        
        # Mock context
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        context.bot = Mock()
        context.bot.send_message = AsyncMock()
        
        # Выполнить команду
        try:
            await start(update, context)
            
            # Проверить что было отправлено сообщение
            assert update.message.reply_text.called or context.bot.send_message.called, \
                "/start должен отправить ответ"
        except Exception as e:
            pytest.fail(f"start command crashed: {e}")
    
    @pytest.mark.asyncio
    async def test_gen_type_callback_no_delay(self):
        """Тест что gen_type callback быстрый (< 1 сек)."""
        from bot_kie import button_callback
        import time
        
        # Mock update with gen_type:text-to-image callback
        update = Mock(spec=Update)
        update.update_id = 999
        update.effective_user = Mock(spec=User)
        update.effective_user.id = 123456
        
        query = Mock(spec=CallbackQuery)
        query.id = "test_query_id"
        query.data = "gen_type:text-to-image"
        query.from_user = update.effective_user
        query.message = Mock(spec=Message)
        query.message.chat = Mock(spec=Chat)
        query.message.chat_id = 123456
        query.message.message_id = 1
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        
        update.callback_query = query
        
        # Mock context
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        context.bot = Mock()
        context.bot.answer_callback_query = AsyncMock()
        
        # Выполнить callback
        start = time.time()
        try:
            await button_callback(update, context)
            duration = time.time() - start
            
            # Проверить что ответ быстрый
            assert duration < 1.0, f"gen_type callback too slow: {duration:.2f}s (должно быть < 1s)"
            
            # Проверить что callback answered
            assert query.answer.called or context.bot.answer_callback_query.called, \
                "Callback query должен быть answered"
        except Exception as e:
            pytest.fail(f"gen_type callback crashed: {e}")
    
    @pytest.mark.asyncio
    async def test_unknown_callback_handled(self):
        """Тест что неизвестные callback'и не вызывают зависание кнопок."""
        from bot_kie import button_callback
        
        # Mock update with unknown callback
        update = Mock(spec=Update)
        update.update_id = 999
        update.effective_user = Mock(spec=User)
        update.effective_user.id = 123456
        
        query = Mock(spec=CallbackQuery)
        query.id = "test_query_id"
        query.data = "totally_unknown_callback_xyz"
        query.from_user = update.effective_user
        query.message = Mock(spec=Message)
        query.message.chat = Mock(spec=Chat)
        query.message.chat_id = 123456
        query.message.message_id = 1
        query.answer = AsyncMock()
        
        update.callback_query = query
        
        # Mock context
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        context.bot = Mock()
        context.bot.answer_callback_query = AsyncMock()
        
        # Выполнить callback
        try:
            await button_callback(update, context)
            
            # Проверить что callback answered (критично!)
            assert query.answer.called or context.bot.answer_callback_query.called, \
                "Unknown callback MUST be answered to prevent button hang"
        except Exception as e:
            # Даже при ошибке callback должен быть answered
            assert query.answer.called or context.bot.answer_callback_query.called, \
                f"Unknown callback MUST be answered even on error: {e}"
    
    def test_catalog_loads_models(self):
        """Тест что каталог моделей загружается."""
        from app.kie_catalog import load_catalog
        
        models = load_catalog()
        assert len(models) > 0, "Catalog should have models"
        assert len(models) >= 70, f"Expected >= 70 models, got {len(models)}"
        
        # Проверить первую модель
        first_model = models[0]
        assert hasattr(first_model, 'id'), "Model should have id"
        assert hasattr(first_model, 'type'), "Model should have type"
    
    def test_catalog_cache_hit(self):
        """Тест что кэш каталога работает."""
        from app.kie_catalog import load_catalog
        import time
        
        # Первая загрузка
        start = time.time()
        models1 = load_catalog()
        first_duration = time.time() - start
        
        # Вторая загрузка (должна быть из кэша)
        start = time.time()
        models2 = load_catalog()
        second_duration = time.time() - start
        
        # Кэш должен ускорить загрузку
        assert second_duration < first_duration or second_duration < 0.01, \
            f"Cache hit should be faster: {second_duration:.3f}s vs {first_duration:.3f}s"
        
        # Должны быть одинаковые данные
        assert len(models1) == len(models2), "Cache should return same data"
    
    def test_visible_models_cache(self):
        """Тест что кэш видимых моделей работает."""
        # Это критично для P1 fix
        import bot_kie
        import time
        
        # Первый вызов
        start = time.time()
        visible_ids = bot_kie._get_visible_model_ids()
        first_duration = time.time() - start
        
        # Второй вызов (должен быть из кэша)
        start = time.time()
        visible_ids2 = bot_kie._get_visible_model_ids()
        second_duration = time.time() - start
        
        # Кэш должен работать
        assert second_duration < 0.1, \
            f"Visible models cache should be fast: {second_duration:.3f}s (was {first_duration:.3f}s on first call)"
        
        # Должны быть одинаковые данные
        assert visible_ids == visible_ids2, "Cache should return same data"
        assert len(visible_ids) > 0, "Should have visible models"


class TestBalanceOperations:
    """Тесты операций с балансом."""
    
    def test_balance_format(self):
        """Тест форматирования баланса."""
        from app.helpers.balance_helpers import format_rub_amount
        
        assert format_rub_amount(100) == "100 ₽"
        assert format_rub_amount(1.5) == "1.5 ₽"
        assert format_rub_amount(0) == "0 ₽"
    
    def test_balance_persistence(self):
        """Тест что баланс сохраняется."""
        from app.storage.balance_storage import get_balance_store
        
        store = get_balance_store()
        test_user_id = 999999
        
        # Установить баланс
        store.set_balance(test_user_id, 100.0)
        
        # Получить баланс
        balance = store.get_balance(test_user_id)
        assert balance == 100.0, f"Balance should persist: got {balance}"


class TestFreeLimits:
    """Тесты бесплатных лимитов."""
    
    def test_free_counter_decrement(self):
        """Тест что счетчик бесплатных генераций декрементируется."""
        from app.helpers.free_limit_helpers import get_free_counter, consume_free_generation
        
        test_user_id = 888888
        
        # Получить текущий счетчик
        initial = get_free_counter(test_user_id)
        
        # Попробовать consume
        success = consume_free_generation(test_user_id)
        
        if initial > 0:
            # Должен уменьшиться
            after = get_free_counter(test_user_id)
            assert after == initial - 1, f"Counter should decrement: {initial} -> {after}"
        else:
            # Не должно быть успешным
            assert not success, "Cannot consume when counter is 0"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
