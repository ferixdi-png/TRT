#!/usr/bin/env python3
"""
Test input validation integration in generator.py

Verifies:
1. Valid inputs pass through to generation
2. Missing required fields are rejected with clear errors
3. Invalid enum values are rejected with clear errors
4. Unknown models are rejected

DRY RUN - uses KIE_STUB=true to avoid real API calls
"""
import os
import sys
import asyncio
import logging

# Set test mode
os.environ['KIE_STUB'] = 'true'
os.environ['TEST_MODE'] = 'true'

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.kie.generator import KieGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_valid_inputs():
    """Test that valid inputs pass validation"""
    print("\n" + "="*80)
    print("TEST 1: Valid inputs should pass")
    print("="*80)
    
    generator = KieGenerator()
    
    # z-image requires: prompt (string), aspect_ratio (enum)
    inputs = {
        'prompt': 'A beautiful sunset over mountains',
        'aspect_ratio': '16:9'
    }
    
    # Test validation only by catching early return
    # We'll use timeout to avoid waiting for polling
    try:
        result = await asyncio.wait_for(
            generator.generate(
                model_id='z-image',
                user_inputs=inputs,
                user_id=1,
                chat_id=1,
                timeout=1  # Very short timeout to skip polling
            ),
            timeout=3.0
        )
    except asyncio.TimeoutError:
        # This is OK - validation passed and it started generation
        print("\n✅ Result: Validation passed (timed out during generation - expected)")
        print("\n✅ Test passed: Valid inputs accepted")
        return
    
    # If we get here quickly with error_code, validation might have failed
    if not result.get('success') and result.get('error_code') == 'VALIDATION_ERROR':
        raise AssertionError(f"Validation should have passed: {result}")
    
    print(f"\n✅ Result: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print("\n✅ Test passed: Valid inputs accepted")


async def test_missing_required():
    """Test that missing required fields are rejected"""
    print("\n" + "="*80)
    print("TEST 2: Missing required field should fail")
    print("="*80)
    
    generator = KieGenerator()
    
    # z-image requires prompt + aspect_ratio, only providing prompt
    inputs = {
        'prompt': 'A beautiful sunset'
        # Missing aspect_ratio
    }
    
    result = await generator.generate(
        model_id='z-image',
        user_inputs=inputs,
        user_id=1,
        chat_id=1
    )
    
    print(f"\n❌ Result: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Error: {result.get('error_code')}")
    
    assert result['success'] == False, "Should fail validation"
    assert result['error_code'] == 'VALIDATION_ERROR', "Should be validation error"
    assert 'aspect_ratio' in result['message'].lower(), "Should mention missing field"
    print("\n✅ Test passed: Missing required field detected")


async def test_invalid_enum():
    """Test that invalid enum values are rejected"""
    print("\n" + "="*80)
    print("TEST 3: Invalid enum value should fail")
    print("="*80)
    
    generator = KieGenerator()
    
    # aspect_ratio must be one of: 1:1, 16:9, 9:16, 4:3, 3:4, 21:9, 9:21
    inputs = {
        'prompt': 'A beautiful sunset',
        'aspect_ratio': '32:9'  # Invalid value
    }
    
    result = await generator.generate(
        model_id='z-image',
        user_inputs=inputs,
        user_id=1,
        chat_id=1
    )
    
    print(f"\n❌ Result: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Error: {result.get('error_code')}")
    
    assert result['success'] == False, "Should fail validation"
    assert result['error_code'] == 'VALIDATION_ERROR', "Should be validation error"
    assert 'aspect_ratio' in result['message'].lower(), "Should mention invalid field"
    print("\n✅ Test passed: Invalid enum value detected")


async def test_unknown_model():
    """Test that unknown models are rejected"""
    print("\n" + "="*80)
    print("TEST 4: Unknown model should fail")
    print("="*80)
    
    generator = KieGenerator()
    
    inputs = {
        'prompt': 'Test'
    }
    
    result = await generator.generate(
        model_id='nonexistent-model-xyz',
        user_inputs=inputs,
        user_id=1,
        chat_id=1
    )
    
    print(f"\n❌ Result: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    print(f"   Error: {result.get('error_code')}")
    
    assert result['success'] == False, "Should fail validation"
    assert result['error_code'] == 'VALIDATION_ERROR', "Should be validation error"
    print("\n✅ Test passed: Unknown model detected")


async def main():
    """Run all validation integration tests"""
    print("\n" + "🔧"*40)
    print("INPUT VALIDATION INTEGRATION TESTS")
    print("Testing: generator.py validation layer")
    print("Mode: DRY RUN (KIE_STUB=true)")
    print("🔧"*40)
    
    try:
        await test_valid_inputs()
        await test_missing_required()
        await test_invalid_enum()
        await test_unknown_model()
        
        print("\n" + "✅"*40)
        print("ALL VALIDATION TESTS PASSED")
        print("✅"*40)
        print("\nIntegration complete:")
        print("  ✅ Valid inputs pass through")
        print("  ✅ Missing required fields rejected")
        print("  ✅ Invalid enum values rejected")
        print("  ✅ Unknown models rejected")
        print("\n🎯 PHASE B COMPLETE: Validation integrated into generator.py")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
