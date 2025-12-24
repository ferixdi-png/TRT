#!/usr/bin/env python3
"""
DRY-RUN валидация payload для всех моделей БЕЗ трат кредитов
Проверяет:
1. Структура payload соответствует schema
2. Все required поля присутствуют
3. Типы данных корректные
4. Можно построить валидный request (но не отправляем)
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List


def load_registry() -> Dict:
    """Загружаем registry"""
    with open('models/KIE_SOURCE_OF_TRUTH.json', 'r') as f:
        return json.load(f)


def validate_payload_structure(model_id: str, example: Dict, schema: Dict) -> List[str]:
    """Валидация структуры payload"""
    errors = []
    
    # 1. Проверяем обязательные поля верхнего уровня
    required_top = ['model', 'callBackUrl', 'input']
    for field in required_top:
        if field not in example:
            errors.append(f"Missing required field: {field}")
    
    # 2. Проверяем что model совпадает
    if example.get('model') != model_id:
        errors.append(f"model mismatch: example has '{example.get('model')}', expected '{model_id}'")
    
    # 3. Проверяем input поля
    input_data = example.get('input', {})
    schema_input = schema.get('input', {})
    
    if not isinstance(input_data, dict):
        errors.append(f"input must be dict, got {type(input_data)}")
        return errors
    
    # Извлекаем примеры полей из schema
    if 'examples' in schema_input and schema_input['examples']:
        expected_fields = set(schema_input['examples'][0].keys())
        actual_fields = set(input_data.keys())
        
        # Проверяем что нет лишних полей (необязательно, но полезно)
        extra_fields = actual_fields - expected_fields
        if extra_fields:
            errors.append(f"Extra fields in input: {extra_fields}")
    
    return errors


def validate_model_payload(model_id: str, model_data: Dict) -> Dict[str, Any]:
    """Валидация payload для одной модели"""
    result = {
        'model_id': model_id,
        'status': 'unknown',
        'errors': [],
        'warnings': []
    }
    
    # Проверяем наличие schema
    schema = model_data.get('input_schema', {})
    if not schema:
        result['status'] = 'error'
        result['errors'].append('No input_schema defined')
        return result
    
    # Проверяем наличие examples
    examples = model_data.get('examples', [])
    if not examples:
        result['status'] = 'warning'
        result['warnings'].append('No examples defined')
        return result
    
    # Валидируем первый example
    example = examples[0]
    errors = validate_payload_structure(model_id, example, schema)
    
    if errors:
        result['status'] = 'error'
        result['errors'].extend(errors)
    else:
        result['status'] = 'success'
    
    return result


def build_mock_request(model_id: str, example: Dict) -> Dict:
    """Строим mock request (для визуализации, не отправляем)"""
    
    # Kie.ai API v4 формат
    return {
        'endpoint': 'https://api.kie.ai/api/v1/jobs/createTask',
        'method': 'POST',
        'headers': {
            'Authorization': 'Bearer YOUR_API_KEY',
            'Content-Type': 'application/json'
        },
        'payload': example
    }


def main():
    print("=" * 80)
    print("🔍 DRY-RUN PAYLOAD VALIDATION (NO CREDITS SPENT)")
    print("=" * 80)
    
    registry = load_registry()
    models = registry['models']
    
    results = []
    
    for model_id, model_data in models.items():
        result = validate_model_payload(model_id, model_data)
        results.append(result)
    
    # Статистика
    success = [r for r in results if r['status'] == 'success']
    errors = [r for r in results if r['status'] == 'error']
    warnings = [r for r in results if r['status'] == 'warning']
    
    print(f"\n📊 VALIDATION RESULTS:")
    print(f"   ✅ Success: {len(success)}/{len(models)} ({len(success)*100//len(models)}%)")
    print(f"   ❌ Errors: {len(errors)}")
    print(f"   ⚠️  Warnings: {len(warnings)}")
    
    # Показываем ошибки
    if errors:
        print(f"\n❌ MODELS WITH ERRORS:")
        for r in errors[:10]:
            print(f"\n  {r['model_id']}:")
            for err in r['errors']:
                print(f"    - {err}")
    
    # Проверяем Top-5 cheapest
    print(f"\n💰 TOP-5 CHEAPEST VALIDATION:")
    
    models_with_price = [(mid, m) for mid, m in models.items() if m.get('pricing')]
    cheapest = sorted(models_with_price, key=lambda x: x[1]['pricing'].get('usd_per_gen', 999))[:5]
    
    for mid, m in cheapest:
        # Находим результат валидации
        res = next((r for r in results if r['model_id'] == mid), None)
        
        if res:
            status_icon = "✅" if res['status'] == 'success' else "❌"
            price = m['pricing']['usd_per_gen']
            print(f"  {status_icon} {mid} (${price}): {res['status']}")
            
            if res['errors']:
                for err in res['errors']:
                    print(f"      - {err}")
    
    # Сохраняем результаты
    output = {
        'total': len(results),
        'success': len(success),
        'errors': len(errors),
        'warnings': len(warnings),
        'details': results
    }
    
    output_file = Path('artifacts/dry_run_validation.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results saved: {output_file}")
    
    # Mock request example для Top-1 cheapest
    if cheapest:
        top1_id, top1_data = cheapest[0]
        if top1_data.get('examples'):
            mock_req = build_mock_request(top1_id, top1_data['examples'][0])
            
            print(f"\n📋 MOCK REQUEST EXAMPLE ({top1_id}):")
            print(json.dumps(mock_req, indent=2)[:500] + "...")
    
    # Exit code
    if errors:
        print(f"\n❌ Validation failed: {len(errors)} models have errors")
        return 1
    else:
        print(f"\n✅ All models passed dry-run validation!")
        return 0


if __name__ == '__main__':
    exit(main())
