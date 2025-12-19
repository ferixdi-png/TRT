#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка UI текстов
Убеждается, что нет хардкода текстов, всё через translations
"""

import sys
import re
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent

# Паттерны хардкода текстов (которые должны быть в translations)
HARDCODED_TEXT_PATTERNS = [
    (r'["\'](Главное меню|Main menu)["\']', "Хардкод 'Главное меню'"),
    (r'["\'](Баланс|Balance)["\']', "Хардкод 'Баланс'"),
    (r'["\'](Ошибка|Error)["\']', "Хардкод 'Ошибка'"),
]

# Исключения
EXCEPTIONS = [
    "translations.py",
    "test_",
    ".md",
    "README",
]


def should_check_file(file_path: Path) -> bool:
    """Проверяет, нужно ли проверять файл"""
    file_str = str(file_path)
    return not any(exc in file_str for exc in EXCEPTIONS)


def find_hardcoded_texts() -> list:
    """Находит хардкод текстов"""
    violations = []
    
    for file_path in PROJECT_ROOT.rglob("*.py"):
        if not should_check_file(file_path):
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue
        
        for pattern, description in HARDCODED_TEXT_PATTERNS:
            for match in re.finditer(pattern, content):
                violations.append((file_path, match.group(0), description))
    
    return violations


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 ПРОВЕРКА UI ТЕКСТОВ")
    print("="*80)
    print()
    
    violations = find_hardcoded_texts()
    
    if not violations:
        print("✅ Хардкод текстов не найден")
        return 0
    
    print(f"⚠️ Найдено {len(violations)} потенциальных хардкодов:")
    for file_path, text, description in violations[:20]:
        rel_path = file_path.relative_to(PROJECT_ROOT)
        print(f"   {rel_path}: {text} - {description}")
    
    if len(violations) > 20:
        print(f"   ... и ещё {len(violations) - 20}")
    
    # Не фейлим, только предупреждаем
    return 0


if __name__ == "__main__":
    sys.exit(main())
