"""
Pytest configuration и фикстуры для тестов.
"""

import os
import shutil
import tempfile
import pytest
import asyncio
import inspect
from tests.ptb_harness import PTBHarness


@pytest.fixture(scope="function")
def test_env():
    """Устанавливает тестовые переменные окружения."""
    old_env = {}
    temp_dir = tempfile.mkdtemp(prefix="trt-test-storage-")
    test_vars = {
        'TEST_MODE': '1',
        'DRY_RUN': '1',
        'ALLOW_REAL_GENERATION': '0',
        'TELEGRAM_BOT_TOKEN': 'test_token_12345',
        'KIE_API_KEY': 'test_api_key',
        'ADMIN_ID': '12345',
        'STORAGE_MODE': 'json',
        'STORAGE_DATA_DIR': temp_dir,
    }
    
    # Сохраняем старые значения
    for key in test_vars:
        old_env[key] = os.environ.get(key)
        os.environ[key] = test_vars[key]
    
    # Сбрасываем singleton'ы после установки env переменных
    try:
        from app.config import reset_settings
        reset_settings()
    except ImportError:
        pass
    
    try:
        from kie_gateway import reset_gateway
        reset_gateway()
    except ImportError:
        pass
    
    yield
    
    # Снова сбрасываем singleton'ы в teardown
    try:
        from app.config import reset_settings
        reset_settings()
    except ImportError:
        pass
    
    try:
        from kie_gateway import reset_gateway
        reset_gateway()
    except ImportError:
        pass
    
    # Восстанавливаем старые значения
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def harness(test_env):
    """Создает и возвращает PTBHarness для тестов."""
    h = PTBHarness()
    asyncio.run(h.setup())
    yield h
    asyncio.run(h.teardown())


def pytest_pyfunc_call(pyfuncitem):
    """Поддержка async тестов без pytest-asyncio."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(pyfuncitem.obj(**pyfuncitem.funcargs))
        loop.close()
        return True
    return None
