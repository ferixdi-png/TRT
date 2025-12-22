#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTOPILOT — АВТОНОМНО ДО ИДЕАЛА
Полный цикл: логи → инциденты → фиксы → тесты → verify → повтор
"""

import sys
import subprocess
import os
from pathlib import Path

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

project_root = Path(__file__).parent.parent
os.chdir(project_root)


def run_command(cmd: list) -> tuple[int, str, str]:
    """Запускает команду"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Timeout"
    except Exception as e:
        return 1, "", str(e)


def main():
    """Главный цикл автопилота"""
    print("\n" + "="*80)
    print("AUTOPILOT - Автономное исправление до идеала")
    print("="*80)
    
    max_iterations = 20
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'='*80}")
        print(f"Iteration {iteration}/{max_iterations}")
        print(f"{'='*80}")
        
        # 1. Читаем логи Render
        print("\n[1/6] Reading Render logs...")
        code, stdout, stderr = run_command([
            "python", "scripts/read_logs.py", "--since", "60m", "--grep", "ERROR|Traceback"
        ])
        if code != 0:
            print(f"{YELLOW}WARN Failed to read logs: {stderr}{RESET}")
        
        # 2. Парсим инциденты
        print("\n[2/6] Parsing incidents...")
        code, stdout, stderr = run_command(["python", "scripts/parse_logs.py"])
        if code != 0:
            print(f"{YELLOW}WARN Failed to parse logs: {stderr}{RESET}")
        
        # 3. Применяем безопасные фиксы
        print("\n[3/6] Applying safe fixes...")
        code, stdout, stderr = run_command(["python", "scripts/autofix.py"])
        if stdout:
            print(stdout)
        
        # 4. Создаём snapshot меню
        print("\n[4/6] Creating menu snapshot...")
        code, stdout, stderr = run_command(["python", "scripts/snapshot_menu.py"])
        if code != 0:
            print(f"{YELLOW}WARN Failed to snapshot menu: {stderr}{RESET}")
        
        # 5. Запускаем verify
        print("\n[5/6] Running verify_project...")
        code, stdout, stderr = run_command(["python", "scripts/verify_project.py"])
        
        if code == 0:
            print(f"\n{GREEN}ALL CHECKS PASSED!{RESET}")
            print(f"\nFinal output:")
            print(stdout)
            return 0
        
        print(f"\n{RED}Checks failed, continuing...{RESET}")
        if stdout:
            print(stdout[:500])  # Первые 500 символов
    
    print(f"\n{RED}Max iterations reached{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
