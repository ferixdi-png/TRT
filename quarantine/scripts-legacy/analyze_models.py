"""
Анализ моделей KIE AI из SOURCE_OF_TRUTH
Проверка данных без вызовов API
"""
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

def load_source_of_truth() -> Dict:
    """Загружает KIE_SOURCE_OF_TRUTH.json"""
    path = Path("models/KIE_SOURCE_OF_TRUTH.json")
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_models(data: Dict) -> None:
    """Анализирует модели и выводит статистику"""
    
    models = data.get('models', {})
    
    print("="*80)
    print("🎯 АНАЛИЗ МОДЕЛЕЙ KIE AI")
    print(f"Версия: {data.get('version', 'N/A')}")
    print(f"Обновлено: {data.get('updated_at', 'N/A')}")
    print("="*80)
    print()
    
    # Статистика по категориям
    by_category = defaultdict(list)
    by_provider = defaultdict(list)
    free_models = []
    paid_models = []
    
    for model_id, model_data in models.items():
        category = model_data.get('category', 'unknown')
        provider = model_data.get('provider', 'unknown')
        pricing = model_data.get('pricing', {})
        
        by_category[category].append(model_id)
        by_provider[provider].append(model_id)
        
        if pricing.get('is_free') or pricing.get('rub_per_gen', 1) == 0:
            free_models.append({
                'id': model_id,
                'name': model_data.get('display_name', model_id),
                'category': category,
                'description': model_data.get('description', '')[:100]
            })
        else:
            paid_models.append({
                'id': model_id,
                'name': model_data.get('display_name', model_id),
                'price': pricing.get('rub_per_gen', 0),
                'category': category
            })
    
    # Общая статистика
    print(f"📊 ОБЩАЯ СТАТИСТИКА")
    print(f"{'─'*80}")
    print(f"Всего моделей: {len(models)}")
    print(f"Бесплатных моделей: {len(free_models)}")
    print(f"Платных моделей: {len(paid_models)}")
    print()
    
    # По категориям
    print(f"📁 ПО КАТЕГОРИЯМ")
    print(f"{'─'*80}")
    for category in sorted(by_category.keys()):
        count = len(by_category[category])
        print(f"  {category:20} {count:3} моделей")
    print()
    
    # По провайдерам
    print(f"🏢 ПО ПРОВАЙДЕРАМ (топ 10)")
    print(f"{'─'*80}")
    sorted_providers = sorted(by_provider.items(), key=lambda x: len(x[1]), reverse=True)
    for provider, model_list in sorted_providers[:10]:
        count = len(model_list)
        print(f"  {provider:25} {count:3} моделей")
    print()
    
    # Бесплатные модели
    print(f"🆓 БЕСПЛАТНЫЕ МОДЕЛИ ({len(free_models)})")
    print(f"{'─'*80}")
    for model in free_models:
        print(f"\n✅ {model['id']}")
        print(f"   Название: {model['name']}")
        print(f"   Категория: {model['category']}")
        print(f"   Описание: {model['description']}")
    print()
    
    # Самые дешевые платные модели
    print(f"💰 САМЫЕ ДЕШЕВЫЕ ПЛАТНЫЕ МОДЕЛИ (топ 10)")
    print(f"{'─'*80}")
    sorted_paid = sorted(paid_models, key=lambda x: x['price'])
    for model in sorted_paid[:10]:
        print(f"  {model['price']:6.2f}₽  {model['id']:40} [{model['category']}]")
    print()
    
    # Проверка структуры данных
    print(f"🔍 ПРОВЕРКА СТРУКТУРЫ ДАННЫХ")
    print(f"{'─'*80}")
    
    issues = []
    for model_id, model_data in models.items():
        # Проверяем обязательные поля
        required_fields = ['model_id', 'category', 'pricing', 'input_schema']
        missing = [f for f in required_fields if f not in model_data]
        
        if missing:
            issues.append(f"❌ {model_id}: отсутствуют поля {missing}")
        
        # Проверяем pricing
        pricing = model_data.get('pricing', {})
        if 'rub_per_gen' not in pricing and not pricing.get('is_free'):
            issues.append(f"⚠️  {model_id}: нет информации о цене")
        
        # Проверяем input_schema
        schema = model_data.get('input_schema', {})
        if not schema:
            issues.append(f"⚠️  {model_id}: пустая input_schema")
    
    if issues:
        print(f"Найдено {len(issues)} проблем:")
        for issue in issues[:20]:  # Первые 20
            print(f"  {issue}")
        if len(issues) > 20:
            print(f"  ... и еще {len(issues) - 20} проблем")
    else:
        print("✅ Все модели имеют корректную структуру!")
    
    print()
    print("="*80)
    print("✅ Анализ завершен")
    print("="*80)


def main():
    try:
        data = load_source_of_truth()
        analyze_models(data)
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
