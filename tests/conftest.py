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
import socket
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
from tests.webhook_harness import WebhookHarness


def _is_localhost(host: object) -> bool:
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode("utf-8", errors="ignore")
    if not isinstance(host, str):
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(scope="session", autouse=True)
def disable_network_calls():
    """Global network kill-switch for tests."""
    if os.getenv("NETWORK_DISABLED", "1").lower() in ("0", "false", "no"):
        yield
        return

    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if _is_localhost(host):
            return original_create_connection(address, *args, **kwargs)
        raise RuntimeError("NETWORK_DISABLED_IN_TESTS")

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if _is_localhost(host):
            return original_connect(self, address)
        raise RuntimeError("NETWORK_DISABLED_IN_TESTS")

    def guarded_connect_ex(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if _is_localhost(host):
            return original_connect_ex(self, address)
        raise RuntimeError("NETWORK_DISABLED_IN_TESTS")

    socket.create_connection = guarded_create_connection
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    yield
    socket.create_connection = original_create_connection
    socket.socket.connect = original_connect
    socket.socket.connect_ex = original_connect_ex


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
        'BOT_INSTANCE_ID': 'test-instance',
        'DATA_DIR': temp_dir,
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

    from app.storage.factory import reset_storage
    from app.generations.request_dedupe_store import reset_memory_entries
    from app.observability.dedupe_metrics import reset_metrics as reset_dedupe_metrics
    from app.observability.correlation_store import reset_correlation_store

    reset_storage()
    reset_memory_entries()
    reset_dedupe_metrics()
    reset_correlation_store()

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

    reset_storage()
    reset_correlation_store()
    
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


@pytest.fixture(scope="function")
def webhook_harness(monkeypatch, tmp_path):
    """Webhook harness с PTB application и mocked bot transport."""
    env_vars = {
        "TEST_MODE": "1",
        "DRY_RUN": "0",
        "ALLOW_REAL_GENERATION": "1",
        "KIE_STUB": "1",
        "TELEGRAM_BOT_TOKEN": "test_token_12345",
        "ADMIN_ID": "12345",
        "BOT_INSTANCE_ID": "test-instance",
        "BOT_MODE": "webhook",
        "GITHUB_STORAGE_STUB": "1",
        "GITHUB_TOKEN": "stub-token",
        "GITHUB_REPO": "owner/repo",
        "STORAGE_BRANCH": "storage",
        "GITHUB_BRANCH": "main",
        "RUNTIME_STORAGE_DIR": str(tmp_path / "runtime"),
        "WEBHOOK_BASE_URL": "http://127.0.0.1:8000",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    try:
        from app.config import reset_settings
        reset_settings()
    except Exception:
        pass
    try:
        from app.storage.factory import reset_storage
        reset_storage()
    except Exception:
        pass

    h = WebhookHarness()
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
