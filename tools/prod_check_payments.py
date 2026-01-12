#!/usr/bin/env python3
"""
PRODUCTION CHECK: Payments System Validation

Validates critical payment flows to prevent revenue loss:
- PHASE 1: Free tier detection (prevent charging free models)
- PHASE 2: Code analysis for double charge bugs
- PHASE 3: Idempotency patterns
- PHASE 4: Insufficient balance checks

Expected result: 0 CRITICAL ERRORS
"""
import sys
import os
from pathlib import Path
import inspect

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup
from app.pricing.free_models import is_free_model, get_free_models
from app.payments import charges


def phase1_free_tier():
    """PHASE 1: Free tier detection."""
    print("\n" + "="*80)
    print("PHASE 1: Free Tier Detection")
    print("="*80)
    
    errors = []
    warnings = []
    
    # Check free models list
    free_models = get_free_models()
    print(f"✅ Free models count: {len(free_models)}")
    if not free_models:
        errors.append("❌ CRITICAL: No free models found! Users can't use bot without balance.")
    
    # Verify is_free_model() works
    for model_id in free_models:
        if not is_free_model(model_id):
            errors.append(f"❌ CRITICAL: is_free_model('{model_id}') returns False but it's in free list!")
    
    # Check paid model detection
    paid_model = "flux-dev/black-forest-labs"  # Known paid model
    if is_free_model(paid_model):
        errors.append(f"❌ CRITICAL: Paid model '{paid_model}' detected as FREE! Revenue loss!")
    else:
        print(f"✅ Paid model '{paid_model}' correctly detected as paid")
    
    return errors, warnings


def phase2_double_charge_analysis():
    """PHASE 2: Static analysis for double charge bugs."""
    print("\n" + "="*80)
    print("PHASE 2: Double Charge Code Analysis")
    print("="*80)
    
    errors = []
    warnings = []
    
    # Read commit_charge source
    source = inspect.getsource(charges.ChargeManager.commit_charge)
    
    # Check if _execute_charge is CALLED (not just mentioned in comments)
    has_execute_charge_call = False
    lines = source.split('\n')
    for line in lines:
        stripped = line.strip()
        # Skip comments
        if stripped.startswith('#'):
            continue
        # Check for actual call
        if 'await self._execute_charge' in stripped or '_execute_charge(' in stripped:
            has_execute_charge_call = True
            break
    
    # Check for double charge pattern (wallet_service.charge + _execute_charge CALL)
    if "wallet_service.charge" in source and has_execute_charge_call:
        errors.append(
            "❌ CRITICAL: commit_charge() calls BOTH wallet_service.charge() AND _execute_charge(). "
            "This creates DOUBLE CHARGE - funds deducted twice!"
        )
        print("❌ CRITICAL: Double charge pattern detected:")
        print("   - wallet_service.charge() → deducts from hold")
        print("   - _execute_charge() → legacy stub, will double-charge if implemented")
        
        # Show affected lines
        for i, line in enumerate(lines):
            if 'wallet_service.charge' in line or ('_execute_charge' in line and not line.strip().startswith('#')):
                print(f"   Line {i+1}: {line.strip()}")
    elif "wallet_service.charge" in source and not has_execute_charge_call:
        print("✅ commit_charge() only calls wallet_service.charge() (no double charge)")
        # Show FIXED comment if present
        if "FIXED:" in source or "Do NOT call _execute_charge" in source:
            print("   ✅ Found fix comment preventing _execute_charge() call")
    
    # Check _execute_charge implementation
    execute_charge_source = inspect.getsource(charges.ChargeManager._execute_charge)
    if "TODO" in execute_charge_source or "return {'success': True}" in execute_charge_source:
        print("✅ _execute_charge() is currently a stub (safe even if called)")
    else:
        errors.append(
            "❌ CRITICAL: _execute_charge() is implemented! Will cause double charge if called."
        )
    
    return errors, warnings


def phase3_idempotency_patterns():
    """PHASE 3: Check idempotency patterns in code."""
    print("\n" + "="*80)
    print("PHASE 3: Idempotency Pattern Analysis")
    print("="*80)
    
    errors = []
    warnings = []
    
    # Check WalletService idempotency
    from app.database import services
    
    methods_to_check = ['hold', 'charge', 'release', 'refund', 'topup']
    
    for method_name in methods_to_check:
        method = getattr(services.WalletService, method_name, None)
        if not method:
            warnings.append(f"⚠️ Method {method_name} not found in WalletService")
            continue
        
        source = inspect.getsource(method)
        
        # Check for idempotency via ref check
        if "SELECT id FROM ledger WHERE ref = " in source:
            print(f"✅ {method_name}() has idempotency check via ref")
        else:
            errors.append(f"❌ CRITICAL: {method_name}() missing idempotency check! Can cause double operations.")
    
    return errors, warnings


