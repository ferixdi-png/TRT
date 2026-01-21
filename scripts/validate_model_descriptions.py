#!/usr/bin/env python3
"""
Валидационный скрипт для проверки описаний моделей.
Требования:
- У каждой модели есть description_ru
- Длина <= 220 символов
- Длина >= 50 символов (чтобы не было пустых)
- Нет пафосных слов
"""

import yaml
import sys
from pathlib import Path


def validate_descriptions(yaml_path: Path) -> dict:
    """Валидирует описания всех моделей."""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    stats = {
        'total': len(data['models']),
        'valid': 0,
        'errors': [],
        'warnings': []
    }
    
    # Запрещённые слова (пафос)
    bad_words = ["лучший", "топ", "революция", "гарантия", "непревзойдённый", "идеальный"]
    
    for model in data['models']:
        model_id = model['id']
        description = model.get('description_ru', '')
        
        # Проверка наличия
        if not description:
            stats['errors'].append(f"❌ {model_id}: отсутствует description_ru")
            continue
        
        # Проверка длины
        desc_len = len(description)
        if desc_len > 220:
            stats['errors'].append(f"❌ {model_id}: длина {desc_len} > 220")
            continue
        
        if desc_len < 50:
            stats['errors'].append(f"❌ {model_id}: длина {desc_len} < 50 (слишком короткое)")
            continue
        
        # Проверка на пафос
        found_bad = []
        for word in bad_words:
            if word in description.lower():
                found_bad.append(word)
        
        if found_bad:
            stats['errors'].append(f"❌ {model_id}: пафосные слова: {', '.join(found_bad)}")
            continue
        
        # Предупреждения
        if desc_len > 200:
            stats['warnings'].append(f"⚠️  {model_id}: длина {desc_len} (близко к лимиту)")
        
        # Подсчёт эмодзи
        emoji_count = sum(1 for char in description if ord(char) > 0x1F000)
        if emoji_count > 2:
            stats['warnings'].append(f"⚠️  {model_id}: слишком много эмодзи ({emoji_count})")
        
        stats['valid'] += 1
    
    return stats


def main():
    yaml_path = Path(__file__).parent.parent / 'app' / 'kie_catalog' / 'models_pricing.yaml'
    
    if not yaml_path.exists():
        print(f"❌ Файл не найден: {yaml_path}")
        sys.exit(1)
    
    print("🔍 Валидация описаний моделей...\n")
    
    stats = validate_descriptions(yaml_path)
    
    print(f"📊 Статистика:")
    print(f"  Всего моделей: {stats['total']}")
    print(f"  ✅ Валидных: {stats['valid']}")
    print(f"  ❌ Ошибок: {len(stats['errors'])}")
    print(f"  ⚠️  Предупреждений: {len(stats['warnings'])}")
    
    if stats['errors']:
        print(f"\n❌ Найдены ошибки:")
        for error in stats['errors']:
            print(f"  {error}")
        sys.exit(1)
    
    if stats['warnings']:
        print(f"\n⚠️  Предупреждения:")
        for warning in stats['warnings']:
            print(f"  {warning}")
    
    print(f"\n✅ Все {stats['valid']} моделей прошли валидацию!")
    
    # Дополнительная статистика
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    lengths = [len(m.get('description_ru', '')) for m in data['models'] if m.get('description_ru')]
    if lengths:
        print(f"\n📏 Статистика длин описаний:")
        print(f"  Минимум: {min(lengths)} символов")
        print(f"  Максимум: {max(lengths)} символов")
        print(f"  Среднее: {sum(lengths) // len(lengths)} символов")


if __name__ == '__main__':
    main()
