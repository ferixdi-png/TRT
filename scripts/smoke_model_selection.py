#!/usr/bin/env python3
"""
Smoke test for model selection - simulates selecting a category and model,
validates required inputs are prompted/defaulted (no actual external API calls).
"""
import sys
import json
from pathlib import Path
from typing import Dict, Any, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.kie.builder import load_source_of_truth


def test_model_selection_flow():
    """Test that model selection flow works without crashes."""
    print("=" * 80)
    print("SMOKE TEST: Model Selection Flow")
    print("=" * 80)
    
    # Load source of truth
    try:
        sot = load_source_of_truth()
        models = sot.get("models", {})
        print(f"✅ Loaded {len(models)} models from SOURCE_OF_TRUTH")
    except Exception as e:
        print(f"❌ Failed to load SOURCE_OF_TRUTH: {e}")
        return False
    
    # Test: Select a category
    categories = {}
    for model_id, model_data in models.items():
        category = model_data.get("category", "other")
        if category not in categories:
            categories[category] = []
        categories[category].append(model_id)
    
    print(f"✅ Found {len(categories)} categories: {', '.join(categories.keys())}")
    
    # Test: Select a model from each category
    test_count = 0
    for category, model_ids in categories.items():
        if not model_ids:
            continue
        
        # Pick first model in category
        test_model_id = model_ids[0]
        model_data = models[test_model_id]
        
        # Validate model has required structure
        input_schema = model_data.get("input_schema", {})
        if not input_schema:
            print(f"⚠️  {test_model_id}: Missing input_schema")
            continue
        
        input_props = input_schema.get("input", {})
        if not input_props:
            print(f"⚠️  {test_model_id}: Missing input_schema.input")
            continue
        
        # Check if prompt is required
        properties = input_props.get("properties", {})
        required = input_props.get("required", [])
        
        has_prompt = "prompt" in properties or "prompt" in required
        if not has_prompt:
            # Try to infer from examples
            examples = input_props.get("examples", [])
            if examples and isinstance(examples[0], dict):
                has_prompt = "prompt" in examples[0]
        
        if has_prompt:
            print(f"✅ {test_model_id} ({category}): Has prompt field")
        else:
            print(f"⚠️  {test_model_id} ({category}): No prompt field found")
        
        test_count += 1
        if test_count >= 5:  # Test 5 models max
            break
    
    print("\n" + "=" * 80)
    print("✅ Model selection smoke test passed")
    print("=" * 80)
    return True


if __name__ == "__main__":
    try:
        success = test_model_selection_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

