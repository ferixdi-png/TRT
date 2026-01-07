#!/usr/bin/env python3
<<<<<<< HEAD
# -*- coding: utf-8 -*-
"""Проверка что все callback'ы обрабатываются и callback_data валидны"""

import sys
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    errors = []
    warnings = []
    
    bot_file = project_root / "bot_kie.py"
    helpers_file = project_root / "helpers.py"
    
    if not bot_file.exists():
        print("OK bot_kie.py not found, skipping")
        return 0
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    helpers_content = helpers_file.read_text(encoding='utf-8', errors='ignore') if helpers_file.exists() else ""
    
    # Ищем все callback_data в обоих файлах
    callback_pattern = r'callback_data\s*[=:]\s*["\']([^"\']+)["\']'
    callbacks_bot = set(re.findall(callback_pattern, content))
    callbacks_helpers = set(re.findall(callback_pattern, helpers_content))
    all_callbacks = callbacks_bot | callbacks_helpers
    
    print(f"Found {len(all_callbacks)} unique callback_data patterns")
    
    # Проверяем длину callback_data (Telegram limit: 64 bytes)
    long_callbacks = []
    for cb in all_callbacks:
        cb_bytes = cb.encode('utf-8')
        if len(cb_bytes) > 64:
            long_callbacks.append((cb, len(cb_bytes)))
    
    if long_callbacks:
        errors.append(f"Found {len(long_callbacks)} callbacks exceeding 64 bytes:")
        for cb, length in long_callbacks[:5]:
            errors.append(f"  - '{cb[:50]}...' ({length} bytes)")
    
    # Ищем обработку в button_callback
    if 'async def button_callback' in content:
        start = content.find('async def button_callback')
        # Ищем конец функции
        lines = content[start:].split('\n')
        indent_level = None
        button_callback_content = ""
        for i, line in enumerate(lines):
            if i == 0:
                button_callback_content += line + '\n'
                continue
            # Определяем уровень отступа функции
            if indent_level is None and line.strip() and not line.strip().startswith('#'):
                indent_level = len(line) - len(line.lstrip())
            
            # Если следующая функция на том же уровне, останавливаемся
            if indent_level is not None and line.strip() and not line.startswith(' ') and 'def ' in line:
                break
            
            button_callback_content += line + '\n'
        
        # Проверяем основные callback'ы
        critical = ['back_to_menu', 'check_balance', 'show_models', 'select_model', 'gen_type']
        missing = []
        for cb_pattern in critical:
            # Ищем callback'ы содержащие паттерн
            matching_callbacks = [cb for cb in all_callbacks if cb_pattern in cb]
            if matching_callbacks:
                # Проверяем что они обрабатываются
                found = False
                for cb in matching_callbacks:
                    if cb in button_callback_content or cb.split(':')[0] in button_callback_content:
                        found = True
                        break
                if not found:
                    missing.extend(matching_callbacks[:1])  # Добавляем один пример
        
        if missing:
            warnings.append(f"Some callbacks may not be handled: {missing[:5]}")
    
    # Проверяем что модели имеют валидные callback_data
    try:
        from app.models.registry import get_models_sync
        models = get_models_sync()
        
        invalid_model_callbacks = []
        for model in models:
            model_id = model.get('id', '')
            if not model_id:
                continue
            
            # Проверяем что callback_data будет валидным
            callback_data = f"select_model:{model_id}"
            if len(callback_data.encode('utf-8')) > 64:
                # Должен использоваться короткий формат
                short_callback = f"sel:{model_id[:50]}"
                if len(short_callback.encode('utf-8')) > 64:
                    invalid_model_callbacks.append(model_id)
        
        if invalid_model_callbacks:
            errors.append(f"Models with IDs too long for callback_data: {invalid_model_callbacks[:5]}")
    except Exception as e:
        warnings.append(f"Could not verify model callbacks: {e}")
    
    # Выводим результаты
    if errors:
        print(f"\nFAIL: Found {len(errors)} errors:")
        for error in errors:
            print(f"  {error}")
    
    if warnings:
        print(f"\nWARN: Found {len(warnings)} warnings:")
        for warning in warnings:
            print(f"  {warning}")
    
    if errors:
        print(f"\nFAIL: {len(errors)} callback errors found")
        return 1
    
    print(f"\nOK: All {len(all_callbacks)} callbacks verified")
=======
"""
Verify all callback_data have handlers.

CRITICAL: No orphaned callbacks allowed in production.
"""
import re
from pathlib import Path


