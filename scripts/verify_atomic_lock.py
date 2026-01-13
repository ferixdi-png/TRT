#!/usr/bin/env python3
"""
Verification: Atomic Delivery Lock Platform-Wide Implementation

Checks:
1. Migration 010 exists and is idempotent
2. Coordinator uses atomic lock correctly
3. Callback handler uses coordinator
4. Polling uses coordinator and exits on lock skip
5. No orphaned delivered_at references
6. State normalization in polling
"""

import re
import sys
from pathlib import Path


def check_migration_010():
    """Verify migration 010 is correct"""
    print("\n[CHECK] Migration 010...")
    
    migration_file = Path('migrations/010_delivery_lock_platform_wide.sql')
    if not migration_file.exists():
        print("❌ Migration 010 does not exist")
        return False
    
    content = migration_file.read_text()
    
    checks = [
        ('delivered_at column for generation_jobs', 
         r'generation_jobs\s+ADD\s+COLUMN\s+delivered_at', 
         content),
        ('delivering_at column for generation_jobs', 
         r'generation_jobs\s+ADD\s+COLUMN\s+delivering_at', 
         content),
        ('Idempotent (IF NOT EXISTS)', 
         'IF NOT EXISTS', 
         content),
        ('Optimized indexes', 
         r'CREATE INDEX.*idx_generation_jobs', 
         content),
    ]
    
    all_ok = True
    for name, pattern, text in checks:
        if re.search(pattern, text, re.IGNORECASE):
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name}")
            all_ok = False
    
    return all_ok


def check_coordinator():
    """Verify delivery coordinator"""
    print("\n[CHECK] Delivery Coordinator...")
    
    coord_file = Path('app/delivery/coordinator.py')
    if not coord_file.exists():
        print("❌ Coordinator module does not exist")
        return False
    
    content = coord_file.read_text()
    
    checks = [
        'deliver_result_atomic',
        'normalize_state',
        'try_acquire_delivery_lock',
        'mark_delivered',
        'DELIVER_LOCK_WIN',
        'DELIVER_LOCK_SKIP',
        'DELIVER_OK',
        'MARK_DELIVERED',
        'DELIVER_FAIL_RELEASED',
        '_deliver_image',
        '_deliver_video',
        '_deliver_audio',
    ]
    
    all_ok = True
    for check in checks:
        if check in content:
            print(f"  ✅ {check}")
        else:
            print(f"  ❌ {check}")
            all_ok = False
    
    return all_ok


def check_callback_handler():
    """Verify callback handler uses coordinator"""
    print("\n[CHECK] Callback Handler...")
    
    main_file = Path('main_render.py')
    if not main_file.exists():
        print("❌ main_render.py does not exist")
        return False
    
    content = main_file.read_text()
    
    checks = [
        ('Uses deliver_result_atomic', 'deliver_result_atomic', content),
        ('Imports from app.delivery', 'from app.delivery import', content),
        ('Passes category parameter', 'category=', content),
    ]
    
    all_ok = True
    for name, pattern, text in checks:
        if pattern in text:
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name}")
            all_ok = False
    
    return all_ok


def check_polling():
    """Verify polling uses coordinator and exits on lock skip"""
    print("\n[CHECK] Polling Loop...")
    
    gen_file = Path('app/kie/generator.py')
    if not gen_file.exists():
        print("❌ generator.py does not exist")
        return False
    
    content = gen_file.read_text()
    
    checks = [
        ('State normalization', 'normalize_state', content),
        ('Uses deliver_result_atomic', 'deliver_result_atomic', content),
        ('Exits on lock skip', 'DELIVER_LOCK_SKIP_POLL_EXIT', content),
        ('Logs success equiv', 'POLL_SUCCESS_EQUIV', content),
        ('Checks already_delivered', 'already_delivered', content),
    ]
    
    all_ok = True
    for name, pattern, text in checks:
        if pattern in text:
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name}")
            all_ok = False
    
    return all_ok


def check_bot_flow():
    """Verify bot flow avoids double sends"""
    print("\n[CHECK] Bot Flow...")
    
    flow_file = Path('bot/handlers/flow.py')
    if not flow_file.exists():
        print("❌ flow.py does not exist")
        return False
    
    content = flow_file.read_text()
    
    checks = [
        ('Checks already_delivered', 'already_delivered', content),
        ('Conditional URL send', 'if already_delivered', content),
    ]
    
    all_ok = True
    for name, pattern, text in checks:
        if pattern in text:
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name}")
            all_ok = False
    
    return all_ok


def check_no_orphaned_references():
    """Static check: no delivered_at used before it exists"""
    print("\n[CHECK] No Orphaned References...")
    
    # This is a basic check - real validation happens at runtime
    migration = Path('migrations/010_delivery_lock_platform_wide.sql')
    if not migration.exists():
        print("❌ Cannot verify - migration 010 missing")
        return False
    
    content = migration.read_text()
    lines = content.split('\n')
    
    # Check that delivered_at column is added before index using it
    delivered_at_line = None
    index_line = None
    
    for i, line in enumerate(lines):
        if 'ADD COLUMN delivered_at' in line:
            delivered_at_line = i
        if 'CREATE INDEX' in line and 'delivered_at' in line:
            index_line = i
    
    if delivered_at_line is None:
        print("  ❌ delivered_at column not added")
        return False
    
    if index_line is None:
        print("  ✅ No index on delivered_at (acceptable)")
        return True
    
    if delivered_at_line < index_line:
        print("  ✅ delivered_at added before index uses it")
        return True
    else:
        print("  ❌ Index created before delivered_at column!")
        return False


def main():
    print("="*60)
    print("ATOMIC DELIVERY LOCK VERIFICATION")
    print("="*60)
    
    results = []
    
    results.append(("Migration 010", check_migration_010()))
    results.append(("Coordinator", check_coordinator()))
    results.append(("Callback Handler", check_callback_handler()))
    results.append(("Polling Loop", check_polling()))
    results.append(("Bot Flow", check_bot_flow()))
    results.append(("No Orphaned Refs", check_no_orphaned_references()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All checks passed!")
        return 0
    else:
        print("\n⚠️ Some checks failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
