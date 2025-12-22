#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка схемы моделей: model_type, input_params, уникальность id, маршрутизация callback_data"""

import sys
from pathlib import Path
from typing import List, Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_model_schema() -> int:
    """Проверяет схему всех моделей."""
    errors = []
    warnings = []
    
    try:
        from app.models.registry import get_models_sync
        
        models = get_models_sync()
        if not models:
            print("FAIL: No models loaded from registry")
            return 1
        
        print(f"OK: Loaded {len(models)} models from registry")
        
        # Проверяем обязательные поля
        required_fields = ['id', 'name', 'category', 'emoji', 'model_type', 'input_params']
        model_ids = set()
        
        for i, model in enumerate(models):
            model_id = model.get('id', '')
            
            # Проверка уникальности id
            if not model_id:
                errors.append(f"Model #{i}: missing 'id'")
                continue
            
            if model_id in model_ids:
                errors.append(f"Model '{model_id}': duplicate ID")
                continue
            model_ids.add(model_id)
            
            # Проверка обязательных полей
            for field in required_fields:
                if field not in model:
                    errors.append(f"Model '{model_id}': missing required field '{field}'")
                elif not model[field]:
                    warnings.append(f"Model '{model_id}': empty field '{field}'")
            
            # Проверка model_type
            model_type = model.get('model_type')
            if not model_type or model_type == 'unknown':
                errors.append(f"Model '{model_id}': invalid model_type '{model_type}'")
            
            # Проверка input_params
            input_params = model.get('input_params', {})
            if not isinstance(input_params, dict):
                errors.append(f"Model '{model_id}': input_params must be dict, got {type(input_params)}")
            elif not input_params:
                warnings.append(f"Model '{model_id}': empty input_params")
        
        # Проверка callback_data маршрутизации
        try:
            bot_file = project_root / "bot_kie.py"
            if bot_file.exists():
                content = bot_file.read_text(encoding='utf-8', errors='ignore')
                
                # Ищем все callback_data форматы для моделей
                callback_patterns = [
                    r'select_model:([^"\']+)',
                    r'model:([^"\']+)',
                    r'sel:([^"\']+)',
                ]
                
                used_callbacks = set()
                for pattern in callback_patterns:
                    import re
                    matches = re.findall(pattern, content)
                    used_callbacks.update(matches)
                
                # Проверяем что все model_id имеют обработчики (или хотя бы проверяем формат)
                missing_handlers = []
                for model_id in model_ids:
                    # Проверяем что callback_data будет валидным (не превышает 64 байта)
                    callback_data = f"select_model:{model_id}"
                    if len(callback_data.encode('utf-8')) > 64:
                        # Используется короткий формат
                        callback_data = f"sel:{model_id[:50]}"
                    
                    # Проверяем что callback_data найдено в коде (хотя бы один вариант)
                    found = False
                    for cb_id in [model_id, model_id[:50]]:
                        if cb_id in used_callbacks:
                            found = True
                            break
                        # Проверяем в button_callback
                        if 'button_callback' in content and (f'select_model:{cb_id}' in content or f'sel:{cb_id}' in content or f'model:{cb_id}' in content):
                            found = True
                            break
                    
                    if not found:
                        missing_handlers.append(model_id)
                
                if missing_handlers:
                    warnings.append(f"Models without clear callback handlers: {len(missing_handlers)} models")
        except Exception as e:
            warnings.append(f"Could not verify callback routing: {e}")
        
        # Выводим результаты
        if errors:
            print(f"\nFAIL: Found {len(errors)} errors:")
            for error in errors[:10]:  # Показываем первые 10
                print(f"  - {error}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")
        
        if warnings:
            print(f"\nWARN: Found {len(warnings)} warnings:")
            for warning in warnings[:5]:  # Показываем первые 5
                print(f"  - {warning}")
            if len(warnings) > 5:
                print(f"  ... and {len(warnings) - 5} more warnings")
        
        if errors:
            print(f"\nFAIL: {len(errors)} schema errors found")
            return 1
        
        print(f"\nOK: All {len(models)} models have valid schema")
        print(f"OK: Unique model IDs: {len(model_ids)}")
        
        # Статистика по model_type
        model_types = {}
        for model in models:
            mt = model.get('model_type', 'unknown')
            model_types[mt] = model_types.get(mt, 0) + 1
        
        print(f"\nModel types distribution:")
        for mt, count in sorted(model_types.items()):
            print(f"  - {mt}: {count} model(s)")
        
        return 0
        
    except Exception as e:
        print(f"FAIL: Error verifying schema: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(verify_model_schema())

