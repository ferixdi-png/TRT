#!/usr/bin/env python3
"""
Валидатор для KIE Registry.

Проверяет:
- каждый model_id уникален
- createTask/recordInfo endpoints корректны
- input schema валидна
- для каждой модели определён output_media_type
- registry_count > 0
"""

import sys
import json
from pathlib import Path
from typing import List, Tuple

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.kie.spec_registry import load_registry


def validate_registry(registry_path: Path) -> Tuple[bool, List[str]]:
    """
    Валидирует registry.
    
    Args:
        registry_path: Путь к файлу registry
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    if not registry_path.exists():
        errors.append(f"Registry file not found: {registry_path}")
        return False, errors
    
    try:
        registry_data = json.loads(registry_path.read_text(encoding='utf-8'))
    except Exception as e:
        errors.append(f"Failed to parse registry JSON: {e}")
        return False, errors
    
    # Проверка 1: registry_count > 0
    models_count = registry_data.get("models_count", 0)
    if models_count == 0:
        errors.append("Registry is empty (models_count == 0)")
    
    models = registry_data.get("models", {})
    
    # Проверка 2: каждый model_id уникален
    model_ids = list(models.keys())
    if len(model_ids) != len(set(model_ids)):
        duplicates = [mid for mid in model_ids if model_ids.count(mid) > 1]
        errors.append(f"Duplicate model_ids found: {duplicates}")
    
    # Проверка 3: для каждой модели проверяем структуру
    for model_id, model_data in models.items():
        # Проверка endpoints
        create_endpoint = model_data.get("create_endpoint", "")
        if not create_endpoint or "createTask" not in create_endpoint:
            errors.append(f"{model_id}: Invalid create_endpoint: {create_endpoint}")
        
        record_endpoint = model_data.get("record_endpoint", "")
        if not record_endpoint or "recordInfo" not in record_endpoint:
            errors.append(f"{model_id}: Invalid record_endpoint: {record_endpoint}")
        
        # Проверка output_media_type
        output_media_type = model_data.get("output_media_type", "")
        if output_media_type not in ["media_urls", "text_object"]:
            errors.append(
                f"{model_id}: Invalid output_media_type: {output_media_type} "
                f"(must be 'media_urls' or 'text_object')"
            )
        
        # Проверка states
        states = model_data.get("states", [])
        if not states:
            errors.append(f"{model_id}: Missing states")
        else:
            required_states = {"waiting", "success", "fail"}
            if not set(states).issuperset(required_states):
                errors.append(
                    f"{model_id}: Missing required states. "
                    f"Got: {states}, required: {required_states}"
                )
        
        # Проверка input_schema
        input_schema = model_data.get("input_schema", {})
        if not isinstance(input_schema, dict):
            errors.append(f"{model_id}: input_schema must be a dict")
        else:
            for field_name, field_data in input_schema.items():
                if not isinstance(field_data, dict):
                    errors.append(f"{model_id}.{field_name}: field_data must be a dict")
                    continue
                
                # Проверка обязательных полей
                if "name" not in field_data:
                    errors.append(f"{model_id}.{field_name}: Missing 'name'")
                if "type" not in field_data:
                    errors.append(f"{model_id}.{field_name}: Missing 'type'")
                if "required" not in field_data:
                    errors.append(f"{model_id}.{field_name}: Missing 'required'")
                
                # Проверка типа
                field_type = field_data.get("type", "")
                if field_type not in ["string", "number", "boolean", "object"]:
                    errors.append(
                        f"{model_id}.{field_name}: Invalid type '{field_type}' "
                        f"(must be string/number/boolean/object)"
                    )
                
                # Проверка options (если есть)
                if "options" in field_data and field_data["options"]:
                    if not isinstance(field_data["options"], list):
                        errors.append(f"{model_id}.{field_name}: options must be a list")
    
    return len(errors) == 0, errors


def main():
    """Главная функция."""
    registry_path = project_root / "models" / "kie_registry.generated.json"
    
    print(f"Validating KIE Registry: {registry_path}")
    
    is_valid, errors = validate_registry(registry_path)
    
    if is_valid:
        # Загружаем registry для дополнительных проверок
        try:
            registry = load_registry(registry_path)
            print(f"[OK] Registry is valid")
            print(f"   Models count: {registry.count()}")
            print(f"   Sample models: {', '.join(registry.list_models()[:5])}...")
            return 0
        except Exception as e:
            print(f"[ERROR] Failed to load registry: {e}")
            return 1
    else:
        print(f"[ERROR] Registry validation failed:")
        for error in errors:
            print(f"   - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())











