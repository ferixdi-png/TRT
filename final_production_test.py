#!/usr/bin/env python3
"""
Final production readiness test - covers all critical fixes
"""

import asyncio
import sys

def test_poll_interval():
    """Test that poll_interval is properly defined in generator"""
    print("\n🧪 TEST: poll_interval definition")
    
    try:
        with open('app/kie/generator.py', 'r') as f:
            content = f.read()
            
        # Check that poll_interval is defined
        if 'poll_interval = 2' in content:
            print("   ✅ poll_interval defined")
        else:
            print("   ❌ poll_interval NOT defined")
            return False
            
        # Check that it's used in the logging statement
        if 'POLLING | TaskID: {task_id} | Timeout: {timeout}s | Interval: {poll_interval}s' in content:
            print("   ✅ poll_interval used in logging")
        else:
            print("   ❌ poll_interval NOT used in logging")
            return False
            
        # Check that asyncio.sleep uses it
        if 'await asyncio.sleep(poll_interval)' in content:
            print("   ✅ poll_interval used in asyncio.sleep")
        else:
            print("   ❌ poll_interval NOT used in asyncio.sleep")
            return False
            
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_required_fields():
    """Test required fields validation"""
    print("\n🧪 TEST: Required fields validation")
    
    try:
        from app.kie.field_options import (
            validate_required_fields, 
            get_required_fields,
            REQUIRED_FIELDS
        )
        
        # Test 1: z-image is in REQUIRED_FIELDS
        if 'z-image' in REQUIRED_FIELDS:
            print("   ✅ z-image has required fields defined")
        else:
            print("   ❌ z-image NOT in REQUIRED_FIELDS")
            return False
            
        # Test 2: z-image requires both prompt and aspect_ratio
        required = get_required_fields('z-image')
        if 'prompt' in required and 'aspect_ratio' in required:
            print(f"   ✅ z-image requires: {required}")
        else:
            print(f"   ❌ z-image requirements incorrect: {required}")
            return False
            
        # Test 3: Validation works - valid case
        valid, msg = validate_required_fields('z-image', {'prompt': 'test', 'aspect_ratio': '1:1'})
        if valid and msg == '':
            print("   ✅ Validation accepts valid inputs")
        else:
            print(f"   ❌ Validation failed for valid inputs: {msg}")
            return False
            
        # Test 4: Validation works - missing field
        valid, msg = validate_required_fields('z-image', {'prompt': 'test'})
        if not valid and 'aspect_ratio' in msg:
            print(f"   ✅ Validation rejects missing fields: {msg}")
        else:
            print(f"   ❌ Validation didn't catch missing field")
            return False
            
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_flow_validation():
    """Test that flow.py has required field validation"""
    print("\n🧪 TEST: Flow handler validation")
    
    try:
        with open('bot/handlers/flow.py', 'r') as f:
            content = f.read()
            
        # Check for import
        if 'from app.kie.field_options import validate_required_fields' in content:
            print("   ✅ validate_required_fields imported in flow.py")
        else:
            print("   ❌ validate_required_fields NOT imported in flow.py")
            return False
            
        # Check for validation call
        if 'is_valid, error_msg = validate_required_fields' in content:
            print("   ✅ validate_required_fields called before generation")
        else:
            print("   ❌ validate_required_fields NOT called")
            return False
            
        # Check for error handling
        if 'Missing required' in content or 'Missing required fields' in content:
            print("   ✅ Error handling for missing required fields")
        else:
            print("   ⚠️  Error handling message may need review")
            
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_syntax():
    """Test that critical files have valid Python syntax"""
    print("\n🧪 TEST: Python syntax validation")
    
    files_to_check = [
        'app/kie/generator.py',
        'app/kie/field_options.py',
        'bot/handlers/flow.py'
    ]
    
    all_valid = True
    for filepath in files_to_check:
        try:
            with open(filepath, 'r') as f:
                code = f.read()
            compile(code, filepath, 'exec')
            print(f"   ✅ {filepath} - syntax OK")
        except SyntaxError as e:
            print(f"   ❌ {filepath} - syntax ERROR: {e}")
            all_valid = False
        except Exception as e:
            print(f"   ❌ {filepath} - error: {e}")
            all_valid = False
            
    return all_valid

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("FINAL PRODUCTION READINESS TEST")
    print("="*70)
    
    results = []
    
    results.append(("poll_interval definition", test_poll_interval()))
    results.append(("required fields validation", test_required_fields()))
    results.append(("flow handler validation", test_flow_validation()))
    results.append(("Python syntax", test_syntax()))
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("="*70)
    if all_passed:
        print("\n🎉 ALL TESTS PASSED - READY FOR PRODUCTION!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED - REVIEW NEEDED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
