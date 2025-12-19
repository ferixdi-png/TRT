#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка инвариантов репозитория
FAIL если найдено нарушение
"""

import sys
import re
from pathlib import Path
from typing import List, Tuple

RED = '\033[91m'
GREEN = '\033[92m'
RESET = '\033[0m'

project_root = Path(__file__).parent.parent
errors: List[str] = []


def check_file(file_path: Path, pattern: str, error_msg: str):
    """Проверяет файл на наличие паттерна"""
    try:
        if not file_path.exists():
            return
        
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        if re.search(pattern, content, re.IGNORECASE):
            errors.append(f"{error_msg}: {file_path.relative_to(project_root)}")
    except Exception as e:
        errors.append(f"Ошибка проверки {file_path}: {e}")


def check_invariants():
    """Проверяет все инварианты"""
    print("🔍 Проверка инвариантов репозитория...")
    
    # 1. COMING SOON / СКОРО ПОЯВИТСЯ
    for py_file in project_root.rglob("*.py"):
        if "test" in str(py_file) or "scripts" in str(py_file):
            continue
        check_file(
            py_file,
            r'(coming\s+soon|скоро\s+появится|в\s+разработке)',
            "❌ Найдено 'COMING SOON' / 'СКОРО ПОЯВИТСЯ'"
        )
    
    # 2. Показ пользователю msg_* (не должно быть в коде)
    bot_file = project_root / "bot_kie.py"
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Ищем прямые строки msg_* которые показываются пользователю
        if re.search(r'["\']msg_\w+["\']', content):
            errors.append("❌ Найдены прямые msg_* строки (должны быть через t())")
    
    # 3. Тишина после ввода (проверяем input_parameters)
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Проверяем, что есть гарантированный ответ
        if '✅ Принято, обрабатываю' not in content:
            errors.append("❌ Нет гарантированного ответа '✅ Принято, обрабатываю' в input_parameters")
    
    # 4. Кнопка без handler (проверяем через callback_data)
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Ищем все callback_data
        callback_pattern = r'callback_data\s*[=:]\s*["\']([^"\']+)["\']'
        callbacks = set(re.findall(callback_pattern, content))
        
        # Проверяем, что есть обработка в button_callback
        button_callback_content = ""
        if 'async def button_callback' in content:
            start = content.find('async def button_callback')
            # Берем функцию до следующей async def
            end = content.find('\nasync def ', start + 1)
            if end == -1:
                end = len(content)
            button_callback_content = content[start:end]
        
        # Проверяем основные callback'ы
        critical_callbacks = ['back_to_menu', 'check_balance', 'show_models', 'all_models']
        for cb in critical_callbacks:
            if cb in callbacks and cb not in button_callback_content:
                errors.append(f"❌ Callback '{cb}' не обрабатывается в button_callback")
    
    # 5. Модель не из Kie.ai (проверяем, что все модели из KIE_MODELS)
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Проверяем импорт KIE_MODELS
        if 'from kie_models import' not in content and 'import kie_models' not in content:
            errors.append("❌ Нет импорта kie_models - модели могут быть не из KIE")
    
    # 6. Реальные HTTP запросы в тестах
    for test_file in project_root.rglob("test_*.py"):
        content = test_file.read_text(encoding='utf-8', errors='ignore')
        # Проверяем, что нет реальных запросов к api.kie.ai
        if 'api.kie.ai' in content and 'FAKE' not in content and 'MOCK' not in content:
            errors.append(f"❌ Найдены реальные запросы к api.kie.ai в тестах: {test_file.relative_to(project_root)}")
    
    # 7. Хардкод персональных данных
    sensitive_patterns = [
        (r'\d{10}:\w{35}', "❌ Найдены хардкод токены бота"),
        (r'rnd_\w{30}', "❌ Найдены хардкод Render API ключи"),
        (r'[A-Za-z0-9]{32,}', "⚠️ Возможные хардкод ключи (проверьте вручную)"),
    ]
    
    for py_file in project_root.rglob("*.py"):
        if "test" in str(py_file) or "scripts" in str(py_file) or ".git" in str(py_file):
            continue
        
        content = py_file.read_text(encoding='utf-8', errors='ignore')
        for pattern, msg in sensitive_patterns:
            matches = re.findall(pattern, content)
            # Игнорируем комментарии и строки с os.getenv
            for match in matches:
                line_num = content[:content.find(match)].count('\n') + 1
                line = content.split('\n')[line_num - 1]
                if 'os.getenv' not in line and 'os.environ' not in line and not line.strip().startswith('#'):
                    errors.append(f"{msg}: {py_file.relative_to(project_root)}:{line_num}")


def main():
    """Главная функция"""
    check_invariants()
    
    if errors:
        print(f"\n{RED}❌ НАЙДЕНО {len(errors)} НАРУШЕНИЙ:{RESET}\n")
        for error in errors:
            print(f"  {error}")
        return 1
    else:
        print(f"\n{GREEN}✅ ВСЕ ИНВАРИАНТЫ СОБЛЮДЕНЫ{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
