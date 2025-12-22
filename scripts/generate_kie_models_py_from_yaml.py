#!/usr/bin/env python3
"""
Генерирует kie_models.py из models/kie_models.yaml

Этот скрипт позволяет автогенерировать kie_models.py из YAML для обратной совместимости
или legacy использования, но рекомендуется использовать app/models/registry.py напрямую.
"""

import sys
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List

# json импортирован наверху, используем его ниже

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Добавляем путь к models
models_dir = root_dir / "models"
yaml_path = models_dir / "kie_models.yaml"
output_path = root_dir / "kie_models.py"


def load_yaml_models() -> Dict[str, Dict[str, Any]]:
    """Загружает модели из YAML."""
    if not yaml_path.exists():
        print(f"ERROR: YAML file not found: {yaml_path}")
        sys.exit(1)
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    return data.get('models', {})


def convert_yaml_input_to_input_params(yaml_input: Dict[str, Any]) -> Dict[str, Any]:
    """Конвертирует YAML формат input в формат input_params для Python."""
    input_params = {}
    
    for param_name, param_spec in yaml_input.items():
        if not isinstance(param_spec, dict):
            continue
        
        param_type = param_spec.get('type', 'string')
        required = param_spec.get('required', False)
        
        converted_param = {
            'type': param_type,
            'required': required
        }
        
        # Добавляем description
        if 'description' in param_spec:
            converted_param['description'] = param_spec['description']
        
        # Обработка max -> max_length
        if 'max' in param_spec:
            converted_param['max_length'] = param_spec['max']
        
        # Обработка enum
        if param_type == 'enum' and 'values' in param_spec:
            converted_param['enum'] = param_spec['values']
            converted_param['type'] = 'string'
        
        # Обработка array
        if param_type == 'array':
            if 'item_type' in param_spec:
                converted_param['item_type'] = param_spec['item_type']
            else:
                converted_param['item_type'] = 'string'
        
        input_params[param_name] = converted_param
    
    return input_params


def generate_kie_models_py(yaml_models: Dict[str, Dict[str, Any]], enrich_from_kie_models: bool = True) -> str:
    """
    Генерирует код kie_models.py из YAML.
    
    Args:
        yaml_models: Модели из YAML
        enrich_from_kie_models: Если True, обогащает данными из существующего kie_models.py
    """
    # Пытаемся загрузить существующий kie_models.py для обогащения
    enrich_data = {}
    if enrich_from_kie_models and output_path.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("kie_models", output_path)
            kie_models_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(kie_models_module)
            
            if hasattr(kie_models_module, 'KIE_MODELS'):
                for model in kie_models_module.KIE_MODELS:
                    model_id = model.get('id')
                    if model_id:
                        enrich_data[model_id] = model
        except Exception as e:
            print(f"WARNING: Could not load existing kie_models.py for enrichment: {e}")
    
    lines = [
        '"""',
        'Static list of KIE AI models available in the bot',
        'AUTO-GENERATED from models/kie_models.yaml',
        'DO NOT EDIT MANUALLY - edit YAML instead and regenerate',
        '',
        'To regenerate: python scripts/generate_kie_models_py_from_yaml.py',
        '"""',
        '',
        '# Available KIE AI models with their details',
        'KIE_MODELS = [',
    ]
    
    for model_id, yaml_data in sorted(yaml_models.items()):
        model_type = yaml_data.get('model_type', 'text_to_image')
        yaml_input = yaml_data.get('input', {})
        
        # Конвертируем input в input_params
        input_params = convert_yaml_input_to_input_params(yaml_input)
        
        # Обогащаем данными из существующего kie_models.py если доступно
        enrich = enrich_data.get(model_id, {})
        
        name = enrich.get('name') or model_id.replace('/', ' ').replace('-', ' ').title()
        description = enrich.get('description') or f"Model {model_id}"
        category = enrich.get('category') or ("Видео" if 'video' in model_type else "Фото" if 'image' in model_type else "Другое")
        emoji = enrich.get('emoji') or "🤖"
        pricing = enrich.get('pricing') or ""
        
        # Формируем модель
        model_dict = {
            'id': model_id,
            'name': name,
            'description': description,
            'category': category,
            'emoji': emoji,
            'input_params': input_params
        }
        
        if pricing:
            model_dict['pricing'] = pricing
        
        # Форматируем как Python код (используем repr для правильных Python булевых)
        lines.append('    {')
        lines.append(f'        "id": {repr(model_id)},')
        lines.append(f'        "name": {repr(name)},')
        lines.append(f'        "description": {repr(description)},')
        lines.append(f'        "category": {repr(category)},')
        lines.append(f'        "emoji": {repr(emoji)},')
        if pricing:
            lines.append(f'        "pricing": {repr(pricing)},')
        # Конвертируем input_params с правильными Python булевыми
        params_json = json.dumps(input_params, indent=16, ensure_ascii=False)
        # Заменяем JSON true/false на Python True/False
        params_json = params_json.replace('true', 'True').replace('false', 'False')
        lines.append(f'        "input_params": {params_json}')
        lines.append('    },')
    
    lines.append(']')
    lines.append('')
    
    return '\n'.join(lines)


def main():
    """Главная функция."""
    print(f"Loading YAML from {yaml_path}...")
    yaml_models = load_yaml_models()
    print(f"Loaded {len(yaml_models)} models from YAML")
    
    print(f"Generating kie_models.py...")
    code = generate_kie_models_py(yaml_models, enrich_from_kie_models=True)
    
    print(f"Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)
    
    print(f"OK: Generated kie_models.py with {len(yaml_models)} models")
    print(f"WARNING: It's recommended to use app/models/registry.py directly instead of kie_models.py")


if __name__ == "__main__":
    main()

