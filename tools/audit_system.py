#!/usr/bin/env python3
"""
Системный аудит TRT - проверка соответствия SOURCE_OF_TRUTH с реальной системой
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict

# Путь к корню проекта
PROJECT_ROOT = Path(__file__).parent.parent
SOURCE_OF_TRUTH = PROJECT_ROOT / "models" / "KIE_SOURCE_OF_TRUTH.json"


def load_source_of_truth() -> Dict[str, Any]:
    """Загрузить SOURCE_OF_TRUTH"""
    with open(SOURCE_OF_TRUTH) as f:
        return json.load(f)


def analyze_models(data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ моделей из SOURCE_OF_TRUTH"""
    models = data.get("models", {})
    
    analysis = {
        "total_models": len(models),
        "categories": defaultdict(list),
        "free_models": [],
        "paid_models": [],
        "models_by_provider": defaultdict(list),
        "input_patterns": defaultdict(set),
        "required_inputs_by_model": {},
        "optional_inputs_by_model": {},
    }
    
    for model_id, model_data in models.items():
        # Категория
        category = model_data.get("category", "unknown")
        analysis["categories"][category].append(model_id)
        
        # Провайдер
        provider = model_data.get("provider", "unknown")
        analysis["models_by_provider"][provider].append(model_id)
        
        # FREE vs PAID
        pricing = model_data.get("pricing", {})
        if pricing.get("is_free"):
            analysis["free_models"].append(model_id)
        else:
            analysis["paid_models"].append(model_id)
        
        # Анализ input schema
        input_schema = model_data.get("input_schema", {}).get("input", {})
        examples = input_schema.get("examples", [])
        
        if examples and isinstance(examples, list) and len(examples) > 0:
            example = examples[0]
            if isinstance(example, dict):
                required_inputs = []
                optional_inputs = []
                
                for key, value in example.items():
                    # Определяем обязательные поля (присутствуют во всех примерах)
                    is_required = all(
                        key in ex for ex in examples if isinstance(ex, dict)
                    )
                    
                    if is_required:
                        required_inputs.append(key)
                    else:
                        optional_inputs.append(key)
                    
                    analysis["input_patterns"][key].add(model_id)
                
                analysis["required_inputs_by_model"][model_id] = required_inputs
                analysis["optional_inputs_by_model"][model_id] = optional_inputs
    
    # Преобразуем sets в lists для JSON
    analysis["input_patterns"] = {
        k: list(v) for k, v in analysis["input_patterns"].items()
    }
    
    return analysis


def check_ui_coverage() -> Dict[str, Any]:
    """Проверка покрытия UI (какие модели доступны в боте)"""
    # Ищем модели в handlers
    ui_models = set()
    
    # Проверяем bot/keyboards.py и handlers
    keyboards_file = PROJECT_ROOT / "bot" / "keyboards.py"
    if keyboards_file.exists():
        content = keyboards_file.read_text()
        # Ищем упоминания моделей (простейшая эвристика)
        # TODO: более точный парсинг
    
    return {
        "ui_models": list(ui_models),
        "coverage": "TODO: implement UI parsing"
    }


def generate_report(analysis: Dict[str, Any]) -> str:
    """Генерация отчёта"""
    report = []
    report.append("=" * 80)
    report.append("TRT SYSTEM AUDIT REPORT")
    report.append("=" * 80)
    report.append("")
    
    # Общая статистика
    report.append("📊 ОБЩАЯ СТАТИСТИКА")
    report.append(f"Всего моделей: {analysis['total_models']}")
    report.append(f"Бесплатных: {len(analysis['free_models'])}")
    report.append(f"Платных: {len(analysis['paid_models'])}")
    report.append("")
    
    # Категории
    report.append("📁 КАТЕГОРИИ")
    for category, models in sorted(analysis["categories"].items()):
        report.append(f"  {category}: {len(models)} моделей")
    report.append("")
    
    # FREE модели (критично для E2E)
    report.append("🆓 FREE МОДЕЛИ (для E2E тестирования)")
    for model_id in sorted(analysis["free_models"]):
        required = analysis["required_inputs_by_model"].get(model_id, [])
        report.append(f"  ✓ {model_id}")
        report.append(f"    Required inputs: {', '.join(required) if required else 'NONE'}")
    report.append("")
    
    # Топ-10 самых популярных input полей
    report.append("🔧 ПОПУЛЯРНЫЕ INPUT ПОЛЯ")
    input_counts = {
        k: len(v) for k, v in analysis["input_patterns"].items()
    }
    for field, count in sorted(input_counts.items(), key=lambda x: -x[1])[:10]:
        report.append(f"  {field}: используется в {count} моделях")
    report.append("")
    
    # Провайдеры
    report.append("🏢 ПРОВАЙДЕРЫ")
    for provider, models in sorted(analysis["models_by_provider"].items()):
        report.append(f"  {provider}: {len(models)} моделей")
    report.append("")
    
    report.append("=" * 80)
    return "\n".join(report)


def main():
    """Главная функция"""
    print("Загрузка SOURCE_OF_TRUTH...")
    data = load_source_of_truth()
    
    print("Анализ моделей...")
    analysis = analyze_models(data)
    
    print("Проверка UI покрытия...")
    ui_coverage = check_ui_coverage()
    
    # Объединяем результаты
    analysis.update(ui_coverage)
    
    # Генерируем отчёт
    report = generate_report(analysis)
    print(report)
    
    # Сохраняем JSON для дальнейшего использования
    audit_result = PROJECT_ROOT / "AUDIT_RESULT.json"
    with open(audit_result, "w") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Результаты сохранены в {audit_result}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
