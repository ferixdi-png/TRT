#!/usr/bin/env python3
"""
Анализатор отсутствующих метаданных моделей для ONE SOURCE OF TRUTH.

Проверяет все модели на наличие необходимых метаданных:
- Названия на русском и английском
- Описания на русском и английском  
- Эмодзи
- Правильные параметры
- Корректные цены
- Статус видимости

Создает отчет о моделях с неполными метаданными.
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
from collections import defaultdict

def load_models_registry() -> Dict[str, Any]:
    """Загружает реестр моделей из models/kie_models.yaml"""
    models_path = Path("models/kie_models.yaml")
    if not models_path.exists():
        return {}
    
    with open(models_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def load_pricing_config() -> Dict[str, Any]:
    """Загружает конфиг цен из pricing/config.yaml"""
    pricing_path = Path("pricing/config.yaml")
    if not pricing_path.exists():
        return {}
    
    with open(pricing_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def load_models_pricing() -> Dict[str, Any]:
    """Загружает models_pricing.yaml"""
    pricing_path = Path("models_pricing.yaml")
    if not pricing_path.exists():
        return {}
    
    with open(pricing_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

def analyze_model_metadata() -> Dict[str, Any]:
    """Анализирует метаданные моделей."""
    
    # Загружаем все источники данных
    models_registry = load_models_registry()
    pricing_config = load_pricing_config()
    models_pricing = load_models_pricing()
    
    report = {
        "summary": {
            "total_models": 0,
            "models_with_issues": 0,
            "issues_by_type": defaultdict(int)
        },
        "issues": {
            "missing_names": [],
            "missing_descriptions": [],
            "missing_emoji": [],
            "missing_input_schema": [],
            "missing_pricing": [],
            "visibility_issues": [],
            "parameter_issues": []
        },
        "detailed_analysis": {}
    }
    
    all_model_ids = set()
    
    # Собираем все ID моделей из всех источников
    if 'models' in models_registry:
        all_model_ids.update(models_registry['models'].keys())
    
    if 'models' in pricing_config:
        all_model_ids.update(pricing_config['models'].keys())
    
    if 'models' in models_pricing:
        all_model_ids.update(models_pricing['models'].keys())
    
    report["summary"]["total_models"] = len(all_model_ids)
    
    for model_id in sorted(all_model_ids):
        model_analysis = {
            "model_id": model_id,
            "issues": [],
            "sources": {
                "kie_models": model_id in models_registry.get('models', {}),
                "pricing_config": model_id in pricing_config.get('models', {}),
                "models_pricing": model_id in models_pricing.get('models', {})
            }
        }
        
        # Анализируем данные из каждого источника
        
        # 1. Проверяем kie_models.yaml
        if model_id in models_registry.get('models', {}):
            model_data = models_registry['models'][model_id]
            
            # Проверяем названия
            name_ru = model_data.get('name_ru')
            name_en = model_data.get('name_en')
            if not name_ru:
                model_analysis["issues"].append("Отсутствует name_ru")
                report["issues"]["missing_names"].append(model_id)
                report["summary"]["issues_by_type"]["missing_names"] += 1
            if not name_en:
                model_analysis["issues"].append("Отсутствует name_en")
                if model_id not in report["issues"]["missing_names"]:
                    report["issues"]["missing_names"].append(model_id)
                    report["summary"]["issues_by_type"]["missing_names"] += 1
            
            # Проверяем описания
            desc_ru = model_data.get('description_ru')
            desc_en = model_data.get('description_en')
            if not desc_ru or len(desc_ru.strip()) < 10:
                model_analysis["issues"].append("Отсутствует или короткое description_ru")
                report["issues"]["missing_descriptions"].append(model_id)
                report["summary"]["issues_by_type"]["missing_descriptions"] += 1
            if not desc_en or len(desc_en.strip()) < 10:
                model_analysis["issues"].append("Отсутствует или короткое description_en")
                if model_id not in report["issues"]["missing_descriptions"]:
                    report["issues"]["missing_descriptions"].append(model_id)
                    report["summary"]["issues_by_type"]["missing_descriptions"] += 1
            
            # Проверяем эмодзи
            emoji = model_data.get('emoji')
            if not emoji:
                model_analysis["issues"].append("Отсутствует emoji")
                report["issues"]["missing_emoji"].append(model_id)
                report["summary"]["issues_by_type"]["missing_emoji"] += 1
            
            # Проверяем input схему
            input_schema = model_data.get('input')
            if not input_schema or not isinstance(input_schema, dict):
                model_analysis["issues"].append("Отсутствует или некорректная input схема")
                report["issues"]["missing_input_schema"].append(model_id)
                report["summary"]["issues_by_type"]["missing_input_schema"] += 1
            else:
                # Проверяем параметры в input схеме
                for param_name, param_schema in input_schema.items():
                    if not isinstance(param_schema, dict):
                        model_analysis["issues"].append(f"Некорректная схема параметра {param_name}")
                        report["issues"]["parameter_issues"].append((model_id, param_name))
                        report["summary"]["issues_by_type"]["parameter_issues"] += 1
                        continue
                    
                    if 'type' not in param_schema:
                        model_analysis["issues"].append(f"Отсутствует type для параметра {param_name}")
                        report["issues"]["parameter_issues"].append((model_id, param_name))
                        report["summary"]["issues_by_type"]["parameter_issues"] += 1
        
        # 2. Проверяем pricing/config.yaml
        if model_id in pricing_config.get('models', {}):
            pricing_data = pricing_config['models'][model_id]
            
            # Проверяем цены
            if 'price_rub' not in pricing_data:
                model_analysis["issues"].append("Отсутствует price_rub в pricing/config.yaml")
                report["issues"]["missing_pricing"].append(model_id)
                report["summary"]["issues_by_type"]["missing_pricing"] += 1
        
        # 3. Проверяем models_pricing.yaml
        if model_id in models_pricing.get('models', {}):
            mp_data = models_pricing['models'][model_id]
            
            # Проверяем видимость
            if 'hidden' in mp_data and mp_data['hidden']:
                model_analysis["issues"].append("Модель скрыта (hidden=true)")
                report["issues"]["visibility_issues"].append(model_id)
                report["summary"]["issues_by_type"]["visibility_issues"] += 1
        
        # Если есть проблемы, добавляем в отчет
        if model_analysis["issues"]:
            report["summary"]["models_with_issues"] += 1
            report["detailed_analysis"][model_id] = model_analysis
    
    return report

def print_report(report: Dict[str, Any]):
    """Выводит отчет в консоль."""
    
    print("=" * 80)
    print("ОТЧЕТ О ПРОПУЩЕННЫХ МЕТАДАННЫХ МОДЕЛЕЙ")
    print("=" * 80)
    print()
    
    # Сводка
    summary = report["summary"]
    print(f"СВОДКА:")
    print(f"   Всего моделей: {summary['total_models']}")
    print(f"   Моделей с проблемами: {summary['models_with_issues']}")
    print(f"   Проблем по типам:")
    
    for issue_type, count in summary["issues_by_type"].items():
        print(f"     - {issue_type}: {count}")
    
    print()
    
    # Детальные проблемы
    issues = report["issues"]
    
    if issues["missing_names"]:
        print(f"МОДЕЛИ БЕЗ НАЗВАНИЙ ({len(issues['missing_names'])}):")
        for model_id in sorted(issues["missing_names"]):
            print(f"   - {model_id}")
        print()
    
    if issues["missing_descriptions"]:
        print(f"МОДЕЛИ БЕЗ ОПИСАНИЙ ({len(issues['missing_descriptions'])}):")
        for model_id in sorted(issues["missing_descriptions"]):
            print(f"   - {model_id}")
        print()
    
    if issues["missing_emoji"]:
        print(f"МОДЕЛИ БЕЗ ЭМОДЗИ ({len(issues['missing_emoji'])}):")
        for model_id in sorted(issues["missing_emoji"]):
            print(f"   - {model_id}")
        print()
    
    if issues["missing_input_schema"]:
        print(f"МОДЕЛИ БЕЗ INPUT СХЕМЫ ({len(issues['missing_input_schema'])}):")
        for model_id in sorted(issues["missing_input_schema"]):
            print(f"   - {model_id}")
        print()
    
    if issues["missing_pricing"]:
        print(f"МОДЕЛИ БЕЗ ЦЕН ({len(issues['missing_pricing'])}):")
        for model_id in sorted(issues["missing_pricing"]):
            print(f"   - {model_id}")
        print()
    
    if issues["visibility_issues"]:
        print(f"СКРЫТЫЕ МОДЕЛИ ({len(issues['visibility_issues'])}):")
        for model_id in sorted(issues["visibility_issues"]):
            print(f"   - {model_id} (hidden=true)")
        print()
    
    if issues["parameter_issues"]:
        print(f"ПРОБЛЕМЫ С ПАРАМЕТРАМИ ({len(issues['parameter_issues'])}):")
        for model_id, param_name in sorted(issues["parameter_issues"]):
            print(f"   - {model_id}: {param_name}")
        print()
    
    # Рекомендации
    print("=" * 80)
    print("РЕКОМЕНДАЦИИ:")
    print("=" * 80)
    print()
    
    if summary["models_with_issues"] > 0:
        print("НЕОБХОДИМО ИСПРАВИТЬ:")
        print("   1. Добавить недостающие названия (name_ru/name_en)")
        print("   2. Написать описания (description_ru/description_en)")
        print("   3. Добавить эмодзи для лучшего UX")
        print("   4. Проверить input схемы всех моделей")
        print("   5. Убедиться что у всех моделей есть цены")
        print("   6. Проверить статус скрытых моделей")
        print()
    else:
        print("ВСЕ МОДЕЛИ ИМЕЮТ ПОЛНЫЕ МЕТАДАННЫЕ!")
        print()
    
    print("ONE SOURCE OF TRUTH:")
    print("   - models/kie_models.yaml: основной реестр моделей")
    print("   - pricing/config.yaml: цены и доступ")
    print("   - models_pricing.yaml: доп. параметры и видимость")
    print()

def main():
    """Основная функция."""
    try:
        report = analyze_model_metadata()
        print_report(report)
        
        # Сохраняем отчет в JSON
        report_path = Path("missing_metadata_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"Детальный отчет сохранен: {report_path}")
        
        # Выходной код для CI
        if report["summary"]["models_with_issues"] > 0:
            return 1
        return 0
        
    except Exception as e:
        print(f"Ошибка при анализе: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
