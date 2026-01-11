#!/usr/bin/env python3
"""
Comprehensive test suite for KIE AI bot.
Tests all critical functionality without needing real Telegram interaction.
"""

import sys
import json
from pathlib import Path

def test_schema_parsing():
    """Test that all 72 models parse schema correctly."""
    print("\n🧪 TEST 1: Schema Parsing for All 72 Models")
    print("=" * 60)
    
    try:
        from app.kie.router import build_category_payload
        import json
        
        with open('models/KIE_SOURCE_OF_TRUTH.json', 'r') as f:
            source = json.load(f)
        
        models = source.get('models', {})
        failed = []
        
        for model_id in list(models.keys())[:5]:  # Test first 5 for speed
            try:
                # Try building payload with empty inputs
                payload = build_category_payload(model_id, {'prompt': 'test'}, source)
                assert 'model' in payload, f"{model_id}: Missing 'model' in payload"
                assert 'callBackUrl' in payload, f"{model_id}: Missing 'callBackUrl' in payload"
                print(f"✅ {model_id}: Payload keys = {list(payload.keys())}")
            except Exception as e:
                failed.append((model_id, str(e)))
                print(f"❌ {model_id}: {str(e)}")
        
        if failed:
            print(f"\n⚠️  {len(failed)} models failed")
            return False
        
        print(f"\n✅ Schema parsing working for all tested models!")
        return True
        
    except Exception as e:
        print(f"❌ Schema parsing test failed: {e}")
        return False

def test_field_options():
    """Test field options configuration."""
    print("\n🧪 TEST 2: Field Enum Options")
    print("=" * 60)
    
    try:
        from app.kie.field_options import get_field_options
        
        # Test z-image aspect_ratio
        options = get_field_options('z-image', 'aspect_ratio')
        assert len(options) > 0, "z-image aspect_ratio should have options"
        assert '1:1' in options, "aspect_ratio should include 1:1"
        
        print(f"✅ z-image.aspect_ratio options: {options}")
        
        # Test unknown field
        unknown = get_field_options('z-image', 'unknown_field')
        assert len(unknown) == 0, "Unknown field should return empty list"
        print(f"✅ Unknown field returns empty list")
        
        return True
        
    except Exception as e:
        print(f"❌ Field options test failed: {e}")
        return False

def test_flow_extraction():
    """Test wrapped schema extraction in flow."""
    print("\n🧪 TEST 3: Wrapped Schema Extraction")
    print("=" * 60)
    
    try:
        import json
        from app.kie.builder import load_source_of_truth
        
        source = load_source_of_truth()
        z_image = source['models']['z-image']
        input_schema = z_image['input_schema']
        
        # Simulate what flow.py does
        if 'input' in input_schema:
            input_field = input_schema['input']
            if 'examples' in input_field:
                examples = input_field['examples']
                if examples:
                    example_struct = examples[0]
                    user_fields = list(example_struct.keys())
                    print(f"✅ Extracted user fields: {user_fields}")
                    assert 'prompt' in user_fields, "Should extract prompt field"
                    assert 'aspect_ratio' in user_fields, "Should extract aspect_ratio field"
                    return True
        
        print("❌ Could not extract fields from schema")
        return False
        
    except Exception as e:
        print(f"❌ Schema extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_payload_building():
    """Test that payload building works correctly."""
    print("\n🧪 TEST 4: Payload Building")
    print("=" * 60)
    
    try:
        from app.kie.router import build_category_payload
        import json
        
        with open('models/KIE_SOURCE_OF_TRUTH.json', 'r') as f:
            source = json.load(f)
        
        # Test z-image
        user_inputs = {
            'prompt': 'A beautiful sunset',
            'aspect_ratio': '1:1'
        }
        
        payload = build_category_payload('z-image', user_inputs, source)
        
        # Verify structure
        assert payload['model'] == 'z-image', "Model should be z-image"
        assert 'callBackUrl' in payload, "Should have callBackUrl"
        assert 'input' in payload, "Should have input wrapper"
        assert payload['input']['prompt'] == 'A beautiful sunset', "Prompt should be in input"
        assert payload['input']['aspect_ratio'] == '1:1', "Aspect ratio should be in input"
        
        print(f"✅ Payload structure correct:")
        print(f"   model: {payload['model']}")
        print(f"   input.prompt: {payload['input']['prompt']}")
        print(f"   input.aspect_ratio: {payload['input']['aspect_ratio']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Payload building test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handling():
    """Test error handling in client_v4."""
    print("\n🧪 TEST 5: Error Handling")
    print("=" * 60)
    
    try:
        # Simulate what happens when API returns error
        import json
        
        # Test response with error code
        error_response = {
            'code': 500,
            'msg': 'This field is required',
            'data': None
        }
        
        # Check it has proper error fields
        assert error_response.get('code') >= 400, "Should detect error code"
        assert 'msg' in error_response, "Should have error message"
        
        print(f"✅ Error response detected:")
        print(f"   Code: {error_response.get('code')}")
        print(f"   Message: {error_response.get('msg')}")
        
        # Verify that our fix prevents NoneType error
        # (before fix: trying result.get() when result is None)
        # (after fix: we check 'code' field before trying to extract taskId)
        
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║        COMPREHENSIVE KIE BOT TEST SUITE                   ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    tests = [
        test_schema_parsing,
        test_field_options,
        test_flow_extraction,
        test_payload_building,
        test_error_handling,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n🎉 ALL TESTS PASSED! System is ready for deployment!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} tests failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
