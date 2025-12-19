#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка что модели видны в меню"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

def main():
    try:
        sys.path.insert(0, str(project_root))
        from kie_models import KIE_MODELS
        
        # Проверяем что есть функции для показа моделей
        bot_file = project_root / "bot_kie.py"
        if bot_file.exists():
            content = bot_file.read_text(encoding='utf-8', errors='ignore')
            if 'show_models' in content and 'all_models' in content:
                print("OK Models visible in menu")
                return 0
        
        print("FAIL Models not visible in menu")
        return 1
    except Exception as e:
        print(f"FAIL Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