def phase4_insufficient_balance_checks():
    """PHASE 4: Validate insufficient balance handling."""
    print("\n" + "="*80)
    print("PHASE 4: Insufficient Balance Checks")
    print("="*80)
    
    errors = []
    warnings = []
    
    from app.database import services
    
    # Check hold() validates balance
    hold_source = inspect.getsource(services.WalletService.hold)
    
    if "wallet['balance_rub'] < amount_rub" in hold_source or "balance_rub < " in hold_source:
        print("✅ hold() validates balance before holding")
    else:
        errors.append("❌ CRITICAL: hold() doesn't check balance! Allows overdraft.")
    
    if "FOR UPDATE" in hold_source:
        print("✅ hold() uses row locking (FOR UPDATE) to prevent race conditions")
    else:
        warnings.append("⚠️ WARNING: hold() may have race conditions without row locking")
    
    # Check charge() validates hold exists
    charge_source = inspect.getsource(services.WalletService.charge)
    
    if "wallet['hold_rub'] < amount_rub" in charge_source or "hold_rub < " in charge_source:
        print("✅ charge() validates hold exists before charging")
    else:
        errors.append("❌ CRITICAL: charge() doesn't check hold! Can charge from non-existent hold.")
    
    return errors, warnings


def phase5_reserve_balance_flag():
    """PHASE 5: Check reserve_balance usage."""
    print("\n" + "="*80)
    print("PHASE 5: Reserve Balance Flag Usage")
    print("="*80)
    
    errors = []
    warnings = []
    
    # Check create_pending_charge
    create_pending_source = inspect.getsource(charges.ChargeManager.create_pending_charge)
    
    if "reserve_balance" in create_pending_source:
        print("✅ create_pending_charge() supports reserve_balance flag")
        
        # Check if it actually holds funds
        if "wallet_service.hold" in create_pending_source:
            print("✅ reserve_balance=True triggers wallet_service.hold()")
        else:
            warnings.append("⚠️ WARNING: reserve_balance flag exists but doesn't call hold()")
    else:
        warnings.append("⚠️ WARNING: create_pending_charge() missing reserve_balance flag")
    
    # Check if insufficient balance is handled
    if "insufficient_balance" in create_pending_source:
        print("✅ create_pending_charge() returns insufficient_balance status")
    else:
        errors.append("❌ CRITICAL: create_pending_charge() doesn't handle insufficient balance!")
    
    return errors, warnings


def phase6_refund_logic():
    """PHASE 6: Validate refund/release logic."""
    print("\n" + "="*80)
    print("PHASE 6: Refund/Release Logic")
    print("="*80)
    
    errors = []
    warnings = []
    
    # Check release_charge implementation
    release_source = inspect.getsource(charges.ChargeManager.release_charge)
    
    if "wallet_service.release" in release_source:
        print("✅ release_charge() calls wallet_service.release() to return funds")
    else:
        errors.append("❌ CRITICAL: release_charge() doesn't call wallet_service.release()! Funds not returned.")
    
    # Check idempotency
    if "task_id in self._released_charges" in release_source:
        print("✅ release_charge() is idempotent (checks _released_charges)")
    else:
        errors.append("❌ CRITICAL: release_charge() not idempotent! Can release funds twice.")
    
    # Check refund vs release distinction
    from app.database import services
    refund_source = inspect.getsource(services.WalletService.refund)
    release_wallet_source = inspect.getsource(services.WalletService.release)
    
    if refund_source != release_wallet_source:
        print("✅ refund() and release() are different operations")
    else:
        warnings.append("⚠️ WARNING: refund() and release() have identical implementations")
    
    return errors, warnings


def main():
    """Run all payment validation phases."""
    print("\n" + "="*80)
    print("🔍 PRODUCTION CHECK: Payments System (Static Analysis)")
    print("="*80)
    
    all_errors = []
    all_warnings = []
    
    # Run phases
    phases = [
        ("Free Tier Detection", phase1_free_tier),
        ("Double Charge Analysis", phase2_double_charge_analysis),
        ("Idempotency Patterns", phase3_idempotency_patterns),
        ("Insufficient Balance Checks", phase4_insufficient_balance_checks),
        ("Reserve Balance Flag", phase5_reserve_balance_flag),
        ("Refund/Release Logic", phase6_refund_logic),
    ]
    
    for name, phase_func in phases:
        try:
            errors, warnings = phase_func()
            all_errors.extend(errors)
            all_warnings.extend(warnings)
        except Exception as e:
            all_errors.append(f"❌ CRITICAL: Phase '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print("📊 SUMMARY")
    print("="*80)
    
    if all_errors:
        print(f"\n❌ CRITICAL ERRORS: {len(all_errors)}")
        for error in all_errors:
            print(f"  {error}")
    
    if all_warnings:
        print(f"\n⚠️  WARNINGS: {len(all_warnings)}")
        for warning in all_warnings:
            print(f"  {warning}")
    
    if not all_errors and not all_warnings:
        print("\n✅ ALL CHECKS PASSED - Payment system is PRODUCTION READY")
        return 0
    elif not all_errors:
        print("\n⚠️  WARNINGS FOUND - Review before production")
        return 0
    else:
        print("\n❌ CRITICAL ERRORS FOUND - FIX BEFORE PRODUCTION")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
