"""
P0: Smoke test for health server - ensures server stays alive even when webhook fails.

This test verifies that:
1. Health server starts on 0.0.0.0:PORT
2. Health server remains alive even when WEBHOOK_BASE_URL is missing
3. /health endpoint returns 200 OK
4. Process doesn't exit due to webhook errors
"""

import os
import pytest
import asyncio
import aiohttp
import time
from pathlib import Path


@pytest.mark.asyncio
async def test_health_server_stays_alive_without_webhook():
    """
    P0: Test that health server starts and stays alive even without WEBHOOK_BASE_URL.
    
    This test:
    1. Sets PORT=10000, BOT_MODE=webhook, without WEBHOOK_BASE_URL
    2. Starts main_render.py in background
    3. Waits 2-3 seconds
    4. Checks that /health returns 200 OK
    5. Verifies process is still alive
    """
    # Skip if running in CI without proper setup
    if os.getenv("CI") and not os.getenv("TEST_HEALTH_SERVER"):
        pytest.skip("Health server smoke test requires manual setup in CI")
    
    # Set test environment
    test_port = 10000
    original_env = {
        'PORT': os.environ.get('PORT'),
        'BOT_MODE': os.environ.get('BOT_MODE'),
        'WEBHOOK_BASE_URL': os.environ.get('WEBHOOK_BASE_URL'),
        'TELEGRAM_BOT_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN'),
    }
    
    try:
        # Set test environment (webhook mode without WEBHOOK_BASE_URL)
        os.environ['PORT'] = str(test_port)
        os.environ['BOT_MODE'] = 'webhook'
        if 'WEBHOOK_BASE_URL' in os.environ:
            del os.environ['WEBHOOK_BASE_URL']
        
        # Ensure we have a minimal bot token (can be fake for this test)
        if 'TELEGRAM_BOT_TOKEN' not in os.environ:
            os.environ['TELEGRAM_BOT_TOKEN'] = '123456789:TEST_TOKEN_FOR_HEALTH_CHECK'
        
        # Import and start main in background
        import main_render
        
        # Start main() as background task
        main_task = asyncio.create_task(main_render.main())
        
        # Wait for server to start (2-3 seconds)
        await asyncio.sleep(3)
        
        # Check health endpoint
        health_url = f"http://localhost:{test_port}/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    assert response.status == 200, f"Health endpoint should return 200, got {response.status}"
                    data = await response.json()
                    assert 'status' in data, "Health response should contain 'status' field"
                    assert data['status'] == 'ok', f"Health status should be 'ok', got {data.get('status')}"
        except Exception as e:
            # Cancel main task before failing
            main_task.cancel()
            try:
                await main_task
            except asyncio.CancelledError:
                pass
            pytest.fail(f"Health endpoint check failed: {e}")
        
        # Verify process is still alive (task not done)
        assert not main_task.done(), "Main task should still be running (health server alive)"
        
        # Cleanup: cancel main task
        main_task.cancel()
        try:
            await asyncio.wait_for(main_task, timeout=2)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        
    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

