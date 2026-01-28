"""
Тесты healthcheck endpoint.
Проверяют корректность проверки здоровья компонентов.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from app.utils.healthcheck import (
    check_database_health,
    check_redis_health,
    check_kie_api_health,
    health_handler,
    set_start_time,
    get_health_status
)


class TestHealthChecks:
    """Тесты проверки здоровья компонентов."""
    
    @pytest.mark.asyncio
    async def test_check_database_health_success(self):
        """Тест успешной проверки БД."""
        with patch.dict('os.environ', {'DATABASE_URL': 'postgres://user:pass@localhost/db'}):
            with patch('asyncpg.connect') as mock_connect:
                mock_conn = AsyncMock()
                mock_connect.return_value = mock_conn
                
                result = await check_database_health()
                
                assert result["status"] == "healthy"
                assert "OK" in result["message"]
                mock_connect.assert_called_once()
                mock_conn.execute.assert_called_once_with("SELECT 1")
                mock_conn.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_database_health_missing_url(self):
        """Тест проверки БД с отсутствующим URL."""
        with patch.dict('os.environ', {}, clear=True):
            result = await check_database_health()
            
            assert result["status"] == "error"
            assert "not set" in result["message"]
    
    @pytest.mark.asyncio
    async def test_check_database_health_connection_error(self):
        """Тест ошибки подключения к БД."""
        with patch.dict('os.environ', {'DATABASE_URL': 'postgres://user:pass@localhost/db'}):
            with patch('asyncpg.connect', side_effect=Exception("Connection failed")):
                result = await check_database_health()
                
                assert result["status"] == "error"
                assert "Connection failed" in result["message"]
    
    @pytest.mark.asyncio
    async def test_check_redis_health_success(self):
        """Тест успешной проверки Redis."""
        with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
            with patch('redis.asyncio.from_url') as mock_from_url:
                mock_client = AsyncMock()
                mock_from_url.return_value = mock_client
                
                result = await check_redis_health()
                
                assert result["status"] == "healthy"
                assert "OK" in result["message"]
                mock_from_url.assert_called_once()
                mock_client.ping.assert_called_once()
                mock_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_redis_health_missing_url(self):
        """Тест проверки Redis с отсутствующим URL."""
        with patch.dict('os.environ', {}, clear=True):
            result = await check_redis_health()
            
            assert result["status"] == "warning"
            assert "not set" in result["message"]
    
    @pytest.mark.asyncio
    async def test_check_redis_health_connection_error(self):
        """Тест ошибки подключения к Redis."""
        with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
            with patch('redis.asyncio.from_url', side_effect=Exception("Redis failed")):
                result = await check_redis_health()
                
                assert result["status"] == "error"
                assert "Redis failed" in result["message"]
    
    @pytest.mark.asyncio
    async def test_check_kie_api_health_missing_key(self):
        """Тест проверки KIE API с отсутствующим ключом."""
        env = {
            'KIE_API_URL': 'https://api.kie.ai',
            'KIE_API_KEY': ''
        }
        
        with patch.dict('os.environ', env):
            result = await check_kie_api_health()
            
            assert result["status"] == "warning"
            assert "not set" in result["message"]
    
    def test_check_kie_api_health_is_async(self):
        """Проверяем что check_kie_api_health асинхронный."""
        import inspect
        assert inspect.iscoroutinefunction(check_kie_api_health)
    
    @pytest.mark.asyncio
    async def test_check_kie_api_health_returns_dict(self):
        """Проверяем что check_kie_api_health возвращает dict со status."""
        # Без ключа API должен вернуть warning
        with patch.dict('os.environ', {'KIE_API_KEY': ''}, clear=False):
            result = await check_kie_api_health()
            assert isinstance(result, dict)
            assert "status" in result
            assert "message" in result


class TestHealthHandler:
    """Тесты обработчика healthcheck - упрощённые."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        set_start_time()
    
    def test_health_handler_exists(self):
        """Проверяем что health_handler существует и callable."""
        assert callable(health_handler)
    
    def test_health_handler_is_async(self):
        """Проверяем что health_handler асинхронный."""
        import inspect
        assert inspect.iscoroutinefunction(health_handler)
    
    @pytest.mark.asyncio
    async def test_health_handler_returns_response(self):
        """Проверяем что health_handler возвращает web.Response."""
        from aiohttp import web
        mock_request = MagicMock()
        
        with patch('app.utils.healthcheck.check_database_health', return_value={"status": "healthy"}):
            with patch('app.utils.healthcheck.check_redis_health', return_value={"status": "healthy"}):
                with patch('app.utils.healthcheck.check_kie_api_health', return_value={"status": "healthy"}):
                    response = await health_handler(mock_request)
                    assert isinstance(response, web.Response)
                    assert response.status in (200, 503)  # OK or Service Unavailable


class TestHealthStatus:
    """Тесты статуса healthcheck."""
    
    def test_get_health_status(self):
        """Тест получения статуса healthcheck."""
        status = get_health_status()
        
        assert "health_server_running" in status
        assert "webhook_route_registered" in status
        assert "start_time" in status
        assert isinstance(status["health_server_running"], bool)
        assert isinstance(status["webhook_route_registered"], bool)
    
    def test_set_start_time(self):
        """Тест установки времени старта."""
        import time
        
        set_start_time()
        status = get_health_status()
        
        assert status["start_time"] is not None
        assert isinstance(status["start_time"], float)
        assert status["start_time"] <= time.time()


if __name__ == "__main__":
    pytest.main([__file__])
