#!/usr/bin/env python3
"""
Test all 72 models to verify payload building works correctly.
This script tests the critical fix for wrapped input schema handling.
"""

import json
import sys
from pathlib import Path
from app.kie.router import build_category_payload

def load_source_of_truth():
    """Load models from SOURCE_OF_TRUTH.json"""
    source_path = Path(__file__).parent / "models" / "KIE_SOURCE_OF_TRUTH.json"
    with open(source_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_model_payload(model_id: str, source_v4: dict) -> dict:
    """
    Test payload building for a single model.
    
    Returns:
        {
            'success': bool,
            'model_id': str,
            'schema_type': 'wrapped' | 'direct',
            'user_fields': list,
            'payload_keys': list,
            'error': str (if any)
        }
    """
    try:
        # Get model schema
        models = source_v4.get('models', {})
        if isinstance(models, dict):
            model_schema = models.get(model_id)
        else:
            model_schema = next((m for m in models if m.get('model_id') == model_id), None)
        
        if not model_schema:
            return {
                'success': False,
                'model_id': model_id,
                'error': 'Model not found in SOURCE_OF_TRUTH'
            }
        
        input_schema = model_schema.get('input_schema', {})
        
        # CRITICAL: input_schema in SOURCE_OF_TRUTH is PROPERTIES DIRECTLY
        if 'properties' in input_schema and isinstance(input_schema['properties'], dict):
            # Nested format
            properties = input_schema.get('properties', {})
        else:
            # Flat format - input_schema IS properties
            properties = input_schema
        
        # Detect schema type and extract user fields
        schema_type = 'direct'
        user_fields = []
        system_fields = {'model', 'callBackUrl', 'webhookUrl'}
        
        if 'input' in properties and isinstance(properties['input'], dict):
            input_field_spec = properties['input']
            if 'examples' in input_field_spec and isinstance(input_field_spec['examples'], list):
                examples = input_field_spec['examples']
                if examples and isinstance(examples[0], dict):
                    schema_type = 'wrapped'
                    user_fields = [k for k in examples[0].keys()]
        
        if not user_fields:
            # Direct format - extract from properties
            user_fields = [k for k in properties.keys() if k not in system_fields and k != 'input']
        
        # Build test payload
        test_inputs = {}
        for field in user_fields[:3]:  # Test with first 3 fields
            if field == 'prompt':
                test_inputs['prompt'] = 'Test prompt'
            elif field == 'aspect_ratio':
                test_inputs['aspect_ratio'] = '1:1'
            elif field == 'url':
                test_inputs['url'] = 'https://placehold.co/1024x1024/png'
            elif field == 'image':
                test_inputs['image'] = 'base64image'
        
        # Build payload
        payload = build_category_payload(model_id, test_inputs, source_v4)
        
        # Count payload content
        payload_keys = list(payload.keys())
        input_content_count = 0
        if 'input' in payload and isinstance(payload['input'], dict):
            input_content_count = len(payload['input'])
            payload_keys.extend([f"input.{k}" for k in payload['input'].keys()])
        
        has_user_inputs = input_content_count > 0 or any(k for k in payload_keys if k not in ['model', 'callBackUrl'])
        
        return {
            'success': True,
            'model_id': model_id,
            'schema_type': schema_type,
            'user_fields': user_fields,
            'payload_keys': payload_keys,
            'has_user_inputs': has_user_inputs
        }
    
    except Exception as e:
        return {
            'success': False,
            'model_id': model_id,
            'error': str(e)
        }

def main():
    """Test all models"""
    source_v4 = load_source_of_truth()
    models = source_v4.get('models', {})
    
    # Get list of model IDs
    if isinstance(models, dict):
        model_ids = list(models.keys())
    else:
        model_ids = [m.get('model_id') for m in models]
    
    print(f"🔍 Testing payload building for {len(model_ids)} models...")
    print()
    
    # Group by schema type
    wrapped_models = []
    direct_models = []
    failed_models = []
    
    for model_id in sorted(model_ids):
        result = test_model_payload(model_id, source_v4)
        
        if not result['success']:
            failed_models.append(result)
            print(f"❌ {model_id}: {result.get('error', 'Unknown error')}")
        else:
            schema_type = result['schema_type']
            has_inputs = result['has_user_inputs']
            
            if schema_type == 'wrapped':
                wrapped_models.append(result)
                status = '✅' if has_inputs else '⚠️'
                print(f"{status} {model_id:30} | WRAPPED | fields: {result['user_fields']}")
            else:
                direct_models.append(result)
                status = '✅' if has_inputs else '⚠️'
                print(f"{status} {model_id:30} | DIRECT  | fields: {result['user_fields']}")
    
    # Summary
    print()
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total models:       {len(model_ids)}")
    print(f"Wrapped format:     {len(wrapped_models)} models")
    print(f"Direct format:      {len(direct_models)} models")
    print(f"Failed:             {len(failed_models)} models")
    print()
    
    if failed_models:
        print("⚠️ FAILED MODELS:")
        for model in failed_models:
            print(f"  - {model['model_id']}: {model.get('error')}")
        print()
    
    # Check if all have user inputs
    no_inputs = [m for m in wrapped_models + direct_models if not m.get('has_user_inputs')]
    if no_inputs:
        print(f"⚠️ WARNING: {len(no_inputs)} models have no user inputs in payload!")
        for model in no_inputs:
            print(f"  - {model['model_id']}")
    else:
        print("✅ All models correctly include user inputs in payload!")
    
    print()
    
    # Wrapped models examples
    if wrapped_models:
        print("📌 WRAPPED FORMAT MODELS (with input: {...}):")
        for model in wrapped_models[:5]:  # Show first 5
            print(f"  - {model['model_id']}: {model['user_fields']}")
        if len(wrapped_models) > 5:
            print(f"  ... and {len(wrapped_models) - 5} more")
    
    # Direct models examples  
    if direct_models:
        print()
        print("📌 DIRECT FORMAT MODELS:")
        for model in direct_models[:5]:  # Show first 5
            print(f"  - {model['model_id']}: {model['user_fields']}")
        if len(direct_models) > 5:
            print(f"  ... and {len(direct_models) - 5} more")
    
    print()
    return 0 if len(failed_models) == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
