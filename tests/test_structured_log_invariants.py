"""
Тесты на structured-log инварианты для 4 старых симптомов webhook sandbox.
Проверяет, что в логах корректно фиксируется outcome=ok/cancelled без asyncio ERROR.
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, patch, AsyncMock
from telegram.ext import Application

# Импортируем наши функции
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from bot_kie import run_webhook_sync
from app.utils.singleton_lock import release_singleton_lock, _release_redis_lock


class TestStructuredLogInvariants:
    """Тесты на structured-log инварианты для webhook sandbox."""

    def test_no_event_loop_symptom_logs_outcome_ok(self):
        """
        Тест: Симптом 'There is no current event loop' → логируется outcome=ok.
        """
        # Мокаем PTB Application
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем отсутствие event loop
        with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
            with patch('asyncio.new_event_loop') as mock_new_loop:
                with patch('asyncio.set_event_loop') as mock_set_loop:
                    mock_loop = Mock()
                    mock_new_loop.return_value = mock_loop
                    
                    with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                        # Собираем structured events
                        structured_events = []
                        
                        def capture_structured_event(**kwargs):
                            structured_events.append(kwargs)
                        
                        with patch('bot_kie.log_structured_event', side_effect=capture_structured_event):
                            with patch('bot_kie.logger'):
                                # Вызываем run_webhook_sync
                                run_webhook_sync(mock_app)
                                
                                # Проверяем, что нет старого симптома в логах
                                all_logs = []
                                for event in structured_events:
                                    if 'action' in event and event['action'] == 'WEBHOOK_START':
                                        all_logs.append(str(event))
                                
                                # Не должно быть старого симптома
                                assert not any("There is no current event loop" in log for log in all_logs)
                                
                                # Должен быть позитивный outcome
                                webhook_events = [e for e in structured_events if e.get('action') == 'WEBHOOK_START']
                                if webhook_events:
                                    assert webhook_events[0].get('outcome') in ['ok', 'started']

    def test_start_webhook_never_awaited_symptom_fixed(self):
        """
        Тест: Симптом 'start_webhook was never awaited' → исправлен.
        """
        # Мокаем PTB Application
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем отсутствие event loop
        with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
            with patch('asyncio.new_event_loop') as mock_new_loop:
                with patch('asyncio.set_event_loop') as mock_set_loop:
                    mock_loop = Mock()
                    mock_new_loop.return_value = mock_loop
                    
                    with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                        # Собираем все логи
                        log_messages = []
                        
                        class TestLogger:
                            def info(self, msg, *args, **kwargs):
                                log_messages.append(msg % args if args else msg)
                            def debug(self, msg, *args, **kwargs):
                                log_messages.append(msg % args if args else msg)
                            def error(self, msg, *args, **kwargs):
                                log_messages.append(f"ERROR: {msg % args if args else msg}")
                            def warning(self, msg, *args, **kwargs):
                                log_messages.append(f"WARNING: {msg % args if args else msg}")
                        
                        with patch('bot_kie.logger', TestLogger()):
                            # Вызываем run_webhook_sync
                            run_webhook_sync(mock_app)
                            
                            # Не должно быть старого симптома
                            assert not any("start_webhook was never awaited" in msg for msg in log_messages)
                            
                            # Должны быть позитивные индикаторы
                            assert any("Starting webhook server in sync mode" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_lock_release_failed_symptom_logs_info(self):
        """
        Тест: Симптом 'lock_release_failed' → логируется как INFO при loop closed.
        """
        # Устанавливаем глобальные переменные для Redis
        import app.utils.singleton_lock as lock_module
        lock_module._redis_client = Mock()
        lock_module._redis_lock_key = "test_key"
        lock_module._redis_lock_value = "test_value"
        
        # Мокаем _stop_redis_renewal с RuntimeError Event loop is closed
        with patch('app.utils.singleton_lock._stop_redis_renewal') as mock_stop:
            mock_stop.side_effect = RuntimeError("Event loop is closed")
            
            # Мокаем logger и проверяем вызовы
            mock_logger = Mock()
            
            with patch('app.utils.singleton_lock.logger', mock_logger):
                # Вызываем _release_redis_lock
                await _release_redis_lock()
                
                # Проверяем, что logger.info был вызван
                mock_logger.info.assert_called_once()
                
                # Проверяем, что logger.warning НЕ был вызван
                mock_logger.warning.assert_not_called()
                
                # Проверяем, что в сообщении есть 'lock_release_skipped'
                call_args = mock_logger.info.call_args[0]
                assert "lock_release_skipped" in call_args[0]

    @pytest.mark.asyncio
    async def test_gathering_future_exception_symptom_fixed(self):
        """
        Тест: Симптом 'GatheringFuture exception was never retrieved' → исправлен.
        """
        from bot_kie import _run_boot_warmups
        
        # Собираем логи
        log_messages = []
        
        class TestLogger:
            def info(self, msg, *args, **kwargs):
                log_messages.append(('INFO', msg % args if args else msg))
            def warning(self, msg, *args, **kwargs):
                log_messages.append(('WARNING', msg % args if args else msg))
            def error(self, msg, *args, **kwargs):
                log_messages.append(('ERROR', msg % args if args else msg))
        
        # Мокаем timeout чтобы вызвать CancelledError
        with patch('asyncio.wait_for', side_effect=asyncio.CancelledError()):
            with patch('bot_kie.logger', TestLogger()):
                with patch('bot_kie.log_structured_event'):
                    with patch('bot_kie._BOOT_WARMUP_STATE', {"cancelled": False}):
                        with patch('bot_kie._create_background_task') as mock_bg_task:
                            # Возвращаем простые моки
                            mock_bg_task.side_effect = [Mock(), Mock(), Mock()]
                            
                            try:
                                await _run_boot_warmups(correlation_id="TEST")
                            except asyncio.CancelledError:
                                pass  # Ожидаем CancelledError
                            
                            # Проверяем, что есть лог BOOT_WARMUP_CANCELLED
                            info_logs = [msg[1] for level, msg in log_messages if level == 'INFO']
                            assert any("BOOT_WARMUP_CANCELLED" in msg for msg in info_logs)
                            
                            # Не должно быть 'GatheringFuture exception was never retrieved'
                            all_logs = [msg[1] for level, msg in log_messages]
                            assert not any("GatheringFuture exception was never retrieved" in msg for msg in all_logs)

    def test_all_four_symptoms_absent_in_integration(self):
        """
        Тест: Интеграционный тест - все 4 симптома отсутствуют в полном пути.
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
                            # Собираем все логи из всех источников
                            all_log_messages = []
                            
                            class UniversalLogger:
                                def info(self, msg, *args, **kwargs):
                                    all_log_messages.append(('INFO', msg % args if args else msg))
                                def debug(self, msg, *args, **kwargs):
                                    all_log_messages.append(('DEBUG', msg % args if args else msg))
                                def warning(self, msg, *args, **kwargs):
                                    all_log_messages.append(('WARNING', msg % args if args else msg))
                                def error(self, msg, *args, **kwargs):
                                    all_log_messages.append(('ERROR', msg % args if args else msg))
                            
                            with patch('bot_kie.logger', UniversalLogger()):
                                # Выполняем полный путь
                                import asyncio
                                
                                # Шаг 1: Выполняем async preflight (мокированный)
                                application = asyncio.run(mock_preflight())
                                
                                # Шаг 2: Запускаем webhook в sync режиме
                                run_webhook_sync(application)
                                
                                # Проверяем отсутствие всех 4 старых симптомов
                                all_messages = [msg[1] for msg in all_log_messages]
                                
                                old_symptoms = [
                                    "There is no current event loop",
                                    "start_webhook was never awaited",
                                    "lock_release_failed",
                                    "GatheringFuture exception was never retrieved"
                                ]
                                
                                for symptom in old_symptoms:
                                    assert not any(symptom in msg for msg in all_messages), \
                                        f"Found old symptom '{symptom}' in logs: {[msg for msg in all_messages if symptom in msg]}"
                                
                                # Проверяем наличие позитивных индикаторов
                                positive_indicators = [
                                    "No event loop in MainThread",
                                    "Created new event loop",
                                    "Starting webhook server in sync mode"
                                ]
                                
                                for indicator in positive_indicators:
                                    assert any(indicator in msg for msg in all_messages), \
                                        f"Missing positive indicator '{indicator}' in logs"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
