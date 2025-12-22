"""
KIE API Sanity Test - тестирует все model_type из models/kie_models.yaml

Загружает models/kie_models.yaml
Берёт 1 модель каждого model_type
Подставляет минимально валидный input
Запускает createTask + waitTask
Выводит таблицу: model | model_type | state | ok/fail | time
"""

import os
import sys
import json
import time
import yaml
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

try:
    from dotenv import load_dotenv
    env_path = root_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Импортируем KIE client
try:
    from kie_client import get_client
    from kie_validator import validate, get_model_schema, load_models_registry
except ImportError as e:
    print(f"ERROR: Failed to import modules: {e}")
    print("Make sure you're running from project root and all dependencies are installed")
    sys.exit(1)

BASE = "https://api.kie.ai"
API_KEY = os.getenv("KIE_API_KEY")
if not API_KEY:
    raise SystemExit("ERROR: KIE_API_KEY environment variable not set")


def mask_token(token: str) -> str:
    """Mask API token in logs"""
    if not token or len(token) < 8:
        return "***"
    return token[:4] + "..." + token[-4:]


def generate_minimal_input(model_id: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Генерирует минимально валидный input для модели на основе схемы.
    """
    input_data = {}
    
    for param_name, param_spec in schema.items():
        param_type = param_spec.get('type')
        required = param_spec.get('required', False)
        
        if not required:
            continue  # Пропускаем необязательные параметры для минимального input
        
        if param_type == 'string':
            # Берем первое значение из enum или используем дефолт
            if 'default' in param_spec:
                input_data[param_name] = param_spec['default']
            elif 'values' in param_spec and param_spec['values']:
                input_data[param_name] = param_spec['values'][0]
            else:
                # Минимальный текст для prompt
                min_len = param_spec.get('min', 1)
                if 'prompt' in param_name.lower():
                    input_data[param_name] = "test" * max(1, min_len // 4)
                else:
                    input_data[param_name] = "test"
        
        elif param_type == 'array':
            item_type = param_spec.get('item_type', 'string')
            if 'image' in param_name.lower() or 'video' in param_name.lower():
                # Для image_urls/video_urls нужен реальный URL (пропускаем в тесте)
                # Используем placeholder
                input_data[param_name] = ["https://example.com/test.jpg"]
            else:
                input_data[param_name] = ["test"]
        
        elif param_type == 'boolean':
            input_data[param_name] = param_spec.get('default', False)
        
        elif param_type == 'number' or param_type == 'integer':
            input_data[param_name] = param_spec.get('default', 1)
        
        elif param_type == 'enum':
            if 'values' in param_spec and param_spec['values']:
                input_data[param_name] = param_spec['values'][0]
    
    return input_data


async def test_model(model_id: str, model_type: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Тестирует одну модель: создает задачу и ждет результата.
    """
    start_time = time.time()
    
    # Генерируем минимальный input
    try:
        input_data = generate_minimal_input(model_id, schema)
    except Exception as e:
        return {
            'model': model_id,
            'model_type': model_type,
            'state': 'error',
            'ok': False,
            'time': 0,
            'error': f"Input generation failed: {e}"
        }
    
    # Валидируем input
    is_valid, errors = validate(model_id, input_data)
    if not is_valid:
        return {
            'model': model_id,
            'model_type': model_type,
            'state': 'invalid',
            'ok': False,
            'time': 0,
            'error': f"Validation failed: {'; '.join(errors)}"
        }
    
    # Создаем задачу
    try:
        client = get_client()
        result = await client.create_task(model_id, input_data)
        
        if not result.get('ok'):
            elapsed = time.time() - start_time
            return {
                'model': model_id,
                'model_type': model_type,
                'state': 'error',
                'ok': False,
                'time': int(elapsed),
                'error': result.get('error', 'Unknown error')
            }
        
        task_id = result.get('taskId')
        if not task_id:
            elapsed = time.time() - start_time
            return {
                'model': model_id,
                'model_type': model_type,
                'state': 'error',
                'ok': False,
                'time': int(elapsed),
                'error': 'No taskId in response'
            }
        
        # Ждем завершения (сокращенный timeout для теста)
        try:
            final_result = await client.wait_task(task_id, timeout_s=300, poll_s=3)
            elapsed = time.time() - start_time
            
            state = final_result.get('state')
            if state == 'success':
                return {
                    'model': model_id,
                    'model_type': model_type,
                    'state': 'success',
                    'ok': True,
                    'time': int(elapsed),
                    'error': None
                }
            else:
                error_msg = final_result.get('failMsg') or final_result.get('errorMessage', 'Task failed')
                return {
                    'model': model_id,
                    'model_type': model_type,
                    'state': 'fail',
                    'ok': False,
                    'time': int(elapsed),
                    'error': error_msg
                }
        except TimeoutError:
            elapsed = time.time() - start_time
            return {
                'model': model_id,
                'model_type': model_type,
                'state': 'timeout',
                'ok': False,
                'time': int(elapsed),
                'error': 'Timeout (300s)'
            }
        except ValueError as e:
            elapsed = time.time() - start_time
            return {
                'model': model_id,
                'model_type': model_type,
                'state': 'fail',
                'ok': False,
                'time': int(elapsed),
                'error': str(e)
            }
    
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            'model': model_id,
            'model_type': model_type,
            'state': 'error',
            'ok': False,
            'time': int(elapsed),
            'error': str(e)
        }


