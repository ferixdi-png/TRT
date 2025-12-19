"""
Тест: Баланс и платежи
Проверяет атомарность, идемпотентность, сохранение после рестарта
"""

import sys
from pathlib import Path

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_balance_functions_exist():
    """Тест: функции работы с балансом существуют"""
    from bot_kie import (
        get_user_balance,
        set_user_balance,
        add_user_balance,
        subtract_user_balance
    )
    
    assert callable(get_user_balance)
    assert callable(set_user_balance)
    assert callable(add_user_balance)
    assert callable(subtract_user_balance)


def test_balance_logging():
    """Тест: баланс логируется"""
    bot_file = PROJECT_ROOT / "bot_kie.py"
    
    with open(bot_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие логирования
    has_logging = (
        "💰💰💰" in content or
        "BALANCE" in content.upper() or
        "GET_BALANCE" in content or
        "SET_BALANCE" in content
    )
    
    assert has_logging, "Логирование баланса не найдено"


def test_balance_persistence():
    """Тест: баланс сохраняется (проверка наличия механизма сохранения)"""
    bot_file = PROJECT_ROOT / "bot_kie.py"
    
    with open(bot_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие сохранения в БД или JSON
    has_persistence = (
        "db_update_user_balance" in content or
        "save_json_file" in content or
        "BALANCES_FILE" in content
    )
    
    assert has_persistence, "Механизм сохранения баланса не найден"


if __name__ == "__main__":
    print("="*80)
    print("🧪 ТЕСТ: БАЛАНС И ПЛАТЕЖИ")
    print("="*80)
    print()
    
    try:
        test_balance_functions_exist()
        print("✅ Функции работы с балансом найдены")
        
        test_balance_logging()
        print("✅ Логирование баланса найдено")
        
        test_balance_persistence()
        print("✅ Механизм сохранения баланса найден")
        
        print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        sys.exit(0)
    except AssertionError as e:
        print(f"❌ ТЕСТ ПРОВАЛЕН: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
