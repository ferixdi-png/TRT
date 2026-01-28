"""
Webhook port bind smoke test for Render deployment.

Verifies that:
1. Health server binds to port quickly (< 5 seconds)
2. /health endpoint responds with 200 OK
3. /webhook endpoint is registered and accepts POST
4. Server handles concurrent requests without blocking
"""

import asyncio
import os
import socket
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession, ClientTimeout

from app.utils.healthcheck import start_health_server, stop_health_server, get_health_status


def _find_free_port() -> int:
    """Find a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class TestWebhookPortBind:
    """Tests for webhook port binding on Render."""

    @pytest.mark.asyncio
    async def test_health_server_binds_port_quickly(self):
        """Verify health server binds to port in < 5 seconds."""
        port = _find_free_port()
        
        start_time = time.monotonic()
        
        # Start health server without webhook handler
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        
        bind_time = time.monotonic() - start_time
        
        try:
            assert result is True, "Health server should start successfully"
            assert bind_time < 5.0, f"Port bind took {bind_time:.2f}s, should be < 5s"
            
            # Verify port is actually listening
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', port),
                timeout=1.0
            )
            writer.close()
            await writer.wait_closed()
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_health_endpoint_responds_with_json(self):
        """Verify /health endpoint responds with valid JSON (status may be 503 without DB)."""
        port = _find_free_port()
        
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        assert result is True
        
        try:
            timeout = ClientTimeout(total=2.0)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(f'http://127.0.0.1:{port}/health') as response:
                    # Status may be 200 or 503 depending on DB/Redis availability
                    assert response.status in (200, 503), f"Unexpected status: {response.status}"
                    data = await response.json()
                    # Must have required fields regardless of status
                    assert 'status' in data
                    assert 'uptime' in data
                    assert 'ok' in data
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_healthz_endpoint_responds_with_json(self):
        """Verify /healthz endpoint responds with valid JSON (Kubernetes compatibility)."""
        port = _find_free_port()
        
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        assert result is True
        
        try:
            timeout = ClientTimeout(total=2.0)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(f'http://127.0.0.1:{port}/healthz') as response:
                    # Status may be 200 or 503 depending on DB/Redis availability
                    assert response.status in (200, 503), f"Unexpected status: {response.status}"
                    data = await response.json()
                    assert 'status' in data
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_webhook_route_registered_with_handler(self):
        """Verify /webhook route is registered when handler is provided."""
        port = _find_free_port()
        
        # Create a mock webhook handler
        async def mock_webhook_handler(request):
            from aiohttp import web
            return web.Response(status=200, text='OK')
        
        result = await start_health_server(
            port=port, 
            webhook_handler=mock_webhook_handler, 
            self_check=True
        )
        assert result is True
        
        try:
            # Check that webhook route is registered
            status = get_health_status()
            assert status['webhook_route_registered'] is True
            
            # Verify webhook endpoint accepts POST
            timeout = ClientTimeout(total=2.0)
            async with ClientSession(timeout=timeout) as session:
                async with session.post(f'http://127.0.0.1:{port}/webhook', json={}) as response:
                    assert response.status == 200
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_webhook_route_not_registered_without_handler(self):
        """Verify /webhook route is NOT registered when no handler is provided."""
        port = _find_free_port()
        
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        assert result is True
        
        try:
            status = get_health_status()
            assert status['webhook_route_registered'] is False
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_server_handles_concurrent_health_checks(self):
        """Verify server handles multiple concurrent health checks."""
        port = _find_free_port()
        
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        assert result is True
        
        try:
            timeout = ClientTimeout(total=5.0)
            
            async def make_request():
                async with ClientSession(timeout=timeout) as session:
                    async with session.get(f'http://127.0.0.1:{port}/health') as response:
                        return response.status
            
            # Make 10 concurrent requests
            tasks = [make_request() for _ in range(10)]
            results = await asyncio.gather(*tasks)
            
            # All should return valid HTTP status (200 or 503)
            assert all(status in (200, 503) for status in results)
            # All should return the same status (consistent behavior)
            assert len(set(results)) == 1, "All concurrent requests should return same status"
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_port_zero_skips_server(self):
        """Verify port=0 skips server startup (for testing)."""
        result = await start_health_server(port=0, webhook_handler=None)
        assert result is False
        
        status = get_health_status()
        assert status['health_server_running'] is False

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(self):
        """Verify starting server twice is safe (idempotent)."""
        port = _find_free_port()
        
        result1 = await start_health_server(port=port, webhook_handler=None, self_check=True)
        assert result1 is True
        
        try:
            # Second start should return True without error
            result2 = await start_health_server(port=port, webhook_handler=None, self_check=True)
            assert result2 is True
            
            # Server should still be running
            status = get_health_status()
            assert status['health_server_running'] is True
        finally:
            await stop_health_server()


class TestRenderDeploymentSimulation:
    """Simulate Render deployment conditions."""

    @pytest.mark.asyncio
    async def test_port_bind_before_telegram_init(self):
        """
        Critical test: Port must bind BEFORE Telegram API initialization.
        
        This simulates the Render deployment scenario where:
        1. Container starts
        2. Port must be open within seconds
        3. Telegram webhook setup happens later (may timeout)
        
        The port MUST be open even if Telegram API is slow/unavailable.
        """
        port = _find_free_port()
        
        # Simulate slow Telegram API by not initializing application
        start_time = time.monotonic()
        
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        
        bind_time = time.monotonic() - start_time
        
        try:
            assert result is True, "Health server must start without Telegram"
            assert bind_time < 2.0, f"Port bind took {bind_time:.2f}s, should be < 2s"
            
            # Verify health endpoint works (may return 503 without DB, but must respond)
            timeout = ClientTimeout(total=1.0)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(f'http://127.0.0.1:{port}/health') as response:
                    assert response.status in (200, 503), f"Unexpected status: {response.status}"
                    data = await response.json()
                    assert 'status' in data
        finally:
            await stop_health_server()

    @pytest.mark.asyncio
    async def test_webhook_health_echo_endpoint(self):
        """Test /webhook/health echo endpoint for webhook verification."""
        port = _find_free_port()
        
        result = await start_health_server(port=port, webhook_handler=None, self_check=True)
        assert result is True
        
        try:
            timeout = ClientTimeout(total=2.0)
            async with ClientSession(timeout=timeout) as session:
                async with session.post(f'http://127.0.0.1:{port}/webhook/health') as response:
                    assert response.status == 200
                    data = await response.json()
                    assert data['ok'] is True
                    assert data['path'] == '/webhook/health'
        finally:
            await stop_health_server()
