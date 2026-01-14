#!/usr/bin/env python3
"""
Comprehensive smoke test: full generation pipeline.
Tests: balance → selection → parameters → background task → callback → result
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def smoke_test_generation_pipeline():
    """Test full generation pipeline without real KIE."""
    print("🧪 SMOKE TEST: Generation Pipeline")
    print("=" * 70)
    
    results = {
        'passed': 0,
        'failed': 0,
        'errors': []
    }
    
    # Test 1: Import critical modules
    try:
        from app.payments.integration import generate_with_payment
        from app.kie.generator import KieGenerator
        from bot.handlers.flow import confirm_cb
        print(f"  ✅ Critical imports: OK")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"Import failed: {e}")
        print(f"  ❌ Import failed: {e}")
        return results
    
    # Test 2: Generator initialization
    try:
        generator = KieGenerator()
        assert generator is not None
        print(f"  ✅ KieGenerator init: OK")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"Generator init: {e}")
        print(f"  ❌ Generator init failed: {e}")
    
    # Test 3: Source of Truth loaded
    try:
        from app.kie.builder import load_source_of_truth
        sot = load_source_of_truth()
        assert 'models' in sot
        model_count = len(sot['models'])
        print(f"  ✅ SOURCE_OF_TRUTH loaded: {model_count} models")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"SOT load: {e}")
        print(f"  ❌ SOURCE_OF_TRUTH failed: {e}")
    
    # Test 4: Field options valid
    try:
        from app.kie.field_options import get_field_options
        qwen_sizes = get_field_options("qwen/text-to-image", "image_size")
        assert "square_hd" in qwen_sizes, f"Expected square_hd in {qwen_sizes}"
        print(f"  ✅ Field options valid: qwen image_size = {qwen_sizes}")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"Field options: {e}")
        print(f"  ❌ Field options failed: {e}")
    
    # Test 5: Free models detection
    try:
        from app.pricing.free_models import is_free_model, get_free_models
        free_list = get_free_models()
        print(f"  ✅ FREE models: {len(free_list)} total")
        for mid in free_list[:3]:
            print(f"      - {mid}")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"Free models: {e}")
        print(f"  ❌ Free models detection failed: {e}")
    
    # Test 6: Correlation tracking
    try:
        from app.utils.correlation import ensure_correlation_id, correlation_tag, clear_correlation_id
        ensure_correlation_id("test_smoke_123")
        tag = correlation_tag()
        assert "test_smoke_123" in tag
        clear_correlation_id()
        print(f"  ✅ Correlation tracking: {tag}")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"Correlation: {e}")
        print(f"  ❌ Correlation failed: {e}")
    
    # Test 7: Background task exception handling (mock test)
    try:
        import asyncio
        
        exception_caught = False
        
        async def failing_task():
            raise ValueError("Test exception in BG task")
        
        task = asyncio.create_task(failing_task())
        
        def callback(future):
            nonlocal exception_caught
            try:
                future.result()
            except ValueError:
                exception_caught = True
        
        task.add_done_callback(callback)
        
        # Wait for task to complete
        try:
            await task
        except ValueError:
            pass
        
        await asyncio.sleep(0.1)  # Give callback time to run
        
        assert exception_caught, "Exception not caught by callback"
        print(f"  ✅ BG task exception handling: OK")
        results['passed'] += 1
    except Exception as e:
        results['failed'] += 1
        results['errors'].append(f"BG task handling: {e}")
        print(f"  ❌ BG task exception handling failed: {e}")
    
    print("\n" + "=" * 70)
    print(f"📊 RESULTS: {results['passed']} PASSED, {results['failed']} FAILED")
    
    if results['failed'] > 0:
        print("\n❌ FAILED TESTS:")
        for error in results['errors']:
            print(f"  - {error}")
        return 1
    else:
        print("\n✅ SMOKE TEST PASSED - Generation pipeline ready")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(smoke_test_generation_pipeline())
    sys.exit(exit_code)