async def main():
    """Основная функция: тестирует все model_type"""
    print("=" * 80)
    print("KIE API SANITY TEST - Testing all model_type from models/kie_models.yaml")
    print("=" * 80)
    print(f"API Key: {mask_token(API_KEY)}")
    print(f"Base URL: {BASE}")
    print()
    
    # Загружаем реестр моделей
    registry = load_models_registry()
    if not registry:
        print("ERROR: Failed to load models registry")
        sys.exit(1)
    
    models = registry.get('models', {})
    if not models:
        print("ERROR: No models found in registry")
        sys.exit(1)

    print(f"Loaded {len(models)} models from registry")
    print()
    
    # Группируем модели по model_type
    models_by_type: Dict[str, List[tuple]] = {}
    for model_id, model_info in models.items():
        model_type = model_info.get('model_type')
        if not model_type:
            continue
        if model_type not in models_by_type:
            models_by_type[model_type] = []
        schema = model_info.get('input', {})
        models_by_type[model_type].append((model_id, schema))
    
    print(f"Found {len(models_by_type)} unique model_type:")
    for model_type in sorted(models_by_type.keys()):
        count = len(models_by_type[model_type])
        print(f"  - {model_type}: {count} model(s)")
    print()
    
    # Берем по одной модели каждого типа
    test_models = []
    for model_type, model_list in models_by_type.items():
        if model_list:
            model_id, schema = model_list[0]  # Берем первую модель
            test_models.append((model_id, model_type, schema))
    
    print(f"Testing {len(test_models)} models (one per model_type)...")
    print()
    
    # Тестируем все модели
    results = []
    for i, (model_id, model_type, schema) in enumerate(test_models, 1):
        print(f"[{i}/{len(test_models)}] Testing {model_id} ({model_type})...")
        result = await test_model(model_id, model_type, schema)
        results.append(result)
        
        status = "✅ OK" if result['ok'] else "❌ FAIL"
        print(f"  {status} - {result['state']} ({result['time']}s)")
        if result.get('error'):
            print(f"  Error: {result['error'][:100]}")
        print()
    
    # Выводим таблицу результатов
    print("=" * 80)
    print("RESULTS TABLE")
    print("=" * 80)
    print(f"{'model':<40} {'model_type':<20} {'state':<10} {'ok/fail':<10} {'time':<10}")
    print("-" * 80)
    
    for result in results:
        model = result['model'][:38] + ".." if len(result['model']) > 40 else result['model']
        model_type = result['model_type']
        state = result['state']
        status = "OK" if result['ok'] else "FAIL"
        time_str = f"{result['time']}s"
        
        print(f"{model:<40} {model_type:<20} {state:<10} {status:<10} {time_str:<10}")
    
    print("-" * 80)
    
    # Статистика
    total = len(results)
    success = sum(1 for r in results if r['ok'])
    failed = total - success
    
    print(f"\nTotal: {total} | Success: {success} | Failed: {failed}")
    
    if failed > 0:
        print("\n⚠️  Some model_type failed! Check errors above.")
        sys.exit(1)
    else:
        print("\n✅ All model_type tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
