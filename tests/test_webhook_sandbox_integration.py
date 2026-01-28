"""
Интеграционные регресс-тесты для webhook sandbox: полный аудит event loop lifecycle.
Проверяет полный путь: asyncio.run(preflight) → run_webhook_sync() с PTB.
"""

import pytest
import asyncio
import warnings
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from telegram.ext import Application

# Импортируем наши функции
import sys
import importlib
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from entrypoints.run_bot import run_bot_preflight
from bot_kie import run_webhook_sync


@pytest.mark.xfail(reason="Deprecated: webhook mode now uses main_render.py instead of run_webhook_sync")
class TestWebhookSandboxIntegration:
    """Интеграционные тесты для webhook sandbox - DEPRECATED после P0 fix."""

    def test_preflight_then_webhook_sync_no_loop_scenario(self):
        """
        Тест: asyncio.run(preflight) → run_webhook_sync() когда loop отсутствует.
        Имитирует реальный сценарий в MainThread после asyncio.run().
        """
        # Мокаем PTB Application
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем run_bot_preflight чтобы вернуть application без реального выполнения
        with patch('entrypoints.run_bot.run_bot_preflight') as mock_preflight:
            mock_preflight.return_value = mock_app
            
            # Мокаем отсутствие event loop (сценарий после asyncio.run)
            with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
                with patch('asyncio.new_event_loop') as mock_new_loop:
                    with patch('asyncio.set_event_loop') as mock_set_loop:
                        mock_loop = Mock()
                        mock_new_loop.return_value = mock_loop
                        
                        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                            # Собираем логи
                            logger_info_calls = []
                            def capture_logger_info(msg, *args):
                                logger_info_calls.append(msg % args if args else msg)
                            
                            with patch('bot_kie.logger.info', side_effect=capture_logger_info):
                                # Выполняем реальный путь из entrypoints/run_bot.py
                                import asyncio
                                
                                # Шаг 1: Выполняем async preflight (мокированный)
                                application = asyncio.run(mock_preflight())
                                
                                # Шаг 2: Запускаем webhook в sync режиме
                                run_webhook_sync(application)
                                
                                # Проверяем, что был создан и установлен новый loop
                                mock_new_loop.assert_called_once()
                                mock_set_loop.assert_called_once_with(mock_loop)
                                
                                # Проверяем, что webhook был запущен
                                mock_app.run_webhook.assert_called_once()
                                
                                # Проверяем логи
                                assert any("No event loop in MainThread" in call for call in logger_info_calls)

    def test_preflight_then_webhook_sync_existing_loop_scenario(self):
        """
        Тест: asyncio.run(preflight) → run_webhook_sync() когда loop уже есть.
        Проверяет, что существующий loop используется повторно.
        """
        # Мокаем PTB Application
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем run_bot_preflight чтобы вернуть application
        with patch('entrypoints.run_bot.run_bot_preflight') as mock_preflight:
            mock_preflight.return_value = mock_app
            
            # Мокаем существующий event loop
            mock_loop = Mock()
            with patch('asyncio.get_event_loop', return_value=mock_loop):
                with patch('asyncio.new_event_loop') as mock_new_loop:
                    with patch('asyncio.set_event_loop') as mock_set_loop:
                        
                        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                            # Выполняем реальный путь
                            import asyncio
                            
                            # Шаг 1: Выполняем async preflight (мокированный)
                            application = asyncio.run(mock_preflight())
                            
                            # Шаг 2: Запускаем webhook в sync режиме
                            run_webhook_sync(application)
                            
                            # Проверяем, что существующий loop используется
                            mock_new_loop.assert_not_called()
                            mock_set_loop.assert_not_called()
                            
                            # Проверяем, что webhook был запущен
                            mock_app.run_webhook.assert_called_once()

    def test_preflight_then_webhook_sync_closed_loop_scenario(self):
        """
        Тест: asyncio.run(preflight) → run_webhook_sync() когда loop закрыт.
        Проверяет обработку закрытого loop.
        """
        # Мокаем PTB Application
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем run_bot_preflight чтобы вернуть application
        with patch('entrypoints.run_bot.run_bot_preflight') as mock_preflight:
            mock_preflight.return_value = mock_app
            
            # Мокаем закрытый event loop
            mock_closed_loop = Mock()
            mock_closed_loop.is_closed.return_value = True
            
            with patch('asyncio.get_event_loop', side_effect=RuntimeError("Event loop is closed")):
                with patch('asyncio.new_event_loop') as mock_new_loop:
                    with patch('asyncio.set_event_loop') as mock_set_loop:
                        mock_loop = Mock()
                        mock_new_loop.return_value = mock_loop
                        
                        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                            # Выполняем реальный путь
                            import asyncio
                            
                            # Шаг 1: Выполняем async preflight (мокированный)
                            application = asyncio.run(mock_preflight())
                            
                            # Шаг 2: Запускаем webhook в sync режиме
                            run_webhook_sync(application)
                            
                            # Проверяем, что был создан новый loop для закрытого
                            mock_new_loop.assert_called_once()
                            mock_set_loop.assert_called_once_with(mock_loop)
                            
                            # Проверяем, что webhook был запущен
                            mock_app.run_webhook.assert_called_once()

    def test_no_unawaited_coroutines_with_warnings_as_errors(self):
        """
        Тест: Проверяет отсутствие un-awaited coroutines через warnings-as-errors.
        """
        # Включаем warnings как ошибки для RuntimeWarning о coroutine
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("error", RuntimeWarning)
            
            # Мокаем PTB Application
            mock_app = Mock(spec=Application)
            mock_app.run_webhook = Mock()
            
            # Мокаем run_bot_preflight чтобы вернуть application
            with patch('entrypoints.run_bot.run_bot_preflight') as mock_preflight:
                mock_preflight.return_value = mock_app
                
                # Мокаем отсутствие event loop
                with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
                    with patch('asyncio.new_event_loop') as mock_new_loop:
                        with patch('asyncio.set_event_loop') as mock_set_loop:
                            mock_loop = Mock()
                            mock_new_loop.return_value = mock_loop
                            
                            with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                                # Выполняем полный путь
                                import asyncio
                                
                                # Шаг 1: Выполняем async preflight (мокированный)
                                application = asyncio.run(mock_preflight())
                                
                                # Шаг 2: Запускаем webhook в sync режиме
                                run_webhook_sync(application)
                                
                                # Проверяем, что не было RuntimeWarning о coroutine
                                runtime_warnings = [warning for warning in w 
                                                 if issubclass(warning.category, RuntimeWarning)]
                                assert len(runtime_warnings) == 0, f"Found RuntimeWarnings: {runtime_warnings}"

    def test_webhook_sync_with_mock_ptb_application(self):
        """
        Тест: run_webhook_sync с моками PTB Application.
        Проверяет корректность вызова PTB API.
        """
        # Создаем мок PTB Application с правильными атрибутами
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем окружение
        with patch.dict(os.environ, {
            'WEBHOOK_URL': 'https://test.com/webhook',
            'PORT': '10000',
            'WEBHOOK_SECRET_TOKEN': 'test_secret'
        }):
            with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
                with patch('asyncio.new_event_loop') as mock_new_loop:
                    with patch('asyncio.set_event_loop') as mock_set_loop:
                        mock_loop = Mock()
                        mock_new_loop.return_value = mock_loop
                        
                        with patch('bot_kie.logger'):
                            # Вызываем run_webhook_sync
                            run_webhook_sync(mock_app)
                            
                            # Проверяем вызов PTB API (allowed_updates будет списком UpdateType)
                            mock_app.run_webhook.assert_called_once()
                            call_args = mock_app.run_webhook.call_args
                            
                            # Проверяем основные параметры
                            assert call_args.kwargs['listen'] == '0.0.0.0'
                            assert call_args.kwargs['port'] == 10000
                            assert call_args.kwargs['url_path'] == 'webhook'
                            assert call_args.kwargs['webhook_url'] == 'https://test.com/webhook'
                            assert call_args.kwargs['drop_pending_updates'] is True
                            assert call_args.kwargs['secret_token'] == 'test_secret'
                            assert 'allowed_updates' in call_args.kwargs
                            
                            # Проверяем создание loop
                            mock_new_loop.assert_called_once()
                            mock_set_loop.assert_called_once_with(mock_loop)

    def test_structured_log_invariants_no_old_symptoms(self):
        """
        Тест: Проверяет structured-log инварианты - отсутствие старых симптомов.
        """
        # Мокаем PTB Application
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем run_bot_preflight чтобы вернуть application
        with patch('entrypoints.run_bot.run_bot_preflight') as mock_preflight:
            mock_preflight.return_value = mock_app
            
            # Мокаем отсутствие event loop
            with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
                with patch('asyncio.new_event_loop') as mock_new_loop:
                    with patch('asyncio.set_event_loop') as mock_set_loop:
                        mock_loop = Mock()
                        mock_new_loop.return_value = mock_loop
                        
                        with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                            # Собираем все логи
                            log_records = []
                            
                            class TestLogger:
                                def info(self, msg, *args, **kwargs):
                                    log_records.append(('INFO', msg % args if args else msg))
                                
                                def debug(self, msg, *args, **kwargs):
                                    log_records.append(('DEBUG', msg % args if args else msg))
                                
                                def warning(self, msg, *args, **kwargs):
                                    log_records.append(('WARNING', msg % args if args else msg))
                                
                                def error(self, msg, *args, **kwargs):
                                    log_records.append(('ERROR', msg % args if args else msg))
                            
                            with patch('bot_kie.logger', TestLogger()):
                                # Выполняем полный путь
                                import asyncio
                                
                                # Шаг 1: Выполняем async preflight (мокированный)
                                application = asyncio.run(mock_preflight())
                                
                                # Шаг 2: Запускаем webhook в sync режиме
                                run_webhook_sync(application)
                                
                                # Проверяем отсутствие старых симптомов в логах
                                log_messages = [record[1] for record in log_records]
                                
                                # Не должно быть этих старых ошибок
                                old_symptoms = [
                                    "There is no current event loop",
                                    "start_webhook was never awaited",
                                    "lock_release_failed",
                                    "GatheringFuture exception was never retrieved"
                                ]
                                
                                for symptom in old_symptoms:
                                    assert not any(symptom in msg for msg in log_messages), \
                                        f"Found old symptom '{symptom}' in logs: {log_messages}"
                                
                                # Должны быть позитивные индикаторы
                                positive_indicators = [
                                    "No event loop in MainThread",
                                    "Created new event loop",
                                    "Starting webhook server in sync mode"
                                ]
                                
                                for indicator in positive_indicators:
                                    assert any(indicator in msg for msg in log_messages), \
                                        f"Missing positive indicator '{indicator}' in logs: {log_messages}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
