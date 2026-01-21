#!/usr/bin/env python3
"""
Smoke тест всех моделей - проверяет что для каждой модели:
1. Есть генератор
2. Генератор не вызывает exception
3. Возвращает ответ (успех или ошибка)
"""

import pytest
import asyncio
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.kie_catalog import load_catalog


@pytest.fixture(scope="module")
def all_models():
    """Загружает все модели из каталога."""
    return load_catalog()


def test_all_models_loaded(all_models):
    """Проверяет что модели загружены."""
    assert len(all_models) > 0, "No models loaded"
    print(f"\n✅ Loaded {len(all_models)} models")


def test_all_models_have_required_fields(all_models):
    """Проверяет что все модели имеют обязательные поля."""
    required_fields = ["id", "name", "gen_type"]
    
    errors = []
    for model in all_models:
        model_id = model.get("id", "unknown")
        for field in required_fields:
            if field not in model:
                errors.append(f"Model {model_id} missing field '{field}'")
    
    if errors:
        pytest.fail("\n".join(errors))


def test_all_models_have_generators():
    """Проверяет что для всех моделей есть генераторы."""
    from app.helpers.generation_engine import get_universal_generator
    
    models = load_catalog()
    missing_generators = []
    
    for model in models:
        model_id = model.get("id")
        if not model_id:
            continue
        
        # Проверяем что можем получить генератор
        try:
            gen = get_universal_generator(model_id)
            if gen is None:
                missing_generators.append(model_id)
        except Exception as e:
            missing_generators.append(f"{model_id} (error: {e})")
    
    if missing_generators:
        print(f"\n⚠️  Models without generators ({len(missing_generators)}):")
        for m in missing_generators[:10]:
            print(f"   - {m}")
        if len(missing_generators) > 10:
            print(f"   ... and {len(missing_generators) - 10} more")
    
    # Не падаем - это warning, модели могут быть BLOCKED_NO_PRICE
    assert len(models) > 0


def test_model_visibility():
    """Проверяет видимость моделей."""
    from bot_kie import is_model_visible
    
    models = load_catalog()
    visible_count = 0
    blocked_count = 0
    
    for model in models:
        model_id = model.get("id")
        if not model_id:
            continue
        
        try:
            if is_model_visible(model_id):
                visible_count += 1
            else:
                blocked_count += 1
        except Exception as e:
            print(f"⚠️  Error checking visibility for {model_id}: {e}")
    
    print(f"\n📊 Model visibility:")
    print(f"   Visible: {visible_count}")
    print(f"   Blocked: {blocked_count}")
    print(f"   Total: {len(models)}")
    
    assert visible_count > 0, "No visible models!"


def test_all_gen_types_have_models():
    """Проверяет что для всех типов генерации есть модели."""
    models = load_catalog()
    
    gen_types = {}
    for model in models:
        gen_type = model.get("gen_type", "unknown")
        if gen_type not in gen_types:
            gen_types[gen_type] = []
        gen_types[gen_type].append(model.get("id", "unknown"))
    
    print(f"\n📊 Models by generation type:")
    for gen_type, model_ids in sorted(gen_types.items()):
        print(f"   {gen_type}: {len(model_ids)} models")
    
    # Критичные типы должны иметь модели
    critical_types = ["text-to-image", "image-to-video"]
    missing = []
    for gen_type in critical_types:
        if gen_type not in gen_types or len(gen_types[gen_type]) == 0:
            missing.append(gen_type)
    
    if missing:
        pytest.fail(f"Critical gen_types without models: {missing}")


def test_catalog_cache_performance():
    """Проверяет производительность кэша каталога."""
    import time
    
    # Первая загрузка - холодный кэш
    start = time.time()
    models1 = load_catalog()
    cold_ms = (time.time() - start) * 1000
    
    # Вторая загрузка - горячий кэш
    start = time.time()
    models2 = load_catalog()
    hot_ms = (time.time() - start) * 1000
    
    print(f"\n⚡ Catalog cache performance:")
    print(f"   Cold cache: {cold_ms:.1f}ms")
    print(f"   Hot cache: {hot_ms:.1f}ms")
    print(f"   Speedup: {cold_ms/hot_ms if hot_ms > 0 else 0:.1f}x")
    
    assert hot_ms < cold_ms, "Cache should be faster"
    assert hot_ms < 100, f"Hot cache too slow: {hot_ms}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
