#!/usr/bin/env python3
"""Convert JSON model definitions to YAML format for kie_models.yaml"""

import json
import yaml
from pathlib import Path

def convert_json_to_yaml(json_path: str, yaml_path: str):
    """Convert JSON model definitions to YAML format"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Convert to YAML format
    yaml_data = {
        'version': data.get('version', '1.0'),
        'source': data.get('source', 'repository_docs_only'),
        'models': []
    }
    
    for model in data.get('models', []):
        yaml_model = {
            'model_id': model.get('model_id'),
            'name': model.get('name', model.get('model_id')),
            'category': model.get('category', 'other'),
            'description': model.get('description', ''),
            'output_type': model.get('output_type', 'url'),
        }
        
        # Add pricing if available
        if 'price' in model:
            yaml_model['price'] = model['price']
        if 'price_usd' in model:
            yaml_model['price_usd'] = model['price_usd']
        if 'price_rub' in model:
            yaml_model['price_rub'] = model['price_rub']
        if 'is_free' in model:
            yaml_model['is_free'] = model['is_free']
        if 'is_pricing_known' in model:
            yaml_model['is_pricing_known'] = model['is_pricing_known']
        
        # Add input schema
        if 'input_schema' in model:
            yaml_model['input_schema'] = model['input_schema']
        
        # Add additional fields
        if 'use_case' in model:
            yaml_model['use_case'] = model['use_case']
        if 'example' in model:
            yaml_model['example'] = model['example']
        if 'sample_prompt' in model:
            yaml_model['sample_prompt'] = model['sample_prompt']
        
        yaml_data['models'].append(yaml_model)
    
    # Write YAML file
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"Converted {len(yaml_data['models'])} models from {json_path} to {yaml_path}")

if __name__ == '__main__':
    json_path = 'models/kie_models_source_of_truth.json.backup'
    yaml_path = 'models/kie_models.yaml'
    
    if not Path(json_path).exists():
        print(f"Error: {json_path} not found")
        exit(1)
    
    convert_json_to_yaml(json_path, yaml_path)
    print(f"Created {yaml_path}")

