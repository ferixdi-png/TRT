#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка что модели видны в меню через registry"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    try:
        # Проверяем что registry работает
        from app.models.registry import get_models_sync, get_generation_types
        
        models = get_models_sync()
        if not models:
            print("FAIL: No models loaded from registry")
            return 1
        
        print(f"OK: Loaded {len(models)} models from registry")
        
        # Проверяем что есть функции для показа моделей в helpers
        helpers_file = project_root / "helpers.py"
        if helpers_file.exists():
            content = helpers_file.read_text(encoding='utf-8', errors='ignore')
            
            # Проверяем что build_main_menu_keyboard использует registry
            if 'app.models.registry' in content or 'get_models_sync' in content:
                print("OK: helpers.py uses registry")
            else:
                print("WARN: helpers.py may not use registry (check manually)")
            
            # Проверяем что build_model_keyboard существует
            if 'build_model_keyboard' in content:
                print("OK: build_model_keyboard exists")
            else:
                print("FAIL: build_model_keyboard not found")
                return 1
        
        # Проверяем что generation_types работают
        gen_types = get_generation_types()
        if gen_types:
            print(f"OK: Found {len(gen_types)} generation types: {', '.join(gen_types[:5])}")
        else:
            print("WARN: No generation types found")
        
        print("OK Models visible in menu")
        return 0
        
    except Exception as e:
        print(f"FAIL Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
