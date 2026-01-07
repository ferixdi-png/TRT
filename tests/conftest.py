<<<<<<< HEAD
"""
Pytest configuration и фикстуры для тестов.
"""

import os
import pytest
import pytest_asyncio
from tests.ptb_harness import PTBHarness


@pytest.fixture(scope="function")
def test_env():
    """Устанавливает тестовые переменные окружения."""
    old_env = {}
    test_vars = {
        'TEST_MODE': '1',
        'DRY_RUN': '1',
        'ALLOW_REAL_GENERATION': '0',
        'TELEGRAM_BOT_TOKEN': 'test_token_12345',
        'KIE_API_KEY': 'test_api_key',
        'ADMIN_ID': '12345',
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


@pytest_asyncio.fixture(scope="function")
async def harness(test_env):
    """Создает и возвращает PTBHarness для тестов."""
    h = PTBHarness()
    await h.setup()
    yield h
    await h.teardown()
=======
"""Pytest configuration for test path setup."""
import sys
import os
import pytest

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture
def source_of_truth_models_as_list():
    """
    Load SOURCE_OF_TRUTH and convert models dict to list for backward compatibility.
    
    New format (v1.2.10): {"models": {model_id: {...}}}
    Old format (tests expect): {"models": [{model_id: ..., ...}]}
    """
    from app.kie.builder import load_source_of_truth
    
    sot = load_source_of_truth()
    models = sot.get('models', {})
    
    # Convert dict to list
    if isinstance(models, dict):
        models_list = []
        for model_id, model_data in models.items():
            model_copy = model_data.copy()
            if 'model_id' not in model_copy:
                model_copy['model_id'] = model_id
            models_list.append(model_copy)
        sot['models'] = models_list
    
    return sot
>>>>>>> cbb364c8c317bf2ab285b1261d4d267c35b303d6

