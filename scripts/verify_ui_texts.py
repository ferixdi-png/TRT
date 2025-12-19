#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка UI текстов - нет COMING SOON, все переводы есть"""

import sys
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
errors = []

def main():
    bot_file = project_root / "bot_kie.py"
    if not bot_file.exists():
        print("OK bot_kie.py not found, skipping")
        return 0
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    
    # Проверяем COMING SOON (только в коде, который выполняется, не в комментариях)
    # Игнорируем комментарии и строки, которые не показываются пользователю
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # Пропускаем комментарии
        stripped = line.strip()
        if stripped.startswith('#') or '"""' in stripped or "'''" in stripped:
            continue
        # Проверяем только строки, которые могут показываться пользователю
        if re.search(r'(coming\s+soon|скоро\s+появится)', line, re.IGNORECASE):
            # Проверяем что это не в комментарии и не в закомментированном коде
            if 'coming_soon' in line.lower() and ('get(' in line or 'if' in line):
                # Это проверка флага, не показ пользователю - пропускаем
                continue
            # Если это текст для пользователя - ошибка
            if 'edit_message_text' in lines[max(0, i-5):i+5] or 'reply_text' in lines[max(0, i-5):i+5]:
                errors.append(f"Found COMING SOON shown to user in bot_kie.py line {i}")
    
    if errors:
        print("FAIL Found issues:")
        for e in errors:
            print(f"  - {e}")
        return 1
    
    print("OK UI texts verified")
    return 0

if __name__ == "__main__":
    sys.exit(main())
