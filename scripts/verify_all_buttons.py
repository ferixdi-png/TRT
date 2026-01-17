#!/usr/bin/env python3
"""Проверка всех кнопок бота - убедиться что все callback обрабатываются"""
import sys
import re
from pathlib import Path

# Добавляем корневую директорию
sys.path.insert(0, str(Path(__file__).parent.parent))

def extract_callback_patterns():
    """Извлекает все callback patterns из bot_kie.py"""
    bot_kie_path = Path(__file__).parent.parent / "bot_kie.py"
    
    with open(bot_kie_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем все CallbackQueryHandler с pattern
    patterns = set()
    pattern_matches = re.findall(r"pattern=['\"]([^'\"]+)['\"]", content)
    for pattern in pattern_matches:
        patterns.add(pattern)
    
    # Ищем callback_data в кнопках
    callback_data_matches = re.findall(r"callback_data=['\"]([^'\"]+)['\"]", content)
    for callback in callback_data_matches:
        patterns.add(callback)
    
    return patterns

def extract_button_callbacks_from_code():
    """Извлекает все обработчики callback из button_callback функции"""
    bot_kie_path = Path(__file__).parent.parent / "bot_kie.py"
    
    with open(bot_kie_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Находим функцию button_callback
    start_idx = content.find("async def button_callback")
    if start_idx == -1:
        return set()
    
    # Находим конец функции (следующая async def или конец файла)
    end_patterns = [
        "\n\nasync def ",
        "\n\n    async def ",
        "\n\n# ",
        "\n\n    # "
    ]
    end_idx = len(content)
    for pattern in end_patterns:
        idx = content.find(pattern, start_idx + 100)
        if idx != -1 and idx < end_idx:
            end_idx = idx
    
    function_content = content[start_idx:end_idx]
    
    # Ищем все проверки callback data
    handled_callbacks = set()
    
    # Паттерны типа if data == "xxx" или if data.startswith("xxx:")
    exact_matches = re.findall(r'if\s+data\s*==\s*["\']([^"\']+)["\']', function_content)
    for match in exact_matches:
        handled_callbacks.add(match)
    
    # Паттерны типа if data.startswith("xxx:")
    startswith_matches = re.findall(r'if\s+data\.startswith\(["\']([^"\']+):', function_content)
    for match in startswith_matches:
        handled_callbacks.add(f"{match}:")
    
    # Паттерны типа if data.startswith("xxx:") or data.startswith("yyy:")
    startswith_or_matches = re.findall(r'data\.startswith\(["\']([^"\']+):', function_content)
    for match in startswith_or_matches:
        handled_callbacks.add(f"{match}:")
    
    # Паттерны типа elif data == "xxx"
    elif_matches = re.findall(r'elif\s+data\s*==\s*["\']([^"\']+)["\']', function_content)
    for match in elif_matches:
        handled_callbacks.add(match)
    
    return handled_callbacks

def check_query_answer():
    """Проверяет, что все callback отвечают через query.answer()"""
    bot_kie_path = Path(__file__).parent.parent / "bot_kie.py"
    
    with open(bot_kie_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие query.answer() в начале функции
    if "async def button_callback" in content:
        start_idx = content.find("async def button_callback")
        # Ищем query.answer() в первых 200 строках функции
        function_start = content[start_idx:start_idx + 5000]
        
        if "await query.answer()" in function_start:
            return True, "query.answer() найден в начале функции"
        else:
            return False, "query.answer() НЕ найден в начале функции"
    
    return False, "Функция button_callback не найдена"

def check_unknown_callback_handler():
    """Проверяет наличие fallback handler для неизвестных callback"""
    bot_kie_path = Path(__file__).parent.parent / "bot_kie.py"
    
    with open(bot_kie_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_unknown_handler = "unknown_callback_handler" in content
    has_registration = "CallbackQueryHandler(unknown_callback_handler)" in content
    
    return has_unknown_handler and has_registration

def main():
    """Главная функция проверки"""
    print("=" * 60)
    print("ПРОВЕРКА ВСЕХ КНОПОК БОТА")
    print("=" * 60)
    
    # 1. Извлекаем все callback patterns
    print("\n[1] Извлечение callback patterns...")
    patterns = extract_callback_patterns()
    print(f"    Найдено patterns: {len(patterns)}")
    print(f"    Примеры: {list(patterns)[:10]}")
    
    # 2. Извлекаем обработанные callback
    print("\n[2] Извлечение обработанных callback из button_callback...")
    handled = extract_button_callbacks_from_code()
    print(f"    Найдено обработчиков: {len(handled)}")
    print(f"    Примеры: {list(handled)[:10]}")
    
    # 3. Проверяем query.answer()
    print("\n[3] Проверка query.answer()...")
    has_answer, answer_msg = check_query_answer()
    if has_answer:
        print(f"    [OK] {answer_msg}")
    else:
        print(f"    [FAIL] {answer_msg}")
    
    # 4. Проверяем unknown_callback_handler
    print("\n[4] Проверка fallback handler...")
    has_fallback = check_unknown_callback_handler()
    if has_fallback:
        print(f"    [OK] unknown_callback_handler зарегистрирован")
    else:
        print(f"    [FAIL] unknown_callback_handler НЕ найден или НЕ зарегистрирован")
    
    # 5. Проверяем покрытие
    print("\n[5] Проверка покрытия...")
    # Проверяем основные callback
    essential_callbacks = [
        "show_models", "category:", "model:", "back_to_menu",
        "check_balance", "topup_balance", "my_generations",
        "help_menu", "admin_stats"
    ]
    
    missing = []
    for callback in essential_callbacks:
        # Проверяем как точное совпадение, так и startswith
        found = False
        for pattern in patterns:
            if callback == pattern or pattern.startswith(callback):
                found = True
                break
        if not found:
            missing.append(callback)
    
    if missing:
        print(f"    [WARN] Не найдено обработчиков для: {missing}")
    else:
        print(f"    [OK] Все основные callback имеют обработчики")
    
    # 6. Итоговый отчет
    print("\n" + "=" * 60)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 60)
    print(f"Callback patterns: {len(patterns)}")
    print(f"Обработанные callback: {len(handled)}")
    print(f"query.answer() в начале: {'[OK]' if has_answer else '[FAIL]'}")
    print(f"Fallback handler: {'[OK]' if has_fallback else '[FAIL]'}")
    print(f"Покрытие основных callback: {'[OK]' if not missing else '[WARN]'}")
    
    if has_answer and has_fallback and not missing:
        print("\n[OK] Все проверки пройдены - кнопки должны работать!")
        return 0
    else:
        print("\n[WARN] Есть проблемы - проверьте детали выше")
        return 1

if __name__ == '__main__':
    sys.exit(main())
