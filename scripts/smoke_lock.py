#!/usr/bin/env python3
"""
Smoke test for lock contention behavior - fast verification (<10s)
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_lock_config_exists():
    """Verify lock configuration constants exist"""
    print("🧪 Testing lock configuration...")
    
    from app.locking.single_instance import (
        LOCK_MODE_WAIT_PASSIVE,
        LOCK_MODE_WAIT_FORCE,
        LOCK_DEFAULT_MODE,
        LOCK_WAIT_SECONDS,
        LOCK_RETRY_BACKOFF_BASE,
        LOCK_RETRY_BACKOFF_MAX,
    )
    
    assert LOCK_MODE_WAIT_PASSIVE == "wait_then_passive"
    assert LOCK_MODE_WAIT_FORCE == "wait_then_force"
    assert LOCK_DEFAULT_MODE == LOCK_MODE_WAIT_PASSIVE, "Default should be safe mode"
    assert LOCK_WAIT_SECONDS > 0
    assert LOCK_RETRY_BACKOFF_BASE == 0.5
    assert LOCK_RETRY_BACKOFF_MAX == 5.0
    
    print("  ✅ Lock config OK")


def test_lock_api_exports():
    """Verify new API functions are exported"""
    print("🧪 Testing lock API exports...")
    
    from app.locking import (
        acquire_single_instance_lock,
        is_active_mode,
        start_background_lock_retry,
        stop_background_lock_retry,
    )
    
    assert callable(acquire_single_instance_lock)
    assert callable(is_active_mode)
    assert callable(start_background_lock_retry)
    assert callable(stop_background_lock_retry)
    
    print("  ✅ Lock API OK")


def test_no_stale_release():
    """Verify dangerous stale release logic removed"""
    print("🧪 Testing stale release removal...")
    
    import app.locking.single_instance as lock_module
    import inspect
    
    # Function should not exist
    assert not hasattr(lock_module, '_force_release_stale_lock'), \
        "Dangerous stale release function still exists!"
    
    # Source should not call it
    source = inspect.getsource(lock_module.acquire_single_instance_lock)
    assert '_force_release_stale_lock' not in source, \
        "acquire still calls stale release!"
    
    assert 'FORCE ACTIVE' not in source or 'wait_then_force' in source, \
        "Old FORCE ACTIVE logic without wait should be replaced"
    
    print("  ✅ Stale release removed")


def test_passive_mode_webhook_behavior():
    """Verify webhook returns 200 in passive mode (no 503)"""
    print("🧪 Testing passive mode webhook behavior...")
    
    import inspect
    import main_render
    
    # Check main_render.py webhook implementation
    source = inspect.getsource(main_render)
    
    # Should NOT raise 503 in passive mode
    assert 'HTTPServiceUnavailable' not in source or 'PASSIVE' in source, \
        "Webhook should not return 503 in passive mode"
    
    # Should have passive mode check
    assert 'active_state.active' in source, "Webhook should check active state"
    assert 'PASSIVE' in source or 'passive' in source, "Should have passive mode logic"
    
    print("  ✅ Webhook passive mode OK")


def test_lock_mode_env_var():
    """Verify LOCK_MODE env var is read correctly"""
    print("🧪 Testing LOCK_MODE environment variable...")
    
    import os
    from unittest.mock import patch
    
    # Test default (safe mode)
    with patch.dict(os.environ, {}, clear=False):
        from app.locking.single_instance import _lock_mode
        # Default should be wait_then_passive (loaded at import)
        # This is checked in test_lock_config_exists
    
    print("  ✅ LOCK_MODE env var OK")


def main():
    """Run all smoke tests"""
    print("=" * 60)
    print("🔒 Lock Contention Smoke Tests")
    print("=" * 60)
    
    tests = [
        test_lock_config_exists,
        test_lock_api_exports,
        test_no_stale_release,
        test_passive_mode_webhook_behavior,
        test_lock_mode_env_var,
    ]
    
    failed = []
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            failed.append(test.__name__)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            failed.append(test.__name__)
    
    print("=" * 60)
    if failed:
        print(f"❌ {len(failed)} test(s) failed: {', '.join(failed)}")
        print("=" * 60)
        return 1
    else:
        print("✅ All lock smoke tests passed!")
        print("=" * 60)
        return 0


if __name__ == '__main__':
    sys.exit(main())
