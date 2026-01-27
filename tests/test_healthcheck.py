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
    async def test_check_kie_api_health_success(self):
        """Тест успешной проверки KIE API."""
        env = {
            'KIE_API_URL': 'https://api.kie.ai',
            'KIE_API_KEY': 'test_key'
        }
        
        with patch.dict('os.environ', env):
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_session.get.return_value.__aenter__.return_value = mock_response
                
                result = await check_kie_api_health()
                
                assert result["status"] == "healthy"
                assert "accessible" in result["message"]
    
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
    
    @pytest.mark.asyncio
    async def test_check_kie_api_health_http_error(self):
        """Тест HTTP ошибки при проверке KIE API."""
        env = {
            'KIE_API_URL': 'https://api.kie.ai',
            'KIE_API_KEY': 'test_key'
        }
        
        with patch.dict('os.environ', env):
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                
                mock_response = AsyncMock()
                mock_response.status = 500
                mock_session.get.return_value.__aenter__.return_value = mock_response
                
                result = await check_kie_api_health()
                
                assert result["status"] == "error"
                assert "500" in result["message"]


class TestHealthHandler:
    """Тесты обработчика healthcheck."""
    
    @pytest.fixture
    def mock_request(self):
        """Мок HTTP запроса."""
        return MagicMock()
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        set_start_time()
    
    @pytest.mark.asyncio
    async def test_health_handler_all_healthy(self, mock_request):
        """Тест healthcheck когда все компоненты здоровы."""
        with patch('app.utils.healthcheck.check_database_health', return_value={"status": "healthy"}):
            with patch('app.utils.healthcheck.check_redis_health', return_value={"status": "healthy"}):
                with patch('app.utils.healthcheck.check_kie_api_health', return_value={"status": "healthy"}):
                    response = await health_handler(mock_request)
                    
                    assert response.status == 200
                    data = await response.json()
                    assert data["ok"] is True
                    assert data["status"] == "ok"
                    assert data["uptime"] >= 0
                    assert "health_checks" in data
                    
                    health_checks = data["health_checks"]
                    assert health_checks["database"]["status"] == "healthy"
                    assert health_checks["redis"]["status"] == "healthy"
                    assert health_checks["kie_api"]["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_health_handler_with_errors(self, mock_request):
        """Тест healthcheck когда есть ошибки."""
        with patch('app.utils.healthcheck.check_database_health', return_value={"status": "error", "message": "DB error"}):
            with patch('app.utils.healthcheck.check_redis_health', return_value={"status": "healthy"}):
                with patch('app.utils.healthcheck.check_kie_api_health', return_value={"status": "warning", "message": "API warning"}):
                    response = await health_handler(mock_request)
                    
                    assert response.status == 503
                    data = await response.json()
                    assert data["ok"] is False
                    assert data["status"] == "error"
                    
                    health_checks = data["health_checks"]
                    assert health_checks["database"]["status"] == "error"
                    assert health_checks["redis"]["status"] == "healthy"
                    assert health_checks["kie_api"]["status"] == "warning"
    
    @pytest.mark.asyncio
    async def test_health_handler_check_exception(self, mock_request):
        """Тест healthcheck когда проверки вызывают исключение."""
        with patch('app.utils.healthcheck.check_database_health', side_effect=Exception("Check failed")):
            response = await health_handler(mock_request)
            
            assert response.status == 503
            data = await response.json()
            assert data["ok"] is False
            assert data["status"] == "error"
            assert "error" in data["health_checks"]
    
    @pytest.mark.asyncio
    async def test_health_handler_storage_mode(self, mock_request):
        """Тест определения storage mode."""
        with patch('app.utils.healthcheck.check_database_health', return_value={"status": "healthy"}):
            with patch('app.utils.healthcheck.check_redis_health', return_value={"status": "healthy"}):
                with patch('app.utils.healthcheck.check_kie_api_health', return_value={"status": "healthy"}):
                    with patch('app.config.get_settings') as mock_settings:
                        mock_instance = MagicMock()
                        mock_instance.get_storage_mode.return_value = "postgres"
                        mock_settings.return_value = mock_instance
                        
                        response = await health_handler(mock_request)
                        data = await response.json()
                        
                        assert data["storage"] == "postgres"
    
    @pytest.mark.asyncio
    async def test_health_handler_kie_mode(self, mock_request):
        """Тест определения KIE mode."""
        with patch('app.utils.healthcheck.check_database_health', return_value={"status": "healthy"}):
            with patch('app.utils.healthcheck.check_redis_health', return_value={"status": "healthy"}):
                with patch('app.utils.healthcheck.check_kie_api_health', return_value={"status": "healthy"}):
                    # Test real mode
                    with patch.dict('os.environ', {'KIE_API_KEY': 'test_key'}, clear=True):
                        response = await health_handler(mock_request)
                        data = await response.json()
                        assert data["kie_mode"] == "real"
                    
                    # Test disabled mode
                    with patch.dict('os.environ', {}, clear=True):
                        response = await health_handler(mock_request)
                        data = await response.json()
                        assert data["kie_mode"] == "disabled"
                    
                    # Test stub mode
                    with patch.dict('os.environ', {'KIE_STUB': '1', 'KIE_API_KEY': 'test_key'}):
                        response = await health_handler(mock_request)
                        data = await response.json()
                        assert data["kie_mode"] == "stub"


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
