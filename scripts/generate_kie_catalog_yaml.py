#!/usr/bin/env python3
"""
Генерация YAML каталога моделей KIE AI из данных pricing.
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any

# Маппинг типов моделей
TYPE_MAPPING = {
    "text-to-image": "t2i",
    "text to image": "t2i",
    "image-to-image": "i2i",
    "image to image": "i2i",
    "text-to-video": "t2v",
    "text to video": "t2v",
    "image-to-video": "i2v",
    "image to video": "i2v",
    "video-to-video": "v2v",
    "video to video": "v2v",
    "text-to-speech": "tts",
    "speech-to-text": "stt",
    "sound effect": "sfx",
    "audio isolation": "audio_isolation",
    "upscale": "upscale",
    "remove background": "bg_remove",
    "watermark remover": "watermark_remove",
    "music": "music",
    "lip sync": "lip_sync",
    "edit": "i2i",
    "remix": "i2i",
    "reframe": "i2i",
}

# Маппинг единиц измерения
UNIT_MAPPING = {
    "per image": "image",
    "per video": "video",
    "per second": "second",
    "per minute": "minute",
    "per 1000 characters": "1000_chars",
    "per request": "request",
    "per megapixel": "megapixel",
    "per removal": "removal",
    "per upscale": "upscale",
}

def detect_type(name: str, model_id: str) -> str:
    """Определяет тип модели по названию."""
    name_lower = name.lower()
    model_lower = model_id.lower()
    
    for key, value in TYPE_MAPPING.items():
        if key in name_lower or key in model_lower:
            return value
    
    # Fallback
    if "video" in name_lower:
        if "image" in name_lower:
            return "i2v"
        return "t2v"
    elif "image" in name_lower:
        if "edit" in name_lower or "remix" in name_lower:
            return "i2i"
        return "t2i"
    elif "speech" in name_lower:
        if "to text" in name_lower:
            return "stt"
        return "tts"
    elif "music" in name_lower:
        return "music"
    elif "upscale" in name_lower:
        return "upscale"
    elif "background" in name_lower:
        return "bg_remove"
    elif "watermark" in name_lower:
        return "watermark_remove"
    elif "audio" in name_lower and "isolation" in name_lower:
        return "audio_isolation"
    elif "sound" in name_lower:
        return "sfx"
    elif "avatar" in name_lower or "lip" in name_lower:
        return "lip_sync"
    
    return "t2i"  # Default

def detect_unit(name: str, mode: str, credits: float) -> str:
    """Определяет единицу измерения."""
    name_lower = name.lower()
    mode_lower = mode.lower()
    
    if "per second" in name_lower or "per second" in mode_lower or "Credits per second" in name:
        return "second"
    if "per minute" in name_lower or "per minute" in mode_lower or "Per minute" in name:
        return "minute"
    if "per 1000 characters" in name_lower or "per 1000 characters" in mode_lower:
        return "1000_chars"
    if "per megapixel" in name_lower or "per megapixel" in mode_lower:
        return "megapixel"
    if "per removal" in name_lower or "remover" in name_lower:
        return "removal"
    if "per upscale" in name_lower or "upscale" in name_lower:
        return "upscale"
    if "per request" in name_lower or "per request" in mode_lower:
        return "request"
    if "video" in name_lower or "video" in mode_lower:
        return "video"
    
    return "image"  # Default

def generate_yaml_catalog():
    """Генерирует YAML каталог из JSON данных."""
    root_dir = Path(__file__).parent.parent
    
    # Читаем JSON
    json_file = root_dir / "data" / "kie_models_complete_pricing.json"
    if not json_file.exists():
        print(f"Error: {json_file} not found")
        return
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Группируем по model_id
    models_dict = {}
    for model_id, model_data in data["models"].items():
        if model_id not in models_dict:
            models_dict[model_id] = {
                "id": model_id,
                "title_ru": model_data["name"],
                "type": detect_type(model_data["name"], model_id),
                "modes": []
            }
        
        # Добавляем режимы
        for mode_data in model_data["modes"]:
            mode_name = mode_data["mode"]
            unit = detect_unit(model_data["name"], mode_name, mode_data["credits_per_generation"])
            
            mode_info = {
                "unit": unit,
                "credits": mode_data["credits_per_generation"],
                "official_usd": mode_data["price_usd"]
            }
            
            # Добавляем notes если есть специфичные параметры
            notes_parts = []
            if mode_name != "default":
                notes_parts.append(mode_name)
            
            if notes_parts:
                mode_info["notes"] = ", ".join(notes_parts)
            
            models_dict[model_id]["modes"].append(mode_info)
    
    # Формируем YAML структуру
    yaml_data = {
        "version": "1.0",
        "source": "KIE AI Models Pricing Table",
        "last_updated": "2025-12-21",
        "models": list(models_dict.values())
    }
    
    # Сохраняем YAML
    output_file = root_dir / "app" / "kie_catalog" / "models_pricing.yaml"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"YAML catalog generated: {output_file}")
    print(f"Total models: {len(models_dict)}")
    
    # Подсчитываем общее количество режимов
    total_modes = sum(len(m["modes"]) for m in models_dict.values())
    print(f"Total modes: {total_modes}")

if __name__ == "__main__":
    generate_yaml_catalog()

