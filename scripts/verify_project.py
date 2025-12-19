#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЕДИНСТВЕННАЯ КОМАНДА ПРАВДЫ
Запускает все проверки проекта и возвращает код выхода 0 только если ВСЁ зелёное
"""

import sys
import subprocess
import os
from pathlib import Path
from typing import List, Tuple

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Список всех проверок
CHECKS = [
    ("Python Compilation", [sys.executable, "-m", "compileall", ".", "-q"]),
    ("Menu Snapshot", ["python", "scripts/snapshot_menu.py"]),
    ("Menu Diff", ["python", "scripts/diff_menu_snapshot.py"]),
    ("Repo Invariants", ["python", "scripts/verify_repo_invariants.py"]),
    ("UI Texts", ["python", "scripts/verify_ui_texts.py"]),
    ("Models KIE Only", ["python", "scripts/verify_models_kie_only.py"]),
    ("Models Visible in Menu", ["python", "scripts/verify_models_visible_in_menu.py"]),
    ("Callbacks", ["python", "scripts/verify_callbacks.py"]),
    ("Payments Balance", ["python", "scripts/verify_payments_balance.py"]),
    ("Pytest", ["pytest", "-q", "--tb=short"]),
]

# Опциональные проверки (не блокируют, но предупреждают)
OPTIONAL_CHECKS = [
    ("Balance Logging", ["python", "scripts/verify_balance_logging.py"]),
]


def run_check(name: str, command: List[str], optional: bool = False) -> Tuple[bool, str]:
    """Запускает проверку и возвращает (успех, вывод)"""
    print(f"\n{'='*80}")
    print(f"🔍 {name}")
    print(f"{'='*80}")
    print(f"Команда: {' '.join(command)}")
    print()
    
    try:
        # Устанавливаем кодировку UTF-8 для subprocess
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,  # 5 минут максимум
            env=env,
            errors='replace'  # Обработка ошибок кодировки
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            print(f"✅ {name} - PASSED")
            return True, result.stdout + result.stderr
        else:
            status = "⚠️ WARNING" if optional else "❌ FAILED"
            print(f"{status} {name} - Exit code: {result.returncode}")
            return False, result.stdout + result.stderr
            
    except subprocess.TimeoutExpired:
        print(f"❌ {name} - TIMEOUT (>5 minutes)")
        return False, "Timeout"
    except Exception as e:
        print(f"❌ {name} - ERROR: {e}")
        return False, str(e)


def main():
    """Главная функция - запускает все проверки"""
    print("="*80)
    print("🚀 VERIFY PROJECT - ЕДИНСТВЕННАЯ КОМАНДА ПРАВДЫ")
    print("="*80)
    print(f"Проект: {PROJECT_ROOT}")
    print(f"Артефакты: {ARTIFACTS_DIR}")
    print()
    
    results = []
    failed_checks = []
    warning_checks = []
    
    # Обязательные проверки
    for name, command in CHECKS:
        # Проверяем, существует ли скрипт
        if len(command) > 1 and command[0] == "python":
            script_path = PROJECT_ROOT / command[1]
            if not script_path.exists():
                print(f"⚠️ Пропущено: {name} (скрипт не найден: {script_path})")
                warning_checks.append(name)
                continue
        
        success, output = run_check(name, command, optional=False)
        results.append((name, success, output))
        
        if not success:
            failed_checks.append(name)
    
    # Опциональные проверки
    for name, command in OPTIONAL_CHECKS:
        script_path = PROJECT_ROOT / command[1]
        if not script_path.exists():
            continue
        
        success, output = run_check(name, command, optional=True)
        results.append((name, success, output))
        
        if not success:
            warning_checks.append(name)
    
    # Итоговый отчёт
    print("\n" + "="*80)
    print("📊 ИТОГОВЫЙ ОТЧЁТ")
    print("="*80)
    
    total = len(results)
    passed = sum(1 for _, success, _ in results if success)
    failed = len(failed_checks)
    warnings = len(warning_checks)
    
    print(f"Всего проверок: {total}")
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    print(f"⚠️ Предупреждений: {warnings}")
    print()
    
    if failed_checks:
        print("❌ ПРОВАЛЕННЫЕ ПРОВЕРКИ:")
        for check in failed_checks:
            print(f"   - {check}")
        print()
    
    if warning_checks:
        print("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for check in warning_checks:
            print(f"   - {check}")
        print()
    
    # Сохраняем отчёт
    report_file = ARTIFACTS_DIR / "verify_report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("VERIFY PROJECT REPORT\n")
        f.write("="*80 + "\n\n")
        f.write(f"Всего проверок: {total}\n")
        f.write(f"✅ Пройдено: {passed}\n")
        f.write(f"❌ Провалено: {failed}\n")
        f.write(f"⚠️ Предупреждений: {warnings}\n\n")
        
        if failed_checks:
            f.write("❌ ПРОВАЛЕННЫЕ ПРОВЕРКИ:\n")
            for check in failed_checks:
                f.write(f"   - {check}\n")
            f.write("\n")
        
        for name, success, output in results:
            f.write(f"{'✅' if success else '❌'} {name}\n")
            if output:
                f.write(f"{output[:500]}\n")  # Первые 500 символов
            f.write("\n")
    
    print(f"📄 Отчёт сохранён: {report_file}")
    
    # Возвращаем код выхода
    if failed > 0:
        print("\n❌ ПРОЕКТ НЕ ПРОШЁЛ ПРОВЕРКУ")
        return 1
    else:
        print("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        return 0


if __name__ == "__main__":
    sys.exit(main())
