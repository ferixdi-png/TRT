#!/usr/bin/env python3
"""
Production Check: User Rate Limiting System

ITERATION 8: Validate that rate limiting prevents spam/abuse on paid generations.

Root Cause:
- PAID models have no rate limiting (only FREE tier has limits)
- User with balance can spam 100 gens/second → instant bankruptcy
- No cooldown, no minute/hour limits for paid users

Fix:
- Created UserRateLimiter (5 gens/min, 20 gens/hour, 10s cooldown)
- Integrated into generate_with_payment() BEFORE charge creation
- Logs rejections + stats after successful gens

Tests (6 phases):
1. Import/Config validation
2. Cooldown enforcement (10s between paid gens)
3. Minute limit (5 gens/minute)
4. Hour limit (20 gens/hour)
5. Free tier (no cooldown)
6. Integration with generate_with_payment()

Expected Logs:
- "[RATE_LIMIT] ⏱ User X limited: cooldown (10s)"
- "[RATE_LIMIT] ✅ Generation recorded: user=X, paid=True, stats={'minute': 5/5, 'hour': 20/20}"

Exit Codes:
- 0: ALL CHECKS PASSED (production ready)
- 1: FAILED (critical issue, DO NOT DEPLOY)
"""

import sys
import os
import time
import inspect
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.user_rate_limiter import UserRateLimiter, get_rate_limiter

RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"

def log_phase(phase: int, title: str):
    print(f"\n{BLUE}{BOLD}═══ PHASE {phase}: {title} ═══{RESET}")

def log_pass(msg: str):
    print(f"{GREEN}✅ PASS:{RESET} {msg}")

def log_fail(msg: str):
    print(f"{RED}❌ FAIL:{RESET} {msg}")

def log_warn(msg: str):
    print(f"{YELLOW}⚠️  WARN:{RESET} {msg}")

def log_info(msg: str):
    print(f"ℹ️  {msg}")


# ════════════════════════════════════════════════════════════════════════════
# PHASE 1: Import and Configuration Validation
# ════════════════════════════════════════════════════════════════════════════

def phase1_import_validation():
    """Validate UserRateLimiter exists with correct config."""
    log_phase(1, "Import and Configuration Validation")
    
    # Check UserRateLimiter class exists
    if not hasattr(sys.modules['app.utils.user_rate_limiter'], 'UserRateLimiter'):
        log_fail("UserRateLimiter class not found in app.utils.user_rate_limiter")
        return False
    
    log_pass("UserRateLimiter class exists")
    
    # Check get_rate_limiter() function
    if not callable(get_rate_limiter):
        log_fail("get_rate_limiter() is not callable")
        return False
    
    log_pass("get_rate_limiter() function exists")
    
    # Check configuration constants
    limiter = get_rate_limiter()
    
    expected_configs = {
        'MAX_GENS_PER_MINUTE': 5,
        'MAX_GENS_PER_HOUR': 20,
        'COOLDOWN_SECONDS': 10,
    }
    
    for attr, expected_val in expected_configs.items():
        if not hasattr(limiter, attr):
            log_fail(f"Missing config: {attr}")
            return False
        
        actual_val = getattr(limiter, attr)
        if actual_val != expected_val:
            log_fail(f"{attr} = {actual_val}, expected {expected_val}")
            return False
        
        log_pass(f"{attr} = {actual_val} ✓")
    
    # Check methods exist
    required_methods = ['check_rate_limit', 'record_generation', 'get_user_stats']
    for method in required_methods:
        if not hasattr(limiter, method) or not callable(getattr(limiter, method)):
            log_fail(f"Method {method}() not found or not callable")
            return False
        log_pass(f"Method {method}() exists")
    
    return True


# ════════════════════════════════════════════════════════════════════════════
# PHASE 2: Cooldown Enforcement (10s between paid gens)
# ════════════════════════════════════════════════════════════════════════════

def phase2_cooldown_enforcement():
    """Validate 10s cooldown between paid generations."""
    log_phase(2, "Cooldown Enforcement (10s between paid gens)")
    
    limiter = get_rate_limiter()
    limiter._user_limits.clear()  # Reset state
    
    test_user = 99999
    
    # First generation should be allowed
    check1 = limiter.check_rate_limit(test_user, is_paid=True)
    if not check1['allowed']:
        log_fail(f"First generation blocked: {check1}")
        return False
    log_pass("First paid generation allowed")
    
    # Record it
    limiter.record_generation(test_user, is_paid=True)
    
    # Immediate second generation should be BLOCKED (cooldown)
    check2 = limiter.check_rate_limit(test_user, is_paid=True)
    if check2['allowed']:
        log_fail("Second generation allowed immediately (cooldown not enforced)")
        return False
    
    if check2['reason'] != 'cooldown':
        log_fail(f"Wrong rejection reason: {check2['reason']}, expected 'cooldown'")
        return False
    
    if check2['wait_seconds'] > 10 or check2['wait_seconds'] < 9:
        log_fail(f"Wait time {check2['wait_seconds']}s not in 9-10s range")
        return False
    
    log_pass(f"Cooldown enforced: wait {check2['wait_seconds']}s")
    
    # Wait 11 seconds, should be allowed
    log_info("Simulating 11s wait...")
    time.sleep(11)
    
    check3 = limiter.check_rate_limit(test_user, is_paid=True)
    if not check3['allowed']:
        log_fail(f"Generation blocked after cooldown: {check3}")
        return False
    
    log_pass("Generation allowed after cooldown")
    
    return True


