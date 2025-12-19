#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFY PROJECT — ЕДИНСТВЕННАЯ ПРАВДА
Запускает все проверки проекта
FAIL если хотя бы одна проверка не прошла
"""

import sys
import subprocess
import os
import io
from pathlib import Path
from typing import List, Tuple

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Цвета для вывода
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def run_check(name: str, command: List[str]) -> Tuple[bool, str]:
    """Запускает проверку и возвращает (успех, вывод)"""
    print(f"\n{'='*80}")
    print(f"[CHECK] {name}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=Path(__file__).parent.parent
        )
        
        if result.returncode == 0:
            print(f"{GREEN}[PASS]{RESET}")
            if result.stdout:
                print(result.stdout[:500])  # Первые 500 символов
            return True, result.stdout
        else:
            print(f"{RED}[FAIL]{RESET}")
            if result.stdout:
                print(result.stdout[:500])
            if result.stderr:
                print(result.stderr[:500])
            return False, result.stderr or result.stdout
    except subprocess.TimeoutExpired:
        print(f"{RED}[TIMEOUT]{RESET}")
        return False, "Timeout"
    except Exception as e:
        print(f"{RED}[ERROR]{RESET}: {e}")
        return False, str(e)


def main():
    """Главная функция - запускает все проверки"""
    print("\n" + "="*80)
    print("VERIFY PROJECT - ЕДИНСТВЕННАЯ ПРАВДА")
    print("="*80)
    
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    checks = [
        ("Compile Python", ["python", "-m", "compileall", ".", "-q"]),
        ("Snapshot Menu", ["python", "scripts/snapshot_menu.py"]),
        ("Diff Menu", ["python", "scripts/diff_menu_snapshot.py"]),
        ("Verify Invariants", ["python", "scripts/verify_repo_invariants.py"]),
        ("Verify UI Texts", ["python", "scripts/verify_ui_texts.py"]),
        ("Verify Models KIE Only", ["python", "scripts/verify_models_kie_only.py"]),
        ("Verify Models Visible", ["python", "scripts/verify_models_visible_in_menu.py"]),
        ("Verify Callbacks", ["python", "scripts/verify_callbacks.py"]),
        ("Verify Payments Balance", ["python", "scripts/verify_payments_balance.py"]),
    ]
    
    # Проверяем наличие pytest
    try:
        import pytest
        checks.append(("Run Tests", ["pytest", "-q", "--tb=short"]))
    except ImportError:
        print(f"{YELLOW}WARN pytest not installed, skipping tests{RESET}")
    
    results = []
    for name, command in checks:
        success, output = run_check(name, command)
        results.append((name, success))
        if not success:
            print(f"\n{RED}[FAILED]{RESET}: {name}")
    
    # Итоговый отчёт
    print("\n" + "="*80)
    print("FINAL REPORT")
    print("="*80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = f"{GREEN}[PASS]{RESET}" if success else f"{RED}[FAIL]{RESET}"
        print(f"{status} {name}")
    
    print(f"\n{passed}/{total} checks passed")
    
    if passed == total:
        print(f"\n{GREEN}ALL CHECKS PASSED!{RESET}")
        return 0
    else:
        print(f"\n{RED}THERE ARE ERRORS!{RESET}")
        print(f"{YELLOW}Run: python scripts/autopilot.py{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
