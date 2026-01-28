"""
Тесты для исправлений webhook sandbox: event loop, warmup cancellation, shutdown safety.
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
from app.utils.singleton_lock import release_singleton_lock, _release_redis_lock


@pytest.mark.xfail(reason="Deprecated: webhook mode now uses main_render.py instead of run_webhook_sync")
class TestWebhookSandboxFixes:
    """Тесты для исправлений webhook sandbox - DEPRECATED после P0 fix."""

    def test_run_webhook_sync_creates_loop_if_missing(self):
        """
        Тест: run_webhook_sync создаёт event loop если отсутствует.
        """
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        
        # Мокаем отсутствие event loop
        with patch('asyncio.get_event_loop', side_effect=RuntimeError("No current event loop")):
            with patch('asyncio.new_event_loop') as mock_new_loop:
                with patch('asyncio.set_event_loop') as mock_set_loop:
                    mock_loop = Mock()
                    mock_new_loop.return_value = mock_loop
                    
                    with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                        with patch('bot_kie.logger'):
                            run_webhook_sync(mock_app)
                            
                            # Проверяем, что новый loop был создан и установлен
                            mock_new_loop.assert_called_once()
                            mock_set_loop.assert_called_once_with(mock_loop)
                            
                            # Проверяем, что webhook был запущен
                            mock_app.run_webhook.assert_called_once()

    def test_run_webhook_sync_uses_existing_loop(self):
        """
        Тест: run_webhook_sync использует существующий event loop.
        """
        mock_app = Mock(spec=Application)
        mock_app.run_webhook = Mock()
        mock_loop = Mock()
        
        # Мокаем существующий event loop
        with patch('asyncio.get_event_loop', return_value=mock_loop):
            with patch('asyncio.new_event_loop') as mock_new_loop:
                with patch('asyncio.set_event_loop') as mock_set_loop:
                    with patch('bot_kie._resolve_webhook_url_from_env', return_value='https://test.com/webhook'):
                        with patch('bot_kie.logger'):
                            run_webhook_sync(mock_app)
                            
                            # Проверяем, что существующий loop используется
                            mock_new_loop.assert_not_called()
                            mock_set_loop.assert_not_called()
                            
                            # Проверяем, что webhook был запущен
                            mock_app.run_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_singleton_lock_handles_loop_closed(self):
        """
        Тест: release_singleton_lock корректно обрабатывает закрытый loop.
        """
        # Устанавливаем глобальные переменные для Redis
        import app.utils.singleton_lock as lock_module
        lock_module._redis_client = Mock()
        lock_module._redis_lock_key = "test_key"
        lock_module._redis_lock_value = "test_value"
        
        # Мокаем _stop_redis_renewal с RuntimeError
        with patch('app.utils.singleton_lock._stop_redis_renewal') as mock_stop:
            mock_stop.side_effect = RuntimeError("Event loop is closed")
            
            # Импортируем логгер из модуля
            from app.utils.singleton_lock import logger
            with patch.object(logger, 'info') as mock_info:
                with patch.object(logger, 'warning') as mock_warning:
                    # Не должно падать с исключением
                    await _release_redis_lock()
                    
                    # Проверяем, что логируется INFO, а не ERROR
                    mock_info.assert_called_once()
                    assert "lock_release_skipped" in mock_info.call_args[0][0]
                    mock_warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_singleton_lock_handles_other_runtime_error(self):
        """
        Тест: release_singleton_lock логирует WARNING для других RuntimeError.
        """
        # Устанавливаем глобальные переменные для Redis
        import app.utils.singleton_lock as lock_module
        lock_module._redis_client = Mock()
        lock_module._redis_lock_key = "test_key"
        lock_module._redis_lock_value = "test_value"
        
        # Мокаем _stop_redis_renewal с другим RuntimeError
        with patch('app.utils.singleton_lock._stop_redis_renewal') as mock_stop:
            mock_stop.side_effect = RuntimeError("Some other error")
            
            # Импортируем логгер из модуля
            from app.utils.singleton_lock import logger
            with patch.object(logger, 'info') as mock_info:
                with patch.object(logger, 'warning') as mock_warning:
                    # Не должно падать с исключением
                    await _release_redis_lock()
                    
                    # Проверяем, что логируется WARNING
                    mock_warning.assert_called_once()
                    assert "lock_release_failed" in mock_warning.call_args[0][0]
                    mock_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_warmup_cancellation_logs_cancelled(self):
        """
        Тест: warmup cancellation логирует BOOT_WARMUP_CANCELLED.
        """
        from bot_kie import _run_boot_warmups
        
        # Мокаем логгер
        with patch('bot_kie.logger') as mock_logger:
            # Мокаем timeout чтобы вызвать CancelledError
            with patch('asyncio.wait_for', side_effect=asyncio.CancelledError()):
                with patch('bot_kie.log_structured_event'):
                    with patch('bot_kie._BOOT_WARMUP_STATE', {"cancelled": False}):
                        with patch('bot_kie._create_background_task') as mock_bg_task:
                            mock_bg_task.side_effect = [Mock(), Mock(), Mock()]
                            
                            try:
                                await _run_boot_warmups(correlation_id="TEST")
                            except asyncio.CancelledError:
                                pass  # Ожидаем CancelledError
                            
                            # Проверяем, что логируется BOOT_WARMUP_CANCELLED
                            mock_logger.info.assert_called()
                            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                            assert any("BOOT_WARMUP_CANCELLED" in call for call in log_calls)

    @pytest.mark.asyncio
    async def test_warmup_timeout_logs_budget_exceeded(self):
        """
        Тест: warmup timeout логирует BOOT_WARMUP_BUDGET_EXCEEDED.
        """
        from bot_kie import _run_boot_warmups
        
        # Мокаем логгер
        with patch('bot_kie.logger') as mock_logger:
            # Мокаем timeout чтобы вызвать asyncio.TimeoutError
            with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError()):
                with patch('bot_kie.log_structured_event'):
                    with patch('bot_kie._BOOT_WARMUP_STATE', {"cancelled": False}):
                        with patch('bot_kie._create_background_task') as mock_bg_task:
                            mock_bg_task.side_effect = [Mock(), Mock(), Mock()]
                            
                            await _run_boot_warmups(correlation_id="TEST")
                            
                            # Проверяем, что логируется BOOT_WARMUP_BUDGET_EXCEEDED
                            mock_logger.info.assert_called()
                            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                            assert any("BOOT_WARMUP_BUDGET_EXCEEDED" in call for call in log_calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
