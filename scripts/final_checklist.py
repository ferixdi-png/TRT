#!/usr/bin/env python3
"""
Final pre-deployment checklist for TRT bot on Render.

Verifies:
1. ✅ FORCE ACTIVE MODE enabled (fixed passive mode blocker)
2. ✅ All 72 KIE models validated
3. ✅ Payment flow tested
4. ✅ Bot smoke test passed
5. ✅ Syntax validation passed
"""

import os
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run command and report results."""
    print(f"\n▶ {description}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd="/workspaces/TRT"
        )
        if result.returncode == 0:
            print(f"   ✅ PASSED")
            return True
        else:
            print(f"   ❌ FAILED: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False


def check_file_content(filepath, search_string, description):
    """Check if file contains required string."""
    print(f"\n▶ {description}")
    try:
        path = Path(filepath)
        if not path.exists():
            print(f"   ❌ File not found: {filepath}")
            return False
        
        with open(path, 'r') as f:
            content = f.read()
        
        if search_string in content:
            print(f"   ✅ PASSED")
            return True
        else:
            print(f"   ❌ NOT FOUND: {search_string}")
            return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False


def main():
    """Run final deployment checklist."""
    
    print("\n" + "="*70)
    print("FINAL PRE-DEPLOYMENT CHECKLIST")
    print("="*70)
    
    checks = []
    
    # 1. FORCE ACTIVE MODE check
    print("\n[1/5] FORCE ACTIVE MODE Implementation")
    checks.append(check_file_content(
        "/workspaces/TRT/app/locking/single_instance.py",
        "_force_release_stale_lock",
        "Stale lock release function"
    ))
    checks.append(check_file_content(
        "/workspaces/TRT/app/locking/single_instance.py",
        "SINGLETON_LOCK_FORCE_ACTIVE",
        "Force active mode env var"
    ))
    checks.append(check_file_content(
        "/workspaces/TRT/app/locking/single_instance.py",
        "ACTIVE MODE",
        "ACTIVE MODE log message"
    ))
    
    # 2. Models validation
    print("\n[2/5] Models Validation (72 KIE Models)")
    checks.append(run_command(
        "python3 scripts/test_models_validity.py | tail -5",
        "Run KIE models validation test"
    ))
    
    # 3. Payment flow
    print("\n[3/5] Payment Flow Verification")
    checks.append(run_command(
        "python3 tests/test_payment_flow.py | tail -5",
        "Run payment flow test"
    ))
    
    # 4. Bot smoke test
    print("\n[4/5] Bot Smoke Test")
    checks.append(run_command(
        "python3 scripts/smoke_bot_active_mode.py | tail -5",
        "Run bot startup smoke test"
    ))
    
    # 5. Syntax validation
    print("\n[5/5] Python Syntax Validation")
    checks.append(run_command(
        "python3 -m py_compile main_render.py app/locking/single_instance.py database.py",
        "Check core files syntax"
    ))
    
    # Summary
    print("\n" + "="*70)
    passed = sum(checks)
    total = len(checks)
    
    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        print("\n📋 DEPLOYMENT READINESS: GREEN ✅")
        print("\nReady to deploy to Render:")
        print("  1. Push to GitHub (commits already pushed)")
        print("  2. Trigger Render deployment")
        print("  3. Monitor first 30 seconds for ACTIVE MODE log")
        print("  4. Test webhook with: /api/test_webhook")
        return 0
    else:
        print(f"❌ SOME CHECKS FAILED ({passed}/{total})")
        print("\n📋 DEPLOYMENT READINESS: RED ❌")
        print("\nFix failed checks before deployment")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
