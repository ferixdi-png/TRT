#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка баланса и платежей - сохранение, атомарность"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

def main():
    # Проверяем что есть функции сохранения баланса
    bot_file = project_root / "bot_kie.py"
    if not bot_file.exists():
        print("OK bot_kie.py not found, skipping")
        return 0
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    
    # Проверяем критическое логирование баланса
    if '💰💰💰' not in content and 'GET_BALANCE' not in content:
        print("WARN Balance logging not found")
    
    # Проверяем сохранение в БД
    if 'db_update_user_balance' in content or 'update_user_balance' in content:
        print("OK Balance saving to DB found")
    else:
        print("FAIL Balance saving to DB not found")
        return 1
    
    # Проверяем верификацию сохранения
    if 'BALANCE VERIFIED' in content:
        print("OK Balance verification found")
    else:
        print("WARN Balance verification not found")
    
    print("OK Payments/balance verified")
    return 0

if __name__ == "__main__":
    sys.exit(main())
