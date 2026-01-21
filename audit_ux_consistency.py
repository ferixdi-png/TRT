#!/usr/bin/env python3
"""
Комплексный аудит UX согласованности всех моделей.
Проверяет:
- Наличие описаний
- Наличие цен
- Наличие обязательных параметров
- Наличие меню кнопок
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.kie_catalog import load_catalog
from app.pricing.price_ssot import list_model_skus, PRICING_SSOT_PATH


def main():
    print("=" * 80)
    print("АУДИТ UX СОГЛАСОВАННОСТИ ВСЕХ МОДЕЛЕЙ")
    print("=" * 80)
    print()
    
    # Загружаем каталог
    models = load_catalog()
    print(f"✅ Загружено моделей: {len(models)}")
    print()
    
    # Проверяем каждую модель
    issues = []
    
    for model in sorted(models, key=lambda m: m.id):
        print(f"🔍 Проверка: {model.id}")
        
        # 1. Проверяем описание
        if not model.description_ru or model.description_ru.strip() == "":
            issues.append(f"  ❌ {model.id}: Описание не заполнено")
            print(f"   ❌ Описание не заполнено")
        elif len(model.description_ru) < 20:
            issues.append(f"  ⚠️ {model.id}: Описание слишком короткое ({len(model.description_ru)} символов)")
            print(f"   ⚠️ Описание слишком короткое ({len(model.description_ru)} символов): {model.description_ru}")
        else:
            print(f"   ✅ Описание ({len(model.description_ru)} символов): {model.description_ru[:60]}...")
        
        # 2. Проверяем цены
        skus = list_model_skus(model.id)
        if not skus:
            issues.append(f"  ❌ {model.id}: Цены не найдены в {PRICING_SSOT_PATH}")
            print(f"   ❌ Цены не найдены")
        else:
            print(f"   ✅ Цены найдены: {len(skus)} SKU")
            # Показываем диапазон цен
            prices = [float(sku.price_rub) for sku in skus]
            min_price = min(prices)
            max_price = max(prices)
            print(f"      Диапазон: от {min_price:.2f} до {max_price:.2f} ₽")
        
        # 3. Проверяем обязательные параметры
        if not model.required_inputs_ru:
            print(f"   ⚠️ Обязательные параметры не определены")
        else:
            print(f"   ✅ Обязательные параметры: {', '.join(model.required_inputs_ru)}")
        
        # 4. Проверяем режимы
        if not model.modes:
            issues.append(f"  ❌ {model.id}: Режимы не найдены")
            print(f"   ❌ Режимы не найдены")
        else:
            print(f"   ✅ Режимы: {len(model.modes)}")
        
        # 5. Проверяем тип модели
        print(f"   ℹ️ Тип: {model.type}, Выход: {model.output_type_ru}")
        
        print()
    
    # Выводим итоги
    print("=" * 80)
    print("ИТОГИ")
    print("=" * 80)
    print(f"✅ Всего моделей проверено: {len(models)}")
    
    if issues:
        print(f"❌ Найдено проблем: {len(issues)}")
        print()
        for issue in issues:
            print(issue)
    else:
        print("✅ Проблем не найдено! UX согласован!")
    
    print()
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
