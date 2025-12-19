#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка, что все модели видны в меню
"""

import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent


def check_models_in_menu():
    """Проверяет, что модели доступны в меню"""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from kie_models import KIE_MODELS
        
        if isinstance(KIE_MODELS, dict):
            model_ids = set(KIE_MODELS.keys())
        elif isinstance(KIE_MODELS, list):
            model_ids = {m.get("id") for m in KIE_MODELS}
        else:
            print("❌ KIE_MODELS имеет неожиданный формат")
            return 1
        
        # Проверяем, что есть callback_data для моделей
        bot_file = PROJECT_ROOT / "bot_kie.py"
        if not bot_file.exists():
            print("⚠️ bot_kie.py не найден")
            return 0
        
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем callback_data для моделей
        found_models = set()
        import re
        for match in re.finditer(r'select_model:([^"\']+)', content):
            model_id = match.group(1)
            found_models.add(model_id)
        
        missing = model_ids - found_models
        if missing:
            print(f"⚠️ {len(missing)} моделей не найдено в callback'ах:")
            for model_id in list(missing)[:10]:
                print(f"   - {model_id}")
            if len(missing) > 10:
                print(f"   ... и ещё {len(missing) - 10}")
        else:
            print(f"✅ Все {len(model_ids)} моделей доступны в меню")
        
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
        return 1


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 ПРОВЕРКА МОДЕЛЕЙ В МЕНЮ")
    print("="*80)
    print()
    
    return check_models_in_menu()


if __name__ == "__main__":
    sys.exit(main())
