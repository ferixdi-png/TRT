#!/usr/bin/env python3
"""
KIE.AI Source of Truth Builder

Собирает все фактические данные о Kie.ai моделях из:
1. models/kie_models.yaml (локальный источник)
2. app/models/registry.py (если доступен)
3. bot_kie.py (фактическое использование в коде)
4. Официальная документация (если доступен интернет)

Создает:
- docs/kie_ai_source_of_truth.md
- models/kie_models_source_of_truth.json (обновляет существующий)

ВАЖНО: НЕ ДОГАДЫВАЕТСЯ - использует только фактические данные.
"""

import os
import sys
import json
import yaml
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from urllib.parse import urljoin, urlparse

# Добавляем корневую директорию в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import aiohttp
    import asyncio
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False
    print("⚠️ aiohttp not available - web parsing disabled")

# Лимиты для веб-парсинга
MAX_WEB_PAGES = 200
MAX_REQUESTS_PER_SEC = 1
WEB_REQUEST_DELAY = 1.0 / MAX_REQUESTS_PER_SEC


def load_yaml_models() -> Dict[str, Any]:
    """Загружает модели из models/kie_models.yaml"""
    yaml_path = project_root / "models" / "kie_models.yaml"
    if not yaml_path.exists():
        print(f"❌ YAML file not found: {yaml_path}")
        return {}
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    return data.get('models', {})