# ════════════════════════════════════════════════════════════════════════════
# PHASE 3: Minute Limit (5 gens/minute)
# ════════════════════════════════════════════════════════════════════════════

def phase3_minute_limit():
    """Validate 5 generations per minute limit."""
    log_phase(3, "Minute Limit (5 gens/minute)")
    
    limiter = get_rate_limiter()
    limiter._user_limits.clear()
    
    test_user = 99998
    
    # Record 5 generations with NO cooldown (simulate rapid clicks)
    for i in range(5):
        # Bypass cooldown by manually adding to history
        now = time.time()
        user_limit = limiter._get_user_limit(test_user)
        user_limit.minute_gens.append(now)
        user_limit.hour_gens.append(now)
        time.sleep(0.1)  # Small delay to spread timestamps
    
    log_pass(f"Recorded 5 generations in <1s")
    
    # 6th generation should be BLOCKED (minute limit)
    check = limiter.check_rate_limit(test_user, is_paid=True)
    if check['allowed']:
        log_fail("6th generation allowed (minute limit not enforced)")
        return False
    
    if check['reason'] != 'minute_limit':
        log_fail(f"Wrong rejection reason: {check['reason']}, expected 'minute_limit'")
        return False
    
    log_pass(f"Minute limit enforced: {check['reason']}")
    
    # Check wait_seconds is reasonable (should be ~60s - time_elapsed)
    if check['wait_seconds'] < 50 or check['wait_seconds'] > 61:
        log_fail(f"Wait time {check['wait_seconds']}s not in 50-61s range")
        return False
    
    log_pass(f"Wait time {check['wait_seconds']}s is correct")
    
    # Get stats
    stats = limiter.get_user_stats(test_user)
    if stats['minute_used'] != 5:
        log_fail(f"Stats show {stats['minute_used']} gens, expected 5")
        return False
    
    log_pass(f"Stats: {stats}")
    
    return True


# ════════════════════════════════════════════════════════════════════════════
# PHASE 4: Hour Limit (20 gens/hour)
# ════════════════════════════════════════════════════════════════════════════

def phase4_hour_limit():
    """Validate 20 generations per hour limit."""
    log_phase(4, "Hour Limit (20 gens/hour)")
    
    limiter = get_rate_limiter()
    limiter._user_limits.clear()
    
    test_user = 99997
    
    # Record 20 generations spread over 10 minutes (bypass minute limit)
    now = time.time()
    user_limit = limiter._get_user_limit(test_user)
    for i in range(20):
        # Spread across 10 minutes (30s apart)
        timestamp = now - (i * 30)
        user_limit.hour_gens.append(timestamp)
    
    log_pass(f"Recorded 20 generations spread over 10 minutes")
    
    # 21st generation should be BLOCKED (hour limit)
    check = limiter.check_rate_limit(test_user, is_paid=True)
    if check['allowed']:
        log_fail("21st generation allowed (hour limit not enforced)")
        return False
    
    if check['reason'] != 'hour_limit':
        log_fail(f"Wrong rejection reason: {check['reason']}, expected 'hour_limit'")
        return False
    
    log_pass(f"Hour limit enforced: {check['reason']}")
    
    # Get stats
    stats = limiter.get_user_stats(test_user)
    if stats['hour_used'] != 20:
        log_fail(f"Stats show {stats['hour_used']} gens, expected 20")
        return False
    
    log_pass(f"Stats: {stats}")
    
    return True


# ════════════════════════════════════════════════════════════════════════════
# PHASE 5: Free Tier (no cooldown, only minute/hour limits)
# ════════════════════════════════════════════════════════════════════════════

def phase5_free_tier():
    """Validate FREE models have no cooldown, only minute/hour limits."""
    log_phase(5, "Free Tier (no cooldown)")
    
    limiter = get_rate_limiter()
    limiter._user_limits.clear()
    
    test_user = 99996
    
    # First FREE generation
    check1 = limiter.check_rate_limit(test_user, is_paid=False)
    if not check1['allowed']:
        log_fail(f"First FREE gen blocked: {check1}")
        return False
    log_pass("First FREE generation allowed")
    
    limiter.record_generation(test_user, is_paid=False)
    
    # Immediate second FREE generation should be ALLOWED (no cooldown for free)
    check2 = limiter.check_rate_limit(test_user, is_paid=False)
    if not check2['allowed']:
        log_fail(f"Second FREE gen blocked: {check2} (should have no cooldown)")
        return False
    
    log_pass("FREE models have no cooldown (as expected)")
    
    # But minute limit still applies
    # Record 4 more (total 5 in minute)
    for _ in range(4):
        limiter.record_generation(test_user, is_paid=False)
    
    # 6th should be blocked by minute limit
    check3 = limiter.check_rate_limit(test_user, is_paid=False)
    if check3['allowed']:
        log_fail("6th FREE gen allowed (minute limit not enforced)")
        return False
    
    if check3['reason'] != 'minute_limit':
        log_fail(f"Wrong reason: {check3['reason']}, expected 'minute_limit'")
        return False
    
    log_pass(f"FREE models respect minute/hour limits: {check3['reason']}")
    
    return True


