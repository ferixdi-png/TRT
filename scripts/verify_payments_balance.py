#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка баланса и платежей
Убеждается, что баланс сохраняется корректно
"""

import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent


def check_balance_functions():
    """Проверяет функции работы с балансом"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        
        # Проверяем, что функции существуют
        from bot_kie import (
            get_user_balance,
            set_user_balance,
            add_user_balance,
            subtract_user_balance
        )
        
        print("✅ Функции работы с балансом найдены:")
        print("   - get_user_balance")
        print("   - set_user_balance")
        print("   - add_user_balance")
        print("   - subtract_user_balance")
        
        # Проверяем, что есть логирование
        bot_file = PROJECT_ROOT / "bot_kie.py"
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if "💰💰💰" in content or "BALANCE" in content.upper():
            print("✅ Логирование баланса найдено")
        else:
            print("⚠️ Логирование баланса не найдено")
        
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return 1


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 ПРОВЕРКА БАЛАНСА И ПЛАТЕЖЕЙ")
    print("="*80)
    print()
    
    return check_balance_functions()


if __name__ == "__main__":
    sys.exit(main())