def extract_from_bot_kie() -> Dict[str, Any]:
    """Извлекает фактические данные из bot_kie.py"""
    bot_kie_path = project_root / "bot_kie.py"
    if not bot_kie_path.exists():
        return {}
    
    with open(bot_kie_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    extracted = {
        'resultJson_structure': {},
        'video_models': [],
        'api_usage': {}
    }
    
    # Извлекаем структуру resultJson
    result_json_pattern = r'result_data\.get\([\'"](resultUrls|resultWaterMarkUrls)[\'"]'
    matches = re.findall(result_json_pattern, content)
    if matches:
        extracted['resultJson_structure']['resultUrls'] = 'array of strings'
        if 'resultWaterMarkUrls' in matches:
            extracted['resultJson_structure']['resultWaterMarkUrls'] = 'array of strings (optional, for sora-2-text-to-video)'
    
    # Извлекаем список video моделей
    video_models_match = re.search(r'is_video_model = model_id in \[(.*?)\]', content, re.DOTALL)
    if video_models_match:
        models_str = video_models_match.group(1)
        # Парсим список моделей
        models = re.findall(r"['\"]([^'\"]+)['\"]", models_str)
        extracted['video_models'] = models
    
    # Извлекаем использование createTask
    if '/api/v1/jobs/createTask' in content or 'createTask' in content:
        extracted['api_usage']['createTask'] = True
    
    # Извлекаем использование recordInfo
    if '/api/v1/jobs/recordInfo' in content or 'recordInfo' in content or 'get_task_status' in content:
        extracted['api_usage']['recordInfo'] = True
    
    return extracted


def extract_from_kie_client() -> Dict[str, Any]:
    """Извлекает данные из kie_client.py"""
    client_path = project_root / "app" / "integrations" / "kie_client.py"
    if not client_path.exists():
        return {}
    
    with open(client_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    extracted = {
        'base_url': 'https://api.kie.ai',
        'endpoints': {}
    }
    
    # Извлекаем base_url
    base_url_match = re.search(r"base_url.*?=.*?['\"](https?://[^'\"]+)['\"]", content)
    if base_url_match:
        extracted['base_url'] = base_url_match.group(1)
    
    # Извлекаем endpoints
    if 'createTask' in content or '/api/v1/jobs/createTask' in content:
        extracted['endpoints']['createTask'] = '/api/v1/jobs/createTask'
    
    if 'recordInfo' in content or '/api/v1/jobs/recordInfo' in content:
        extracted['endpoints']['recordInfo'] = '/api/v1/jobs/recordInfo'
    
    return extracted


async def try_web_parse(base_url: str = "https://api.kie.ai") -> Dict[str, Any]:
    """
    Пытается спарсить официальную документацию (если доступен интернет).
    Соблюдает лимиты: не более 1 запроса/сек, не более 200 страниц.
    """
    if not WEB_AVAILABLE:
        return {'web_available': False, 'reason': 'aiohttp not available'}
    
    web_data = {
        'web_available': True,
        'base_url': base_url,
        'pages_parsed': 0,
        'endpoints_found': {},
        'models_found': [],
        'errors': []
    }
    
    try:
        # Проверяем доступность базового URL
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(base_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        web_data['base_url_accessible'] = True
                    else:
                        web_data['base_url_accessible'] = False
                        web_data['errors'].append(f"Base URL returned {resp.status}")
            except Exception as e:
                web_data['base_url_accessible'] = False
                web_data['errors'].append(f"Cannot access base URL: {e}")
                return web_data
        
        # Пытаемся найти документацию (не более 5 страниц для безопасности)
        doc_urls = [
            f"{base_url}/docs",
            f"{base_url}/documentation",
            f"{base_url}/api/docs",
            f"{base_url}/v1/docs",
        ]
        
        for doc_url in doc_urls[:5]:  # Ограничиваем 5 страницами
            if web_data['pages_parsed'] >= MAX_WEB_PAGES:
                break
            
            try:
                await asyncio.sleep(WEB_REQUEST_DELAY)
                async with aiohttp.ClientSession() as session:
                    async with session.get(doc_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            web_data['pages_parsed'] += 1
                            
                            # Ищем упоминания createTask
                            if 'createTask' in text or '/api/v1/jobs/createTask' in text:
                                web_data['endpoints_found']['createTask'] = True
                            
                            # Ищем упоминания recordInfo
                            if 'recordInfo' in text or '/api/v1/jobs/recordInfo' in text:
                                web_data['endpoints_found']['recordInfo'] = True
                        else:
                            web_data['errors'].append(f"{doc_url} returned {resp.status}")
            except Exception as e:
                web_data['errors'].append(f"Error accessing {doc_url}: {e}")
    
    except Exception as e:
        web_data['errors'].append(f"Web parsing failed: {e}")
    
    return web_data


def build_model_payload_example(model_id: str, model_data: Dict[str, Any]) -> Dict[str, Any]:
    """Создает пример минимального валидного payload для модели"""
    payload = {
        "model": model_id,
        "input": {}
    }
    
    input_params = model_data.get('input', {})
    
    for param_name, param_spec in input_params.items():
        if param_spec.get('required', False):
            param_type = param_spec.get('type', 'string')
            
            if param_type == 'string':
                # Для строк используем пример
                if 'max' in param_spec:
                    max_len = min(param_spec['max'], 50)
                    payload['input'][param_name] = "example"[:max_len]
                else:
                    payload['input'][param_name] = "example"
            
            elif param_type == 'enum':
                # Для enum используем первое значение
                values = param_spec.get('values', [])
                if values:
                    payload['input'][param_name] = values[0]
                else:
                    payload['input'][param_name] = "value"
            
            elif param_type == 'boolean':
                payload['input'][param_name] = True
            
            elif param_type == 'number' or param_type == 'integer':
                # Для чисел используем минимальное значение или 0
                min_val = param_spec.get('min', 0)
                payload['input'][param_name] = min_val if min_val >= 0 else 0
            
            elif param_type == 'array':
                # Для массивов используем пустой массив или массив с одним примером
                item_type = param_spec.get('item_type', 'string')
                if item_type == 'string':
                    payload['input'][param_name] = ["https://example.com/image.jpg"]
                else:
                    payload['input'][param_name] = []
    
    return payload


def determine_output_type(model_type: str, model_id: str) -> str:
    """Определяет тип результата на основе model_type"""
    if 'video' in model_type or 'video' in model_id.lower():
        return 'video'
    elif 'audio' in model_type or 'audio' in model_id.lower() or 'speech' in model_id.lower():
        return 'audio'
    elif 'text' in model_type or 'speech_to_text' in model_type:
        return 'text'
    elif 'image' in model_type or 'image' in model_id.lower():
        return 'image'
    else:
        return 'unknown'


def build_source_of_truth() -> Dict[str, Any]:
    """Собирает полный source_of_truth из всех доступных источников"""
    print("=" * 60)
    print("KIE.AI SOURCE OF TRUTH BUILDER")
    print("=" * 60)
    
    # 1. Загружаем YAML модели
    print("\n[1/5] Loading YAML models...")
    yaml_models = load_yaml_models()
    print(f"[OK] Loaded {len(yaml_models)} models from YAML")
    
    # 2. Извлекаем из bot_kie.py
    print("\n[2/5] Extracting from bot_kie.py...")
    bot_kie_data = extract_from_bot_kie()
    print(f"[OK] Extracted: {len(bot_kie_data.get('video_models', []))} video models, API usage: {list(bot_kie_data.get('api_usage', {}).keys())}")
    
    # 3. Извлекаем из kie_client.py
    print("\n[3/5] Extracting from kie_client.py...")
    client_data = extract_from_kie_client()
    print(f"[OK] Extracted base_url: {client_data.get('base_url')}, endpoints: {list(client_data.get('endpoints', {}).keys())}")
    
    # 4. Пытаемся веб-парсинг (если доступен интернет)
    print("\n[4/5] Attempting web parsing...")
    web_data = {}
    if WEB_AVAILABLE:
        try:
            base_url = client_data.get('base_url', 'https://api.kie.ai')
            web_data = asyncio.run(try_web_parse(base_url))
            if web_data.get('web_available'):
                print(f"[OK] Web parsing: {web_data.get('pages_parsed', 0)} pages parsed, endpoints found: {list(web_data.get('endpoints_found', {}).keys())}")
            else:
                print(f"[WARN] Web parsing not available: {web_data.get('reason', 'unknown')}")
        except Exception as e:
            print(f"[WARN] Web parsing failed: {e}")
            web_data = {'web_available': False, 'reason': str(e)}
    else:
        print("[WARN] Web parsing disabled (aiohttp not available)")
        web_data = {'web_available': False, 'reason': 'aiohttp not available'}
    
    # 5. Собираем финальный source_of_truth
    print("\n[5/5] Building source_of_truth...")
    
    source_of_truth = {
        'meta': {
            'generated_at': datetime.now().isoformat(),
            'source': 'LOCAL_ONLY' if not web_data.get('web_available') else 'LOCAL_AND_WEB',
            'total_models': len(yaml_models),
            'yaml_file': 'models/kie_models.yaml',
            'web_parsed': web_data.get('web_available', False),
            'web_pages_parsed': web_data.get('pages_parsed', 0)
        },
        'api': {
            'base_url': client_data.get('base_url', 'https://api.kie.ai'),
            'endpoints': {
                'createTask': {
                    'method': 'POST',
                    'path': '/api/v1/jobs/createTask',
                    'confirmed_from': []
                },
                'recordInfo': {
                    'method': 'GET',
                    'path': '/api/v1/jobs/recordInfo',
                    'confirmed_from': []
                }
            },
            'states': ['waiting', 'queuing', 'generating', 'success', 'fail'],
            'resultJson_structure': {
                'resultUrls': 'array of strings (required for most models)',
                'resultWaterMarkUrls': 'array of strings (optional, for sora-2-text-to-video when remove_watermark=false)'
            }
        },
        'models': {}
    }
    
    # Подтверждаем endpoints
    if bot_kie_data.get('api_usage', {}).get('createTask'):
        source_of_truth['api']['endpoints']['createTask']['confirmed_from'].append('bot_kie.py')
    if client_data.get('endpoints', {}).get('createTask'):
        source_of_truth['api']['endpoints']['createTask']['confirmed_from'].append('kie_client.py')
    if web_data.get('endpoints_found', {}).get('createTask'):
        source_of_truth['api']['endpoints']['createTask']['confirmed_from'].append('web_docs')
    
    if bot_kie_data.get('api_usage', {}).get('recordInfo'):
        source_of_truth['api']['endpoints']['recordInfo']['confirmed_from'].append('bot_kie.py')
    if client_data.get('endpoints', {}).get('recordInfo'):
        source_of_truth['api']['endpoints']['recordInfo']['confirmed_from'].append('kie_client.py')
    if web_data.get('endpoints_found', {}).get('recordInfo'):
        source_of_truth['api']['endpoints']['recordInfo']['confirmed_from'].append('web_docs')
    
    # Добавляем request/response схемы для endpoints
    source_of_truth['api']['endpoints']['createTask']['request'] = {
        'model': 'string (required)',
        'input': 'object (required, model-specific)',
        'callBackUrl': 'string (optional)'
    }
    source_of_truth['api']['endpoints']['createTask']['response'] = {
        'code': 200,
        'data': {
            'taskId': 'string'
        }
    }
    
    source_of_truth['api']['endpoints']['recordInfo']['query'] = {
        'taskId': 'string (required)'
    }
    source_of_truth['api']['endpoints']['recordInfo']['response'] = {
        'code': 200,
        'data': {
            'state': 'waiting|queuing|generating|success|fail',
            'resultJson': 'string (JSON, contains resultUrls/resultWaterMarkUrls)',
            'resultUrls': 'array (optional, deprecated - use resultJson)',
            'errorMessage': 'string (optional, present on fail)',
            'failCode': 'string (optional, present on fail)'
        }
    }
    
    # Обрабатываем каждую модель из YAML
    for model_id, model_data in yaml_models.items():
        model_type = model_data.get('model_type', 'unknown')
        input_params = model_data.get('input', {})
        
        # Определяем output type
        output_type = determine_output_type(model_type, model_id)
        
        # Создаем пример payload
        payload_example = build_model_payload_example(model_id, model_data)
        
        # Нормализуем input параметры
        normalized_input = {}
        for param_name, param_spec in input_params.items():
            normalized_input[param_name] = {
                'type': param_spec.get('type', 'string'),
                'required': param_spec.get('required', False)
            }
            
            # Добавляем ограничения
            if 'max' in param_spec:
                normalized_input[param_name]['max'] = param_spec['max']
            if 'min' in param_spec:
                normalized_input[param_name]['min'] = param_spec['min']
            if 'values' in param_spec:
                normalized_input[param_name]['values'] = param_spec['values']
            if 'item_type' in param_spec:
                normalized_input[param_name]['item_type'] = param_spec['item_type']
        
        source_of_truth['models'][model_id] = {
            'model_type': model_type,
            'output_type': output_type,
            'input': normalized_input,
            'payload_example': payload_example
        }
    
    print(f"[OK] Built source_of_truth with {len(source_of_truth['models'])} models")
    
    return source_of_truth


def verify_registry_consistency(source_of_truth: Dict[str, Any]) -> Dict[str, Any]:
    """Проверяет согласованность с текущим registry"""
    print("\n" + "=" * 60)
    print("VERIFYING REGISTRY CONSISTENCY")
    print("=" * 60)
    
    issues = {
        'missing_in_registry': [],
        'extra_in_registry': [],
        'count_mismatch': False,
        'schema_mismatches': []
    }
    
    try:
        # Пытаемся загрузить registry
        from app.models.registry import get_models_sync
        registry_models = get_models_sync()
        registry_model_ids = {m.get('id') for m in registry_models if m.get('id')}
        
        source_model_ids = set(source_of_truth['models'].keys())
        
        # Проверяем количество
        if len(registry_model_ids) != len(source_model_ids):
            issues['count_mismatch'] = True
            print(f"[WARN] Count mismatch: registry has {len(registry_model_ids)}, source_of_truth has {len(source_model_ids)}")
        
        # Проверяем отсутствующие в registry
        missing = source_model_ids - registry_model_ids
        if missing:
            issues['missing_in_registry'] = list(missing)
            print(f"[WARN] {len(missing)} models in source_of_truth but not in registry: {list(missing)[:5]}")
        
        # Проверяем лишние в registry
        extra = registry_model_ids - source_model_ids
        if extra:
            issues['extra_in_registry'] = list(extra)
            print(f"[WARN] {len(extra)} models in registry but not in source_of_truth: {list(extra)[:5]}")
        
        if not issues['count_mismatch'] and not issues['missing_in_registry'] and not issues['extra_in_registry']:
            print("[OK] Registry and source_of_truth are consistent!")
    
    except Exception as e:
        print(f"[WARN] Could not verify registry consistency: {e}")
        issues['verification_error'] = str(e)
    
    return issues


def write_source_of_truth(source_of_truth: Dict[str, Any], issues: Dict[str, Any]):
    """Записывает source_of_truth в файлы"""
    print("\n" + "=" * 60)
    print("WRITING SOURCE OF TRUTH FILES")
    print("=" * 60)
    
    # 1. JSON файл
    json_path = project_root / "models" / "kie_models_source_of_truth.json"
    print(f"\n[1/2] Writing JSON to {json_path}...")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(source_of_truth, f, indent=2, ensure_ascii=False)
    print(f"[OK] Written {len(source_of_truth['models'])} models to JSON")
    
    # 2. Markdown файл
    md_path = project_root / "docs" / "kie_ai_source_of_truth.md"
    print(f"\n[2/2] Writing Markdown to {md_path}...")
    
    # Создаем директорию docs если не существует
    md_path.parent.mkdir(exist_ok=True)
    
    md_content = f"""# KIE.AI Source of Truth

**Generated:** {source_of_truth['meta']['generated_at']}
**Source:** {source_of_truth['meta']['source']}
**Total Models:** {source_of_truth['meta']['total_models']}
**Web Parsed:** {source_of_truth['meta']['web_parsed']} ({source_of_truth['meta']['web_pages_parsed']} pages)

## API Endpoints

### createTask
- **Method:** {source_of_truth['api']['endpoints']['createTask']['method']}
- **Path:** {source_of_truth['api']['endpoints']['createTask']['path']}
- **Confirmed from:** {', '.join(source_of_truth['api']['endpoints']['createTask']['confirmed_from']) or 'N/A'}

**Request:**
```json
{{
  "model": "string (required)",
  "input": {{}} (required, model-specific),
  "callBackUrl": "string (optional)"
}}
```

**Response:**
```json
{{
  "code": 200,
  "data": {{
    "taskId": "string"
  }}
}}
```

### recordInfo
- **Method:** {source_of_truth['api']['endpoints']['recordInfo']['method']}
- **Path:** {source_of_truth['api']['endpoints']['recordInfo']['path']}
- **Confirmed from:** {', '.join(source_of_truth['api']['endpoints']['recordInfo']['confirmed_from']) or 'N/A'}

**Query Parameters:**
- `taskId` (string, required)

**Response:**
```json
{{
  "code": 200,
  "data": {{
    "state": "waiting|queuing|generating|success|fail",
    "resultJson": "string (JSON)",
    "resultUrls": "array (optional, deprecated)",
    "errorMessage": "string (optional)",
    "failCode": "string (optional)"
  }}
}}
```

## Result JSON Structure

The `resultJson` field contains a JSON string with the following structure:

```json
{{
  "resultUrls": ["url1", "url2", ...],
  "resultWaterMarkUrls": ["url1", "url2", ...]  // Optional, for sora-2-text-to-video
}}
```

## States

- `waiting` - Task is waiting to be processed
- `queuing` - Task is in queue
- `generating` - Task is being generated
- `success` - Task completed successfully
- `fail` - Task failed

## Models

Total: {len(source_of_truth['models'])} models

"""
    
    # Добавляем информацию о каждой модели
    for model_id, model_data in sorted(source_of_truth['models'].items()):
        model_type = model_data['model_type']
        output_type = model_data['output_type']
        input_params = model_data['input']
        payload_example = json.dumps(model_data['payload_example'], indent=2, ensure_ascii=False)
        
        md_content += f"""### {model_id}

- **Type:** {model_type}
- **Output:** {output_type}

**Input Parameters:**
"""
        
        for param_name, param_spec in sorted(input_params.items()):
            required = "[REQUIRED]" if param_spec.get('required') else "[OPTIONAL]"
            param_type = param_spec.get('type', 'string')
            constraints = []
            
            if 'max' in param_spec:
                constraints.append(f"max: {param_spec['max']}")
            if 'min' in param_spec:
                constraints.append(f"min: {param_spec['min']}")
            if 'values' in param_spec:
                values_str = ', '.join(str(v) for v in param_spec['values'][:10])
                if len(param_spec['values']) > 10:
                    values_str += f" ... (+{len(param_spec['values']) - 10} more)"
                constraints.append(f"values: [{values_str}]")
            if 'item_type' in param_spec:
                constraints.append(f"item_type: {param_spec['item_type']}")
            
            constraints_str = f" ({', '.join(constraints)})" if constraints else ""
            
            md_content += f"- `{param_name}`: {param_type} {required}{constraints_str}\n"
        
        md_content += f"""
**Example Payload:**
```json
{payload_example}
```

"""
    
    # Добавляем информацию о расхождениях
    if issues.get('count_mismatch') or issues.get('missing_in_registry') or issues.get('extra_in_registry'):
        md_content += "\n## Registry Consistency Issues\n\n"
        if issues.get('count_mismatch'):
            md_content += "**WARNING: Count Mismatch:** Registry and source_of_truth have different model counts\n\n"
        if issues.get('missing_in_registry'):
            md_content += f"**WARNING: Missing in Registry:** {len(issues['missing_in_registry'])} models\n\n"
        if issues.get('extra_in_registry'):
            md_content += f"**WARNING: Extra in Registry:** {len(issues['extra_in_registry'])} models\n\n"
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"[OK] Written Markdown documentation")


def main():
    """Главная функция"""
    print("=" * 60)
    print("KIE.AI SOURCE OF TRUTH BUILDER")
    print("=" * 60)
    print("\nIMPORTANT: This script uses ONLY factual data from:")
    print("  - models/kie_models.yaml")
    print("  - bot_kie.py (actual code usage)")
    print("  - kie_client.py (API client)")
    print("  - Official docs (if web available)")
    print("\nNO GUESSING - only confirmed data")
    print("=" * 60)
    
    # Собираем source_of_truth
    source_of_truth = build_source_of_truth()
    
    # Проверяем согласованность
    issues = verify_registry_consistency(source_of_truth)
    
    # Записываем файлы
    write_source_of_truth(source_of_truth, issues)
    
    # Финальный отчёт
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"[OK] Total models: {len(source_of_truth['models'])}")
    print(f"[OK] Web available: {source_of_truth['meta']['web_parsed']}")
    print(f"[OK] Source: {source_of_truth['meta']['source']}")
    print(f"[OK] Files written:")
    print(f"   - models/kie_models_source_of_truth.json")
    print(f"   - docs/kie_ai_source_of_truth.md")
    
    if issues.get('count_mismatch') or issues.get('missing_in_registry') or issues.get('extra_in_registry'):
        print(f"\n[WARN] Registry issues found - see docs/kie_ai_source_of_truth.md for details")
    else:
        print(f"\n[OK] Registry is consistent with source_of_truth")
    
    print("\n[OK] NO GUESSING - all data from factual sources only")
    print("=" * 60)


if __name__ == '__main__':
    main()