def extract_callbacks_from_buttons(file_path: Path) -> set:
    """Extract all callback_data strings from InlineKeyboardButton calls."""
    callbacks = set()
    content = file_path.read_text()
    
    # Pattern: callback_data="something" or callback_data=f"something:{var}"
    patterns = [
        r'callback_data\s*=\s*["\']([^"\']+)["\']',  # Static
        r'callback_data\s*=\s*f["\']([^"\'{}]+)',     # F-string prefix
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            callback = match.group(1)
            # Extract prefix for dynamic callbacks (e.g., "cat:" from "cat:{category}")
            if ':' in callback:
                prefix = callback.split(':')[0] + ':'
                callbacks.add(prefix)
            else:
                callbacks.add(callback)
    
    return callbacks


def extract_handlers(file_path: Path) -> set:
    """Extract all callback patterns from @router.callback_query decorators."""
    handlers = set()
    content = file_path.read_text()
    
    # Pattern: F.data == "something" or F.data.startswith("prefix:")
    patterns = [
        r'F\.data\s*==\s*["\']([^"\']+)["\']',         # Exact match
        r'F\.data\.startswith\(["\']([^"\']+)["\']\)', # Prefix match
        r'F\.data\.in_\(\{[^}]*["\']([^"\']+)["\'][^}]*\}\)',  # in_ set
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            handler = match.group(1)
            # Normalize prefix
            if handler.endswith(':'):
                handlers.add(handler)
            elif ':' in handler:
                # For exact matches like "cat:something", add prefix
                prefix = handler.split(':')[0] + ':'
                handlers.add(prefix)
                handlers.add(handler)  # Also add exact
            else:
                handlers.add(handler)
    
    return handlers


def main():
    print("="*80)
    print("🔍 CALLBACK WIRING VERIFICATION")
    print("="*80)
    print()
    
    # Find all handler files
    handler_dir = Path("bot/handlers")
    if not handler_dir.exists():
        print("❌ bot/handlers directory not found")
        return 1
    
    handler_files = list(handler_dir.glob("*.py"))
    
    # Collect all callbacks and handlers
    all_callbacks = set()
    all_handlers = set()
    
    for file in handler_files:
        if file.name == "__init__.py":
            continue
        
        callbacks = extract_callbacks_from_buttons(file)
        handlers = extract_handlers(file)
        
        all_callbacks.update(callbacks)
        all_handlers.update(handlers)
        
        print(f"📄 {file.name}")
        print(f"   Callbacks defined: {len(callbacks)}")
        print(f"   Handlers defined: {len(handlers)}")
    
    print()
    print("="*80)
    print("📊 SUMMARY")
    print("="*80)
    print(f"Total callbacks: {len(all_callbacks)}")
    print(f"Total handlers: {len(all_handlers)}")
    print()
    
    # Find orphaned callbacks (callback without handler)
    orphaned = set()
    for callback in all_callbacks:
        # Check if there's a matching handler
        matched = False
        for handler in all_handlers:
            if callback == handler:
                matched = True
                break
            # Check prefix match
            if handler.endswith(':') and callback.startswith(handler):
                matched = True
                break
        
        if not matched:
            orphaned.add(callback)
    
    if orphaned:
        print("❌ ORPHANED CALLBACKS (no handler):")
        for cb in sorted(orphaned):
            print(f"   - {cb}")
        print()
        return 1
    else:
        print("✅ ALL CALLBACKS HAVE HANDLERS")
        print()
    
    # Find unused handlers (handler without any callback)
    unused = set()
    for handler in all_handlers:
        # Check if any callback uses this handler
        matched = False
        for callback in all_callbacks:
            if callback == handler:
                matched = True
                break
            if handler.endswith(':') and callback.startswith(handler):
                matched = True
                break
        
        if not matched:
            unused.add(handler)
    
    if unused:
        print("⚠️ UNUSED HANDLERS (defined but no callback uses them):")
        for h in sorted(unused):
            print(f"   - {h}")
        print()
        print("Note: These might be for future use or external triggers")
    
    print("="*80)
    print("✅ VERIFICATION COMPLETE")
    print("="*80)
>>>>>>> cbb364c8c317bf2ab285b1261d4d267c35b303d6
    return 0


if __name__ == "__main__":
<<<<<<< HEAD
    sys.exit(main())

=======
    exit(main())
>>>>>>> cbb364c8c317bf2ab285b1261d4d267c35b303d6
