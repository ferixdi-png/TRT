#!/usr/bin/env python3
"""
Тест Input Schema Parser

Проверяет корректность парсинга required/optional/enum полей
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.input_schema import (
    get_input_schema_parser,
    get_model_schema,
    validate_inputs,
    InputType,
)


def test_free_models():
    """Тест парсинга FREE моделей"""
    print("🧪 Testing Input Schema Parser")
    print("=" * 80)
    
    parser = get_input_schema_parser()
    
    # FREE модели для тестирования
    free_models = ["z-image", "qwen/text-to-image", "qwen/image-to-image", "qwen/image-edit"]
    
    for model_id in free_models:
        print(f"\n📦 {model_id}")
        print("-" * 80)
        
        schema = parser.get_schema(model_id)
        if not schema:
            print(f"  ❌ Schema not found")
            continue
        
        print(f"  Category: {schema.category}")
        print(f"  Required fields: {len(schema.required_fields)}")
        for field in schema.required_fields:
            enum_info = f" (enum: {field.enum_values})" if field.is_enum else ""
            print(f"    - {field.name}: {field.type.value}{enum_info}")
        
        print(f"  Optional fields: {len(schema.optional_fields)}")
        for field in schema.optional_fields:
            enum_info = f" (enum: {field.enum_values})" if field.is_enum else ""
            print(f"    - {field.name}: {field.type.value}{enum_info}")
        
        # Тест валидации
        print(f"  Validation test:")
        
        # Создаём минимальный valid input
        valid_inputs = {}
        for field in schema.required_fields:
            if field.name == "prompt":
                valid_inputs["prompt"] = "test image"
            elif field.name == "image" or field.name == "image_url":
                valid_inputs[field.name] = "data:image/png;base64,..."
            elif field.is_enum and field.enum_values:
                valid_inputs[field.name] = field.enum_values[0]
            elif field.type == InputType.NUMBER:
                valid_inputs[field.name] = 1.0
            elif field.type == InputType.BOOLEAN:
                valid_inputs[field.name] = True
            else:
                valid_inputs[field.name] = "test"
        
        is_valid, errors = schema.validate(valid_inputs)
        if is_valid:
            print(f"    ✅ Valid inputs accepted")
        else:
            print(f"    ❌ Validation failed: {errors}")
        
        # Тест с missing required field
        incomplete_inputs = valid_inputs.copy()
        if schema.required_fields:
            del incomplete_inputs[schema.required_fields[0].name]
            is_valid, errors = schema.validate(incomplete_inputs)
            if not is_valid:
                print(f"    ✅ Missing required field detected: {errors[0]}")
            else:
                print(f"    ❌ Should have failed validation")


def test_enum_detection():
    """Тест определения enum полей"""
    print("\n\n🎯 Enum Fields Detection")
    print("=" * 80)
    
    parser = get_input_schema_parser()
    all_schemas = parser.parse_all()
    
    # Собираем все enum поля
    enum_fields_by_name = {}
    
    for model_id, schema in all_schemas.items():
        for field in schema.enum_fields:
            if field.name not in enum_fields_by_name:
                enum_fields_by_name[field.name] = {
                    "models": [],
                    "values": set(),
                }
            
            enum_fields_by_name[field.name]["models"].append(model_id)
            if field.enum_values:
                enum_fields_by_name[field.name]["values"].update(field.enum_values)
    
    print(f"\nFound {len(enum_fields_by_name)} unique enum fields:")
    for field_name, info in sorted(enum_fields_by_name.items()):
        print(f"\n  {field_name}:")
        print(f"    Used in {len(info['models'])} models")
        if info['values']:
            values_str = ", ".join(sorted(map(str, info['values']))[:10])
            if len(info['values']) > 10:
                values_str += f"... (+{len(info['values']) - 10} more)"
            print(f"    Values: {values_str}")


def test_validation():
    """Тест функции валидации"""
    print("\n\n✅ Validation Tests")
    print("=" * 80)
    
    # Test 1: Valid inputs
    valid, errors = validate_inputs("z-image", {
        "prompt": "test image",
        "aspect_ratio": "1:1"
    })
    print(f"\nTest 1 (valid inputs): {'✅ PASS' if valid else '❌ FAIL'}")
    if errors:
        print(f"  Errors: {errors}")
    
    # Test 2: Missing required field
    valid, errors = validate_inputs("z-image", {
        "aspect_ratio": "1:1"
        # missing prompt
    })
    print(f"\nTest 2 (missing required): {'✅ PASS' if not valid else '❌ FAIL'}")
    if errors:
        print(f"  Expected error: {errors}")
    
    # Test 3: Invalid enum value
    valid, errors = validate_inputs("z-image", {
        "prompt": "test",
        "aspect_ratio": "invalid_ratio"
    })
    print(f"\nTest 3 (invalid enum): {'✅ PASS' if not valid else '❌ FAIL'}")
    if errors:
        print(f"  Expected error: {errors}")
    
    # Test 4: Unknown model
    valid, errors = validate_inputs("unknown-model", {"prompt": "test"})
    print(f"\nTest 4 (unknown model): {'✅ PASS' if not valid else '❌ FAIL'}")
    if errors:
        print(f"  Expected error: {errors}")


def main():
    """Main test runner"""
    try:
        test_free_models()
        test_enum_detection()
        test_validation()
        
        print("\n\n" + "=" * 80)
        print("✅ ALL TESTS COMPLETE")
        print("=" * 80)
        return 0
    except Exception as e:
        print(f"\n\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
