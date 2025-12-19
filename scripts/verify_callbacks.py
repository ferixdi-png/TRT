#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка, что все callback'ы имеют обработчики
"""

import sys
import re
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent


def extract_callbacks() -> set:
    """Извлекает все callback_data из кода"""
    callbacks = set()
    bot_file = PROJECT_ROOT / "bot_kie.py"
    
    if not bot_file.exists():
        return callbacks
    
    with open(bot_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем callback_data
    patterns = [
        r'callback_data\s*=\s*["\']([^"\']+)["\']',
        r'callback_data\s*=\s*f["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            callback = match.group(1)
            if '{' not in callback and '}' not in callback:
                callbacks.add(callback)
    
    return callbacks


def extract_handlers() -> set:
    """Извлекает все обработчики"""
    handlers = set()
    bot_file = PROJECT_ROOT / "bot_kie.py"
    
    if not bot_file.exists():
        return handlers
    
    with open(bot_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем обработку в button_callback
    patterns = [
        r'if\s+data\s*==\s*["\']([^"\']+)["\']',
        r'elif\s+data\s*==\s*["\']([^"\']+)["\']',
        r'if\s+data\.startswith\(["\']([^"\']+)["\']',
        r'elif\s+data\.startswith\(["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            callback = match.group(1)
            handlers.add(callback)
    
    return handlers


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 ПРОВЕРКА CALLBACK'ОВ")
    print("="*80)
    print()
    
    callbacks = extract_callbacks()
    handlers = extract_handlers()
    
    print(f"📊 Callback'ов найдено: {len(callbacks)}")
    print(f"📊 Обработчиков найдено: {len(handlers)}")
    print()
    
    # Проверяем необработанные callback'ы
    unhandled = callbacks - handlers
    
    # Исключаем префиксы (например, "select_model:" обрабатывается через startswith)
    prefix_handlers = {h for h in handlers if h.endswith(':')}
    
    # Также проверяем множественные условия (например, "show_models" or "all_models")
    bot_file = PROJECT_ROOT / "bot_kie.py"
    if bot_file.exists():
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # Ищем паттерны типа "data == 'x' or data == 'y'"
        for match in re.finditer(r'data\s*==\s*["\']([^"\']+)["\']\s+or\s+data\s*==\s*["\']([^"\']+)["\']', content):
            handler1, handler2 = match.groups()
            if handler1 in unhandled:
                unhandled.remove(handler1)
            if handler2 in unhandled:
                unhandled.remove(handler2)
    
    truly_unhandled = []
    for callback in unhandled:
        # Проверяем, не обрабатывается ли через префикс
        handled_by_prefix = any(callback.startswith(prefix) for prefix in prefix_handlers)
        if not handled_by_prefix:
            truly_unhandled.append(callback)
    
    if truly_unhandled:
        print(f"⚠️ Найдено {len(truly_unhandled)} необработанных callback'ов:")
        for callback in sorted(truly_unhandled)[:20]:
            print(f"   - {callback}")
        if len(truly_unhandled) > 20:
            print(f"   ... и ещё {len(truly_unhandled) - 20}")
        return 1
    else:
        print("✅ Все callback'ы обработаны")
        return 0


if __name__ == "__main__":
    sys.exit(main())