# ════════════════════════════════════════════════════════════════════════════
# PHASE 6: Integration with generate_with_payment()
# ════════════════════════════════════════════════════════════════════════════

def phase6_integration():
    """Validate rate limiting is integrated into generate_with_payment()."""
    log_phase(6, "Integration with generate_with_payment()")
    
    # Import the module
    try:
        from app.payments.integration import generate_with_payment
    except ImportError as e:
        log_fail(f"Cannot import generate_with_payment: {e}")
        return False
    
    log_pass("generate_with_payment() imported")
    
    # Check source code contains rate limiter calls
    source = inspect.getsource(generate_with_payment)
    
    required_patterns = [
        'get_rate_limiter',
        'check_rate_limit',
        'record_generation',
        'RATE_LIMIT',
    ]
    
    for pattern in required_patterns:
        if pattern not in source:
            log_fail(f"Pattern '{pattern}' not found in generate_with_payment() source")
            return False
        log_pass(f"Pattern '{pattern}' found in source")
    
    # Check that rate check happens BEFORE charge creation
    check_index = source.find('check_rate_limit')
    charge_index = source.find('create_charge')
    
    if check_index == -1:
        log_fail("check_rate_limit() not called in generate_with_payment()")
        return False
    
    if charge_index != -1 and check_index > charge_index:
        log_fail("check_rate_limit() called AFTER create_charge() (should be BEFORE)")
        return False
    
    log_pass("Rate check happens BEFORE charge creation")
    
    # Check that record_generation is called AFTER success
    record_index = source.find('record_generation')
    if record_index == -1:
        log_fail("record_generation() not called after success")
        return False
    
    # Find "if gen_result.get('success')" block
    success_check_index = source.find("if gen_result.get('success')")
    if success_check_index == -1:
        log_fail("Cannot find success check block")
        return False
    
    if record_index < success_check_index:
        log_fail("record_generation() called BEFORE success check")
        return False
    
    log_pass("record_generation() called AFTER success confirmation")
    
    return True


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    print(f"{BOLD}{BLUE}╔════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{BLUE}║  PRODUCTION CHECK: User Rate Limiting System (ITERATION 8)  ║{RESET}")
    print(f"{BOLD}{BLUE}╚════════════════════════════════════════════════════════════════╝{RESET}")
    
    phases = [
        ("Import/Config Validation", phase1_import_validation),
        ("Cooldown Enforcement (10s)", phase2_cooldown_enforcement),
        ("Minute Limit (5/min)", phase3_minute_limit),
        ("Hour Limit (20/hour)", phase4_hour_limit),
        ("Free Tier (no cooldown)", phase5_free_tier),
        ("Integration Check", phase6_integration),
    ]
    
    results = []
    for title, phase_func in phases:
        try:
            passed = phase_func()
            results.append((title, passed))
        except Exception as e:
            log_fail(f"Exception in {title}: {e}")
            import traceback
            traceback.print_exc()
            results.append((title, False))
    
    # Summary
    print(f"\n{BOLD}{BLUE}═══ SUMMARY ═══{RESET}")
    all_passed = True
    for title, passed in results:
        status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
        print(f"{status}: {title}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print(f"{GREEN}{BOLD}╔═══════════════════════════════════════════════════╗{RESET}")
        print(f"{GREEN}{BOLD}║  ✅ ALL CHECKS PASSED - PRODUCTION READY         ║{RESET}")
        print(f"{GREEN}{BOLD}║  Rate limiting system is correctly implemented    ║{RESET}")
        print(f"{GREEN}{BOLD}║  - Cooldown: 10s between paid gens               ║{RESET}")
        print(f"{GREEN}{BOLD}║  - Minute limit: 5 gens/min                      ║{RESET}")
        print(f"{GREEN}{BOLD}║  - Hour limit: 20 gens/hour                      ║{RESET}")
        print(f"{GREEN}{BOLD}║  - Free tier: no cooldown, same limits           ║{RESET}")
        print(f"{GREEN}{BOLD}║  - Integrated into generate_with_payment()       ║{RESET}")
        print(f"{GREEN}{BOLD}╚═══════════════════════════════════════════════════╝{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}╔═══════════════════════════════════════════════════╗{RESET}")
        print(f"{RED}{BOLD}║  ❌ CHECKS FAILED - DO NOT DEPLOY                 ║{RESET}")
        print(f"{RED}{BOLD}║  Fix rate limiting issues before pushing         ║{RESET}")
        print(f"{RED}{BOLD}╚═══════════════════════════════════════════════════╝{RESET}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
