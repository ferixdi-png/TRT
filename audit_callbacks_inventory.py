#!/usr/bin/env python3
"""Инвентаризация всех callback_data в боте."""

import re
from pathlib import Path

def extract_callbacks():
    """Извлечь все callback_data из bot_kie.py."""
    bot_file = Path("/workspaces/TRT/bot_kie.py")
    content = bot_file.read_text()
    
    # Найти все callback_data=
    callback_pattern = r'callback_data\s*=\s*["\']([^"\']+)["\']'
    callbacks_defined = set(re.findall(callback_pattern, content))
    
    # Найти все if data == "..."
    handler_pattern = r'if data\s*==\s*["\']([^"\']+)["\']'
    handlers_defined = set(re.findall(handler_pattern, content))
    
    # Найти startswith handlers
    startswith_pattern = r'if data\.startswith\(["\']([^"\']+)["\']'
    startswith_handlers = set(re.findall(startswith_pattern, content))
    
    return callbacks_defined, handlers_defined, startswith_handlers

def main():
    callbacks, handlers, startswith = extract_callbacks()
    
    print("=" * 80)
    print("CALLBACK DATA INVENTORY")
    print("=" * 80)
    
    # Статические callback_data
    static_callbacks = {cb for cb in callbacks if ':' not in cb and '{' not in cb}
    dynamic_callbacks = callbacks - static_callbacks
    
    print(f"\n📊 СТАТИСТИКА:")
    print(f"  Всего callback_data определено: {len(callbacks)}")
    print(f"  Статических: {len(static_callbacks)}")
    print(f"  Динамических (с :): {len(dynamic_callbacks)}")
    print(f"  Обработчиков if data ==: {len(handlers)}")
    print(f"  Обработчиков startswith: {len(startswith)}")
    
    # Проверить покрытие
    print(f"\n🔍 АНАЛИЗ ПОКРЫТИЯ:")
    
    # Статические без обработчика
    unhandled_static = static_callbacks - handlers
    if unhandled_static:
        print(f"\n⚠️  СТАТИЧЕСКИЕ БЕЗ ОБРАБОТЧИКА ({len(unhandled_static)}):")
        for cb in sorted(unhandled_static)[:20]:
            print(f"    - {cb}")
        if len(unhandled_static) > 20:
            print(f"    ... и еще {len(unhandled_static) - 20}")
    
    # Обработчики без определения
    undefined_handlers = handlers - callbacks
    if undefined_handlers:
        print(f"\n⚠️  ОБРАБОТЧИКИ БЕЗ КНОПОК ({len(undefined_handlers)}):")
        for h in sorted(undefined_handlers)[:20]:
            print(f"    - {h}")
        if len(undefined_handlers) > 20:
            print(f"    ... и еще {len(undefined_handlers) - 20}")
    
    print(f"\n✅ КОРРЕКТНО ОБРАБОТАННЫЕ СТАТИЧЕСКИЕ ({len(static_callbacks & handlers)}):")
    for cb in sorted(static_callbacks & handlers):
        print(f"    - {cb}")
    
    print(f"\n🔄 ДИНАМИЧЕСКИЕ PATTERNS ({len(startswith)}):")
    for pattern in sorted(startswith):
        print(f"    - {pattern}*")
    
    # Проверить динамические
    print(f"\n🔧 ПРИМЕРЫ ДИНАМИЧЕСКИХ CALLBACK_DATA:")
    for cb in sorted(dynamic_callbacks)[:20]:
        print(f"    - {cb}")
    if len(dynamic_callbacks) > 20:
        print(f"    ... и еще {len(dynamic_callbacks) - 20}")
    
    # Найти потенциально битые
    print(f"\n❌ ПОТЕНЦИАЛЬНО БИТЫЕ (нет ни статического, ни startswith):")
    potentially_broken = []
    for cb in sorted(unhandled_static):
        has_handler = any(cb.startswith(pattern) for pattern in startswith)
        if not has_handler:
            potentially_broken.append(cb)
    
    if potentially_broken:
        for cb in potentially_broken[:30]:
            print(f"    - {cb}")
        if len(potentially_broken) > 30:
            print(f"    ... и еще {len(potentially_broken) - 30}")
    else:
        print("    ✅ Все статические callback покрыты!")

if __name__ == "__main__":
    main()
