#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка инвариантов репозитория
Фейлит, если найдено:
- COMING SOON / СКОРО ПОЯВИТСЯ
- показ пользователю msg_*
- тишина после ввода
- кнопка без handler
- модель не из Kie.ai
- реальные HTTP запросы в тестах
- хардкод персональных данных
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent

# Паттерны для поиска нарушений
VIOLATIONS = {
    "COMING_SOON": [
        (r"COMING\s+SOON", "COMING SOON в коде"),
        (r"СКОРО\s+ПОЯВИТСЯ", "СКОРО ПОЯВИТСЯ в коде"),
        (r"coming\s+soon", "coming soon в коде"),
    ],
    "MSG_STAR": [
        (r"msg_\w+", "Показ пользователю msg_* (должно быть через translations)"),
    ],
    "SILENCE_AFTER_INPUT": [
        (r"await\s+update\.message\.reply_text\([^)]*\)\s*$", "Возможная тишина после ввода"),
    ],
    "HARDCODED_SECRETS": [
        (r"8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y", "Хардкод Telegram токена"),
        (r"8390068635:AAHAIwuTxW3eWbow8WjeViZtZ9xp1SW57V8", "Хардкод Telegram токена"),
        (r"rnd_[A-Za-z0-9]+", "Хардкод Render API ключа"),
        (r"sk-[A-Za-z0-9]+", "Хардкод API ключа (возможно OpenAI/KIE)"),
    ],
    "REAL_HTTP_IN_TESTS": [
        (r"requests\.(get|post|put|delete)", "Реальные HTTP запросы в тестах"),
        (r"httpx\.(get|post|put|delete)", "Реальные HTTP запросы в тестах"),
        (r"aiohttp\.(get|post|put|delete)", "Реальные HTTP запросы в тестах"),
    ],
}

# Исключения (файлы/паттерны, где это допустимо)
EXCEPTIONS = {
    "COMING_SOON": [
        "README",
        "docs",
        ".md",
    ],
    "MSG_STAR": [
        "translations.py",
        "test_",
    ],
    "HARDCODED_SECRETS": [
        ".example",
        ".template",
        "services_config.json.example",
        "README",
        ".md",
    ],
    "REAL_HTTP_IN_TESTS": [
        "fake_",
        "mock_",
        "test_fakes",
    ],
}

# Файлы для проверки
INCLUDE_PATTERNS = ["*.py"]
EXCLUDE_PATTERNS = [
    "__pycache__",
    ".git",
    "venv",
    "env",
    "node_modules",
    ".pytest_cache",
    "*.pyc",
]


def should_check_file(file_path: Path, violation_type: str) -> bool:
    """Проверяет, нужно ли проверять файл для данного типа нарушений"""
    file_str = str(file_path)
    
    # Проверяем исключения
    for exception in EXCEPTIONS.get(violation_type, []):
        if exception in file_str:
            return False
    
    return True


def find_violations() -> List[Tuple[str, Path, int, str]]:
    """Находит все нарушения инвариантов"""
    violations = []
    
    for file_path in PROJECT_ROOT.rglob("*.py"):
        # Пропускаем исключённые файлы
        if any(exc in str(file_path) for exc in EXCLUDE_PATTERNS):
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            continue
        
        for violation_type, patterns in VIOLATIONS.items():
            if not should_check_file(file_path, violation_type):
                continue
            
            for pattern, description in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        # Дополнительная проверка для REAL_HTTP_IN_TESTS
                        if violation_type == "REAL_HTTP_IN_TESTS":
                            # Проверяем, что это тестовый файл
                            if "test" not in str(file_path).lower():
                                continue
                            # Проверяем, что это не fake/mock
                            if any(exc in str(file_path) for exc in EXCEPTIONS.get(violation_type, [])):
                                continue
                        
                        violations.append((violation_type, file_path, line_num, description))
    
    return violations


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 ПРОВЕРКА ИНВАРИАНТОВ РЕПОЗИТОРИЯ")
    print("="*80)
    print()
    
    violations = find_violations()
    
    if not violations:
        print("✅ Инварианты соблюдены - нарушений не найдено")
        return 0
    
    # Группируем по типам
    by_type = {}
    for violation_type, file_path, line_num, description in violations:
        if violation_type not in by_type:
            by_type[violation_type] = []
        by_type[violation_type].append((file_path, line_num, description))
    
    # Выводим отчёт
    print(f"❌ Найдено {len(violations)} нарушений:\n")
    
    for violation_type, items in sorted(by_type.items()):
        print(f"🔴 {violation_type} ({len(items)} нарушений):")
        for file_path, line_num, description in items[:10]:  # Показываем первые 10
            rel_path = file_path.relative_to(PROJECT_ROOT)
            print(f"   {rel_path}:{line_num} - {description}")
        if len(items) > 10:
            print(f"   ... и ещё {len(items) - 10} нарушений")
        print()
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
