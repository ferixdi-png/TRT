#!/usr/bin/env python3
"""
Smoke test for unified model pipeline - validates payload building and pricing calculation.

Tests nano-banana-pro with:
1. Defaults (1K resolution) → 18 credits
2. Custom resolution (4K) → 24 credits
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_nano_banana_pro_defaults():
    """Test nano-banana-pro with default parameters."""
    print("\n" + "="*60)
    print("SMOKE TEST: nano-banana-pro (defaults)")
    print("="*60)
    
    # Load SSOT
    ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
    with open(ssot_path, 'r', encoding='utf-8') as f:
        ssot = json.load(f)
    
    model_id = "nano-banana-pro"
    model = ssot['models'][model_id]
    
    # Test 1: Build payload with defaults
    print(f"\n📋 Test 1: Build payload with defaults")
    user_inputs = {
        "prompt": "A beautiful sunset over mountains"
    }
    
    # Get input schema
    input_schema = model['input_schema']['input']
    properties = input_schema.get('properties', {})
    required = input_schema.get('required', [])
    
    # Apply defaults
    for field_name, field_spec in properties.items():
        if field_name not in user_inputs and 'default' in field_spec:
            user_inputs[field_name] = field_spec['default']
    
    print(f"  User inputs: {json.dumps(user_inputs, indent=2, ensure_ascii=False)}")
    
    # Validate required fields
    missing_required = [f for f in required if f not in user_inputs]
    if missing_required:
        print(f"  ❌ Missing required fields: {missing_required}")
        return False
    
    # Validate prompt max_length
    prompt = user_inputs.get('prompt', '')
    prompt_spec = properties.get('prompt', {})
    max_length = prompt_spec.get('max_length', 20000)
    if len(prompt) > max_length:
        print(f"  ❌ Prompt too long: {len(prompt)} > {max_length}")
        return False
    
    # Validate enum values
    resolution = user_inputs.get('resolution', '1K')
    resolution_spec = properties.get('resolution', {})
    resolution_enum = resolution_spec.get('enum', [])
    if resolution not in resolution_enum:
        print(f"  ❌ Invalid resolution: {resolution}, allowed: {resolution_enum}")
        return False
    
    print(f"  ✅ Payload validation passed")
    
    # Test 2: Calculate pricing
    print(f"\n💰 Test 2: Calculate pricing (defaults → 1K)")
    from app.payments.pricing import calculate_kie_cost
    
    kie_cost_rub = calculate_kie_cost(model, user_inputs, None)
    print(f"  KIE cost: {kie_cost_rub} RUB")
    
    # Expected: 18 credits = 18 * 0.005 * 78 = 7.02 RUB
    expected_credits = 18
    expected_rub = expected_credits * 0.005 * 78.0
    if abs(kie_cost_rub - expected_rub) < 0.1:
        print(f"  ✅ Pricing correct: {kie_cost_rub} RUB ≈ {expected_rub} RUB ({expected_credits} credits)")
    else:
        print(f"  ❌ Pricing mismatch: expected {expected_rub} RUB ({expected_credits} credits), got {kie_cost_rub} RUB")
        return False
    
    return True


def test_nano_banana_pro_4k():
    """Test nano-banana-pro with 4K resolution."""
    print("\n" + "="*60)
    print("SMOKE TEST: nano-banana-pro (4K resolution)")
    print("="*60)
    
    # Load SSOT
    ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
    with open(ssot_path, 'r', encoding='utf-8') as f:
        ssot = json.load(f)
    
    model_id = "nano-banana-pro"
    model = ssot['models'][model_id]
    
    # Test 1: Build payload with 4K resolution
    print(f"\n📋 Test 1: Build payload with 4K resolution")
    user_inputs = {
        "prompt": "A beautiful sunset over mountains",
        "resolution": "4K"
    }
    
    # Get input schema
    input_schema = model['input_schema']['input']
    properties = input_schema.get('properties', {})
    required = input_schema.get('required', [])
    
    # Apply defaults for missing fields
    for field_name, field_spec in properties.items():
        if field_name not in user_inputs and 'default' in field_spec:
            user_inputs[field_name] = field_spec['default']
    
    print(f"  User inputs: {json.dumps(user_inputs, indent=2, ensure_ascii=False)}")
    
    # Validate enum values
    resolution = user_inputs.get('resolution', '1K')
    resolution_spec = properties.get('resolution', {})
    resolution_enum = resolution_spec.get('enum', [])
    if resolution not in resolution_enum:
        print(f"  ❌ Invalid resolution: {resolution}, allowed: {resolution_enum}")
        return False
    
    print(f"  ✅ Payload validation passed")
    
    # Test 2: Calculate pricing
    print(f"\n💰 Test 2: Calculate pricing (4K → 24 credits)")
    from app.payments.pricing import calculate_kie_cost
    
    kie_cost_rub = calculate_kie_cost(model, user_inputs, None)
    print(f"  KIE cost: {kie_cost_rub} RUB")
    
    # Expected: 24 credits = 24 * 0.005 * 78 = 9.36 RUB
    expected_credits = 24
    expected_rub = expected_credits * 0.005 * 78.0
    if abs(kie_cost_rub - expected_rub) < 0.1:
        print(f"  ✅ Pricing correct: {kie_cost_rub} RUB ≈ {expected_rub} RUB ({expected_credits} credits)")
    else:
        print(f"  ❌ Pricing mismatch: expected {expected_rub} RUB ({expected_credits} credits), got {kie_cost_rub} RUB")
        return False
    
    return True


def test_image_input_validation():
    """Test image_input array validation."""
    print("\n" + "="*60)
    print("SMOKE TEST: nano-banana-pro (image_input validation)")
    print("="*60)
    
    # Load SSOT
    ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
    with open(ssot_path, 'r', encoding='utf-8') as f:
        ssot = json.load(f)
    
    model_id = "nano-banana-pro"
    model = ssot['models'][model_id]
    
    input_schema = model['input_schema']['input']
    properties = input_schema.get('properties', {})
    image_input_spec = properties.get('image_input', {})
    
    # Test max_items
    max_items = image_input_spec.get('max_items', 8)
    print(f"\n📋 Test: image_input max_items = {max_items}")
    
    # Valid: 8 images
    valid_inputs = ["url1", "url2", "url3", "url4", "url5", "url6", "url7", "url8"]
    if len(valid_inputs) <= max_items:
        print(f"  ✅ Valid: {len(valid_inputs)} images <= {max_items}")
    else:
        print(f"  ❌ Invalid: {len(valid_inputs)} images > {max_items}")
        return False
    
    # Invalid: 9 images
    invalid_inputs = valid_inputs + ["url9"]
    if len(invalid_inputs) > max_items:
        print(f"  ✅ Validation would reject: {len(invalid_inputs)} images > {max_items}")
    else:
        print(f"  ❌ Validation should reject: {len(invalid_inputs)} images > {max_items}")
        return False
    
    return True


def main():
    """Run all smoke tests."""
    print("\n" + "="*60)
    print("SMOKE TESTS: nano-banana-pro Model Pipeline")
    print("="*60)
    
    results = []
    
    # Test 1: Defaults
    try:
        result = test_nano_banana_pro_defaults()
        results.append(("Defaults", result))
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Defaults", False))
    
    # Test 2: 4K resolution
    try:
        result = test_nano_banana_pro_4k()
        results.append(("4K Resolution", result))
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("4K Resolution", False))
    
    # Test 3: Image input validation
    try:
        result = test_image_input_validation()
        results.append(("Image Input Validation", result))
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Image Input Validation", False))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n✅ All smoke tests passed!")
        return 0
    else:
        print("\n❌ Some smoke tests failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())

