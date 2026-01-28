"""
Регрессионный тест для webhook event loop конфликта.
Проверяет, что webhook путь не создаёт внешний loop и стартует без RuntimeError.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from telegram.ext import Application

# Импортируем наши функции
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from bot_kie import run_webhook_sync
from entrypoints.run_bot import run_bot_preflight


class TestWebhookEventLoopRegression:
    """Регрессионные тесты для event loop конфликта в webhook режиме."""
    
    @pytest.mark.asyncio
    async def test_webhook_sync_no_await_in_run_webhook(self):
        """
        Тест: run_webhook_sync не использует await и не создаёт внешний loop.
        """
        # Мокаем application
        mock_app = Mock(spec=Application)
        mock_app.add_post_shutdown_hook = Mock()
        mock_app.run_webhook = Mock()
        
        # Мокаем _resolve_webhook_url_from_env
        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
            with patch('bot_kie.logger'):
                # Вызываем sync функцию
                run_webhook_sync(mock_app)
                
                # Проверяем, что run_webhook был вызван
                mock_app.run_webhook.assert_called_once()
                
                # Проверяем параметры вызова
                call_args = mock_app.run_webhook.call_args
                assert call_args.kwargs['listen'] == '0.0.0.0'
                assert call_args.kwargs['url_path'] == 'webhook'
                assert call_args.kwargs['webhook_url'] == 'https://test.com/webhook'
    
    @pytest.mark.asyncio
    async def test_webhook_preflight_returns_application(self):
        """
        Тест: run_bot_preflight возвращает application объект.
        """
        # Мокаем все зависимости
        with patch('entrypoints.run_bot.configure_logging'):
            with patch('entrypoints.run_bot.resolve_port', return_value=10000):
                with patch('entrypoints.run_bot.start_healthcheck', return_value=False):
                    with patch('app.storage.get_storage') as mock_storage:
                        with patch('entrypoints.run_bot._wait_for_storage', return_value=True):
                            with patch('app.diagnostics.boot.run_boot_diagnostics', return_value={'result': 'OK', 'meta': {'bot_mode': 'webhook', 'port': 10000}}):
                                with patch('app.diagnostics.billing_preflight.run_billing_preflight', return_value={'result': 'OK'}):
                                    with patch('bot_kie.main') as mock_main:
                                        with patch('importlib.util.spec_from_file_location') as mock_spec:
                                            with patch('importlib.util.module_from_spec') as mock_module:
                                                # Настраиваем моки
                                                mock_storage.return_value = Mock()
                                                
                                                # Мокаем модуль бота
                                                mock_bot_module = Mock()
                                                mock_bot_module.main = AsyncMock()
                                                mock_bot_module.application = Mock()
                                                mock_module.return_value = mock_bot_module
                                                
                                                mock_spec_instance = Mock()
                                                mock_spec_instance.loader = Mock()
                                                mock_spec.return_value = mock_spec_instance
                                                
                                                # Вызываем preflight
                                                result = await run_bot_preflight()
                                                
                                                # Проверяем, что вернулся application
                                                assert result is mock_bot_module.application
                                                mock_bot_module.main.assert_called_once()
    
    def test_webhook_sync_adds_post_shutdown_hook(self):
        """
        Тест: run_webhook_sync добавляет post_shutdown хук для очистки singleton_lock.
        """
        mock_app = Mock(spec=Application)
        mock_app.add_post_shutdown_hook = Mock()
        mock_app.run_webhook = Mock()
        
        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
            with patch('bot_kie.logger'):
                run_webhook_sync(mock_app)
                
                # Проверяем, что хук был добавлен
                mock_app.add_post_shutdown_hook.assert_called_once()
                
                # Проверяем, что хук является coroutine функцией
                hook_func = mock_app.add_post_shutdown_hook.call_args[0][0]
                assert asyncio.iscoroutinefunction(hook_func)
    
    def test_webhook_sync_raises_error_without_webhook_url(self):
        """
        Тест: run_webhook_sync raises RuntimeError если WEBHOOK_URL не задан.
        """
        mock_app = Mock(spec=Application)
        
        with patch('bot_kie._resolve_webhook_url_from_env', return_value=None):
            with patch('bot_kie.logger'):
                with pytest.raises(RuntimeError, match="WEBHOOK_URL not set"):
                    run_webhook_sync(mock_app)
    
    @pytest.mark.asyncio
    async def test_post_shutdown_hook_releases_singleton_lock(self):
        """
        Тест: post_shutdown хук корректно освобождает singleton_lock.
        """
        mock_app = Mock(spec=Application)
        mock_app.add_post_shutdown_hook = Mock()
        mock_app.run_webhook = Mock()
        
        # Мокаем release_singleton_lock
        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
            with patch('bot_kie.logger'):
                run_webhook_sync(mock_app)
                
                # Получаем хук функцию
                hook_func = mock_app.add_post_shutdown_hook.call_args[0][0]
                
                # Мокаем release_singleton_lock через правильный импорт
                with patch('app.utils.singleton_lock.release_singleton_lock') as mock_release:
                    await hook_func()
                    mock_release.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
