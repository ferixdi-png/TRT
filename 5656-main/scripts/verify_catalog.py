#!/usr/bin/env python3
"""
Проверка каталога моделей KIE AI.
Проверяет корректность данных в app/kie_catalog/models_pricing.yaml
"""

import sys
import yaml
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import Counter

# Разрешённые типы моделей
ALLOWED_TYPES = {
    't2i', 'i2i', 't2v', 'i2v', 'v2v',
    'tts', 'stt', 'sfx', 'audio_isolation',
    'upscale', 'bg_remove', 'watermark_remove',
    'music', 'lip_sync'
}

# Разрешённые единицы измерения
ALLOWED_UNITS = {
    'image', 'video', 'second', 'minute', '1000_chars',
    'request', 'megapixel', 'removal', 'upscale'
}


def load_catalog() -> Dict[str, Any]:
    """Загружает каталог из YAML."""
    root_dir = Path(__file__).parent.parent
    catalog_file = root_dir / "app" / "kie_catalog" / "models_pricing.yaml"
    
    if not catalog_file.exists():
        print(f"[ERROR] Catalog file not found: {catalog_file}")
        sys.exit(1)
    
    try:
        with open(catalog_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict) or 'models' not in data:
            print(f"[ERROR] Invalid catalog format: missing 'models' key")
            sys.exit(1)
        
        return data
    except Exception as e:
        print(f"[ERROR] Failed to load catalog: {e}")
        sys.exit(1)


def verify_catalog() -> bool:
    """
    Проверяет каталог на корректность.
    
    Returns:
        True если все проверки пройдены, False иначе
    """
    catalog = load_catalog()
    models = catalog.get('models', [])
    
    if not models:
        print("[ERROR] No models in catalog")
        return False
    
    errors = []
    warnings = []
    
    # Собираем все model_id для проверки дублей
    model_ids = []
    model_ids_counter = Counter()
    
    for i, model in enumerate(models):
        model_id = model.get('id')
        if not model_id:
            errors.append(f"Model #{i+1}: missing 'id' field")
            continue
        
        model_ids.append(model_id)
        model_ids_counter[model_id] += 1
        
        # Проверяем обязательные поля
        if not model.get('title_ru'):
            errors.append(f"Model {model_id}: missing 'title_ru' field")
        
        model_type = model.get('type')
        if not model_type:
            errors.append(f"Model {model_id}: missing 'type' field")
        elif model_type not in ALLOWED_TYPES:
            errors.append(f"Model {model_id}: invalid type '{model_type}', allowed: {ALLOWED_TYPES}")
        
        # Проверяем modes
        modes = model.get('modes', [])
        if not modes:
            warnings.append(f"Model {model_id}: no modes defined")
        else:
            for j, mode in enumerate(modes):
                # Проверяем обязательные поля режима
                if 'unit' not in mode:
                    errors.append(f"Model {model_id}, mode #{j+1}: missing 'unit' field")
                elif mode['unit'] not in ALLOWED_UNITS:
                    errors.append(f"Model {model_id}, mode #{j+1}: invalid unit '{mode['unit']}', allowed: {ALLOWED_UNITS}")
                
                if 'credits' not in mode:
                    errors.append(f"Model {model_id}, mode #{j+1}: missing 'credits' field")
                else:
                    try:
                        credits = float(mode['credits'])
                        if credits <= 0:
                            errors.append(f"Model {model_id}, mode #{j+1}: credits must be > 0, got {credits}")
                    except (ValueError, TypeError):
                        errors.append(f"Model {model_id}, mode #{j+1}: invalid credits value '{mode['credits']}'")
                
                if 'official_usd' not in mode:
                    errors.append(f"Model {model_id}, mode #{j+1}: missing 'official_usd' field")
                else:
                    try:
                        official_usd = float(mode['official_usd'])
                        if official_usd <= 0:
                            errors.append(f"Model {model_id}, mode #{j+1}: official_usd must be > 0, got {official_usd}")
                    except (ValueError, TypeError):
                        errors.append(f"Model {model_id}, mode #{j+1}: invalid official_usd value '{mode['official_usd']}'")
    
    # Проверяем дубли model_id
    duplicates = [model_id for model_id, count in model_ids_counter.items() if count > 1]
    if duplicates:
        for model_id in duplicates:
            errors.append(f"Duplicate model_id: '{model_id}' (found {model_ids_counter[model_id]} times)")
    
    # Выводим результаты
    print("=" * 60)
    print("KIE Catalog Verification")
    print("=" * 60)
    print(f"\nTotal models: {len(models)}")
    
    # Подсчитываем режимы
    total_modes = sum(len(m.get('modes', [])) for m in models)
    print(f"Total modes: {total_modes}")
    
    # Подсчитываем по типам
    type_counts = Counter(m.get('type', 'unknown') for m in models)
    print(f"\nModels by type:")
    for model_type in sorted(type_counts.keys()):
        count = type_counts[model_type]
        status = "[OK]" if model_type in ALLOWED_TYPES else "[ERROR]"
        print(f"  {status} {model_type}: {count}")
    
    # Выводим ошибки
    if errors:
        print(f"\n[ERROR] ERRORS ({len(errors)}):")
        for error in errors:
            print(f"  • {error}")
        return False
    
    # Выводим предупреждения
    if warnings:
        print(f"\n[WARN] WARNINGS ({len(warnings)}):")
        for warning in warnings:
            print(f"  • {warning}")
    
    # Всё ок
    print(f"\n[OK] Catalog verification passed!")
    print(f"   • No duplicate model_ids")
    print(f"   • All official_usd > 0")
    print(f"   • All types are valid")
    print(f"   • All required fields present")
    
    return True


if __name__ == "__main__":
    success = verify_catalog()
    sys.exit(0 if success else 1)

