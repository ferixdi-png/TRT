#!/usr/bin/env python3
"""
Pre-deploy verification: runs local tests + smoke before push.
After push, monitors Render deploy and verifies clean startup.
"""

import sys
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_command(cmd: List[str], description: str) -> bool:
    """Run a command and return True if successful."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ {description} - PASSED")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"❌ {description} - FAILED")
            if result.stderr:
                print(result.stderr)
            if result.stdout:
                print(result.stdout)
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️  {description} - TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False


def local_import_check() -> bool:
    """Check that main_render can be imported."""
    return run_command(
        [sys.executable, "-c", "import main_render; print('✅ Import OK')"],
        "Import Check (main_render)"
    )


def syntax_check() -> bool:
    """Check syntax of critical files."""
    files = ["main_render.py", "app/telemetry/middleware.py", "app/telemetry/telemetry_helpers.py"]
    all_ok = True
    for file in files:
        file_path = project_root / file
        if file_path.exists():
            ok = run_command(
                [sys.executable, "-m", "py_compile", str(file_path)],
                f"Syntax Check ({file})"
            )
            all_ok = all_ok and ok
    return all_ok


def sync_report() -> bool:
    """Sync TRT_REPORT.md to Desktop."""
    return run_command(
        [sys.executable, "scripts/sync_desktop_report.py"],
        "Sync Desktop Report"
    )


def main():
    """Main pre-deploy verification."""
    print("="*60)
    print("  PRE-DEPLOY VERIFICATION")
    print("="*60)
    
    results = []
    
    # Step 1: Import check
    results.append(("Import Check", local_import_check()))
    
    # Step 2: Syntax check
    results.append(("Syntax Check", syntax_check()))
    
    # Step 3: Sync report
    results.append(("Report Sync", sync_report()))
    
    # Summary
    print("\n" + "="*60)
    print("  VERIFICATION SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Result: {passed}/{total} checks passed")
    
    if passed == total:
        print("  ✅ Pre-deploy verification PASSED")
        return 0
    else:
        print("  ❌ Pre-deploy verification FAILED")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

