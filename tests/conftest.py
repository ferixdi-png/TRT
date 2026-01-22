"""
Pytest configuration и фикстуры для тестов.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import pytest
import asyncio
import inspect
from pathlib import Path


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _ensure_test_dependencies() -> None:
    bootstrap_enabled = os.getenv("VERIFY_BOOTSTRAP", "1").lower() not in ("0", "false", "no")
    if not bootstrap_enabled:
        return
    missing = []
    for module_name in ("telegram", "yaml"):
        if not _module_available(module_name):
            missing.append(module_name)
    if not missing:
        return
    requirements_file = Path(__file__).resolve().parents[1] / "requirements.txt"
    print(f"ℹ️ Missing test modules: {', '.join(missing)}. Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)])


_ensure_test_dependencies()

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
        'STORAGE_MODE': 'db',
        'BOT_INSTANCE_ID': 'test-instance',
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
        signature = inspect.signature(pyfuncitem.obj)
        allowed_kwargs = {
            name: value
            for name, value in pyfuncitem.funcargs.items()
            if name in signature.parameters
        }
        loop.run_until_complete(pyfuncitem.obj(**allowed_kwargs))
        loop.close()
        return True
    return None
