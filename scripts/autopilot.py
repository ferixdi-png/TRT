#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
АВТОПИЛОТ - Автономный цикл улучшений
Сканирует репозиторий, находит проблемы, чинит, проверяет
Завершается ТОЛЬКО НА ЗЕЛЁНОМ
"""

import sys
import subprocess
import os
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent


def run_verify() -> int:
    """Запускает verify_project.py и возвращает код выхода"""
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    
    result = subprocess.run(
        [sys.executable, "scripts/verify_project.py"],
        cwd=PROJECT_ROOT,
        env=env,
        errors='replace'
    )
    return result.returncode


def main():
    """Главная функция - цикл автопилота"""
    print("="*80)
    print("🤖 АВТОПИЛОТ - АВТОНОМНЫЙ ЦИКЛ УЛУЧШЕНИЙ")
    print("="*80)
    print()
    print("Цикл: Сканирование → Проверка → Исправление → Повтор")
    print("Завершается ТОЛЬКО когда все проверки зелёные")
    print()
    
    max_iterations = 10
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'='*80}")
        print(f"🔄 ИТЕРАЦИЯ {iteration}/{max_iterations}")
        print(f"{'='*80}\n")
        
        # Запускаем проверку
        exit_code = run_verify()
        
        if exit_code == 0:
            print("\n" + "="*80)
            print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ - АВТОПИЛОТ ЗАВЕРШЁН")
            print("="*80)
            return 0
        
        print(f"\n⚠️ Итерация {iteration}: Найдены проблемы")
        print("💡 Автопилот требует ручного исправления проблем")
        print("   Запустите: python scripts/verify_project.py")
        print("   Исправьте все FAILED проверки")
        print("   Повторите: python scripts/autopilot.py")
        
        if iteration < max_iterations:
            print(f"\n⏸️ Ожидание исправлений... (итерация {iteration}/{max_iterations})")
            # В реальном автопилоте здесь была бы автоматическая попытка исправления
            # Пока просто сообщаем о необходимости ручного исправления
            break
    
    print("\n" + "="*80)
    print("❌ АВТОПИЛОТ НЕ СМОГ ЗАВЕРШИТЬ ЦИКЛ")
    print("="*80)
    print("Требуется ручное исправление проблем")
    return 1


if __name__ == "__main__":
    sys.exit(main())
