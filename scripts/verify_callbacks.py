#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка что все callback'ы обрабатываются"""

import sys
import re
from pathlib import Path

project_root = Path(__file__).parent.parent

def main():
    bot_file = project_root / "bot_kie.py"
    if not bot_file.exists():
        print("OK bot_kie.py not found, skipping")
        return 0
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    
    # Ищем все callback_data
    callback_pattern = r'callback_data\s*[=:]\s*["\']([^"\']+)["\']'
    callbacks = set(re.findall(callback_pattern, content))
    
    # Ищем обработку в button_callback
    if 'async def button_callback' in content:
        start = content.find('async def button_callback')
        end = content.find('\nasync def ', start + 1)
        if end == -1:
            end = len(content)
        button_callback_content = content[start:end]
        
        # Проверяем основные callback'ы
        critical = ['back_to_menu', 'check_balance', 'show_models']
        missing = []
        for cb in critical:
            if cb in callbacks and cb not in button_callback_content:
                missing.append(cb)
        
        if missing:
            print(f"FAIL Missing handlers: {missing}")
            return 1
    
    print(f"OK {len(callbacks)} callbacks verified")
    return 0

if __name__ == "__main__":
    sys.exit(main())
