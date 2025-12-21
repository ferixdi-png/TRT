#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка всех моделей с разными входными данными и типами
"""

from kie_models import KIE_MODELS, get_generation_types, get_models_by_generation_type, get_model_by_id

def analyze_all_models():
    """Анализирует все модели и их входные параметры"""
    
    print("=" * 80)
    print("ПРОВЕРКА ВСЕХ МОДЕЛЕЙ С РАЗНЫМИ ВХОДНЫМИ ДАННЫМИ И ТИПАМИ")
    print("=" * 80)
    print()
    
    total_models = len(KIE_MODELS)
    print(f"📊 Всего моделей: {total_models}")
    print()
    
    # Анализ по типам генерации
    generation_types = get_generation_types()
    print(f"📋 Типов генерации: {len(generation_types)}")
    print()
    
    # Группировка по типам входных данных
    input_types = {
        'prompt_only': [],  # Только prompt
        'prompt_image': [],  # prompt + image_input
        'prompt_audio': [],  # prompt + audio_input
        'image_only': [],    # Только image_input
        'audio_only': [],    # Только audio_input
        'complex': []        # Множество параметров
    }
    
    # Анализ каждой модели
    for model in KIE_MODELS:
        model_id = model.get('id', 'unknown')
        input_params = model.get('input_params', {})
        
        has_prompt = 'prompt' in input_params
        has_image = 'image_input' in input_params or 'image_urls' in input_params
        has_audio = 'audio_input' in input_params or 'audio_url' in input_params
        has_aspect_ratio = 'aspect_ratio' in input_params
        has_resolution = 'resolution' in input_params
        has_duration = 'duration' in input_params
        
        param_count = len(input_params)
        
        # Классификация
        if has_prompt and not has_image and not has_audio:
            input_types['prompt_only'].append(model_id)
        elif has_prompt and has_image and not has_audio:
            input_types['prompt_image'].append(model_id)
        elif has_prompt and has_audio:
            input_types['prompt_audio'].append(model_id)
        elif has_image and not has_prompt:
            input_types['image_only'].append(model_id)
        elif has_audio and not has_prompt:
            input_types['audio_only'].append(model_id)
        else:
            input_types['complex'].append(model_id)
    
    # Вывод статистики
    print("=" * 80)
    print("СТАТИСТИКА ПО ТИПАМ ВХОДНЫХ ДАННЫХ")
    print("=" * 80)
    print()
    
    for input_type, models in input_types.items():
        if models:
            print(f"📌 {input_type}: {len(models)} моделей")
            if len(models) <= 10:
                for model_id in models:
                    print(f"   • {model_id}")
            else:
                for model_id in models[:5]:
                    print(f"   • {model_id}")
                print(f"   ... и еще {len(models) - 5} моделей")
            print()
    
    # Анализ по типам генерации
    print("=" * 80)
    print("СТАТИСТИКА ПО ТИПАМ ГЕНЕРАЦИИ")
    print("=" * 80)
    print()
    
    for gen_type in generation_types:
        models = get_models_by_generation_type(gen_type)
        if models:
            print(f"🎯 {gen_type}: {len(models)} моделей")
            print(f"   Описание: {get_models_by_generation_type.__doc__ or 'N/A'}")
            print()
    
    # Проверка уникальности моделей
    print("=" * 80)
    print("ПРОВЕРКА УНИКАЛЬНОСТИ")
    print("=" * 80)
    print()
    
    model_ids = [m.get('id') for m in KIE_MODELS]
    unique_ids = set(model_ids)
    
    if len(model_ids) == len(unique_ids):
        print("✅ Все модели имеют уникальные ID")
    else:
        duplicates = [id for id in model_ids if model_ids.count(id) > 1]
        print(f"⚠️ Найдены дубликаты: {set(duplicates)}")
    
    print()
    print(f"✅ Всего уникальных моделей: {len(unique_ids)}")
    print()
    
    # Проверка доступности через get_model_by_id
    print("=" * 80)
    print("ПРОВЕРКА ДОСТУПНОСТИ МОДЕЛЕЙ")
    print("=" * 80)
    print()
    
    not_found = []
    for model_id in model_ids[:20]:  # Проверяем первые 20
        model = get_model_by_id(model_id)
        if not model:
            not_found.append(model_id)
    
    if not_found:
        print(f"⚠️ Модели не найдены через get_model_by_id: {not_found}")
    else:
        print("✅ Все проверенные модели доступны через get_model_by_id")
    
    print()
    print("=" * 80)
    print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 80)

if __name__ == "__main__":
    analyze_all_models()




