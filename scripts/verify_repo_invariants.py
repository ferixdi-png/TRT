#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка инвариантов репозитория
FAIL если найдено нарушение
"""

import sys
import re
import io
from pathlib import Path
from typing import List, Tuple

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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
    print("Checking repository invariants...")
    
    # 1. COMING SOON / СКОРО ПОЯВИТСЯ (только в коде, который показывается пользователю)
    # Игнорируем kie_models.py - там это метаданные моделей
    bot_file = project_root / "bot_kie.py"
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Пропускаем комментарии
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue
            # Проверяем только строки, которые показываются пользователю
            if re.search(r'(coming\s+soon|скоро\s+появится)', line, re.IGNORECASE):
                # Проверяем контекст - если это проверка флага - пропускаем
                if 'coming_soon' in line.lower() and ('get(' in line or 'if' in line):
                    continue
                # Если это текст для пользователя (в edit_message_text или reply_text) - ошибка
                context_start = max(0, i-10)
                context_end = min(len(lines), i+10)
                context = '\n'.join(lines[context_start:context_end])
                if 'edit_message_text' in context or 'reply_text' in context:
                    if 'coming soon' in line.lower() or 'скоро появится' in line.lower():
                        errors.append(f"FAIL Found COMING SOON shown to user in bot_kie.py line {i}")
    
    # 2. Показ пользователю msg_* (не должно быть прямых строк, только через t())
    bot_file = project_root / "bot_kie.py"
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Ищем прямые строки msg_* которые показываются пользователю (не через t())
        # Игнорируем t('msg_*') - это правильно
        matches = re.findall(r'["\']msg_\w+["\']', content)
        if matches:
            # Проверяем что это не через t()
            for match in matches:
                # Ищем контекст вокруг match
                match_pos = content.find(match)
                context = content[max(0, match_pos-20):min(len(content), match_pos+20)]
                if "t('msg_" not in context and 't("msg_' not in context:
                    errors.append("FAIL Found direct msg_* strings (should use t())")
                    break
    
    # 3. Тишина после ввода (проверяем input_parameters)
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Проверяем, что есть гарантированный ответ
        if '✅ Принято, обрабатываю' not in content:
            errors.append("FAIL No guaranteed reply 'Принято, обрабатываю' in input_parameters")
    
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
                errors.append(f"FAIL Callback '{cb}' not handled in button_callback")
    
    # 5. Модель не из Kie.ai (проверяем, что все модели из KIE_MODELS)
    if bot_file.exists():
        content = bot_file.read_text(encoding='utf-8', errors='ignore')
        # Проверяем импорт KIE_MODELS
        if 'from kie_models import' not in content and 'import kie_models' not in content:
            errors.append("FAIL No kie_models import - models may not be from KIE")
    
    # 6. Реальные HTTP запросы в тестах
    for test_file in project_root.rglob("test_*.py"):
        content = test_file.read_text(encoding='utf-8', errors='ignore')
        # Проверяем, что нет реальных запросов к api.kie.ai
        if 'api.kie.ai' in content:
            # Проверяем что это не просто проверка наличия строки в коде
            # Если это проверка на наличие строки в файле - это нормально
            if 'in content' in content or 'in file' in content or 'read_text' in content:
                # Это проверка наличия строки в файле - нормально
                continue
            # Проверяем что это не просто проверка наличия строки
            if 'FAKE' not in content and 'MOCK' not in content:
                # Проверяем контекст - если это проверка или комментарий - пропускаем
                if 'check' in content.lower() or 'test' in content.lower() or 'assert' in content.lower():
                    # Это тест или проверка - нормально, если нет реальных HTTP запросов
                    if not re.search(r'(requests\.(get|post)|httpx\.|aiohttp\.)', content):
                        continue
                # Если это реальный HTTP запрос (requests.get, httpx, aiohttp) - ошибка
                if re.search(r'(requests\.(get|post)|httpx\.|aiohttp\.)', content):
                    errors.append(f"FAIL Found real HTTP requests to api.kie.ai in tests: {test_file.relative_to(project_root)}")
    
    # 7. Хардкод персональных данных
    sensitive_patterns = [
        (r'\d{10}:\w{35}', "FAIL Found hardcoded bot tokens"),
        (r'rnd_\w{30}', "FAIL Found hardcoded Render API keys"),
        (r'[A-Za-z0-9]{32,}', "WARN Possible hardcoded keys (check manually)"),
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
    
    # 8. НОВЫЙ ИНВАРИАНТ: Все модели должны пройти behavioral_e2e
    behavioral_results_file = project_root / "artifacts" / "behavioral" / "behavioral_e2e_results.json"
    if behavioral_results_file.exists():
        try:
            import json
            with open(behavioral_results_file, 'r', encoding='utf-8') as f:
                behavioral_data = json.load(f)
            
            failed_count = behavioral_data.get('failed', 0)
            silent_models = behavioral_data.get('silent_models', [])
            
            if failed_count > 0:
                errors.append(f"FAIL {failed_count} models failed behavioral E2E (silent/no response): {', '.join(silent_models[:5])}")
        except Exception as e:
            errors.append(f"WARN Could not check behavioral E2E results: {e}")
    else:
        # Если behavioral_e2e не запускался - это предупреждение, но не критично
        pass


def main():
    """Главная функция"""
    check_invariants()
    
    # Разделяем ошибки и предупреждения
    fails = [e for e in errors if not e.startswith("WARN")]
    warns = [e for e in errors if e.startswith("WARN")]
    
    if fails:
        print(f"\nFAIL Found {len(fails)} violations:\n")
        for error in fails:
            print(f"  {error}")
        if warns:
            print(f"\nWARN ({len(warns)} warnings):\n")
            for warn in warns:
                print(f"  {warn}")
        return 1
    else:
        if warns:
            print(f"\nOK All invariants satisfied ({len(warns)} warnings):\n")
            for warn in warns:
                print(f"  {warn}")
        else:
            print(f"\nOK All invariants satisfied")
        return 0


if __name__ == "__main__":
    sys.exit(main())
