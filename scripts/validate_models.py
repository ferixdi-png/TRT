#!/usr/bin/env python3
"""
Скрипт для валидации моделей согласно инвариантам проекта.

Использование:
    python scripts/validate_models.py

Выводит:
- Общее количество моделей
- Количество валидных моделей
- Список невалидных моделей с ошибками
- Отчет о недостающих полях
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.models.validator import ModelValidator


def main():
    print("Model Validation Report")
    print("=" * 50)
    
    validator = ModelValidator()
    result = validator.validate_all_models()
    
    if 'error' in result:
        print(f"Error: {result['error']}")
        return 1
    
    total = result['total_models']
    valid = len(result['valid_models'])
    invalid = len(result['invalid_models'])
    
    print(f"Total models: {total}")
    print(f"Valid models: {valid}")
    print(f"Invalid models: {invalid}")
    print(f"Validity rate: {valid/total*100:.1f}%")
    print()
    
    if invalid > 0:
        print("Invalid Models:")
        print("-" * 30)
        
        for model_info in result['invalid_models']:
            model_id = model_info['model_id']
            errors = model_info['errors']
            print(f"\n{model_id}")
            for error in errors:
                print(f"   • {error}")
        
        print("\n" + "=" * 50)
        print("Missing Fields Report:")
        print("=" * 50)
        print(validator.get_missing_fields_report())
        
        # Сохраняем отчет в файл
        report_path = project_root / "models_validation_report.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(validator.get_missing_fields_report())
        print(f"\nReport saved to: {report_path}")
        
        return 1
    else:
        print("All models are valid!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
