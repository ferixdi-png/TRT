#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTOPILOT ONE COMMAND - Единая команда для полного цикла автопилота
Объединяет все проверки и исправления в один запуск
"""

import sys
import subprocess
import os
import io
from pathlib import Path

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
os.chdir(project_root)

def run_command(cmd: list, description: str) -> bool:
    """Запускает команду и возвращает успех"""
    print(f"\n{'='*80}")
    print(f"[AUTOPILOT] {description}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"[PASS] {description}")
            if result.stdout:
                print(result.stdout[:500])
            return True
        else:
            print(f"[FAIL] {description}")
            if result.stdout:
                print(result.stdout[:500])
            if result.stderr:
                print(result.stderr[:500])
            return False
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {description}")
        return False
    except Exception as e:
        print(f"[ERROR] {description}: {e}")
        return False


def main():
    """Главная функция - полный цикл автопилота"""
    print("\n" + "="*80)
    print("AUTOPILOT ONE COMMAND - Полный цикл")
    print("="*80)
    
    steps = [
        (["python", "scripts/preflight_checks.py"], "Preflight checks"),
        (["python", "scripts/verify_project.py"], "Verify project"),
        (["python", "scripts/behavioral_e2e.py"], "Behavioral E2E"),
    ]
    
    results = []
    for cmd, desc in steps:
        success = run_command(cmd, desc)
        results.append((desc, success))
        if not success:
            print(f"\n❌ FAILED: {desc}")
            print("Stopping autopilot - fix errors and rerun")
            return 1
    
    # Итоговый отчёт
    print("\n" + "="*80)
    print("AUTOPILOT SUMMARY")
    print("="*80)
    
    all_passed = all(success for _, success in results)
    
    for desc, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} {desc}")
    
    if all_passed:
        print("\n[SUCCESS] ALL CHECKS PASSED - READY FOR DEPLOY")
        return 0
    else:
        print("\n[FAIL] SOME CHECKS FAILED - FIX ERRORS BEFORE DEPLOY")
        return 1


if __name__ == "__main__":
    sys.exit(main())
