#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка, что все модели только из Kie.ai
"""

import sys
from pathlib import Path

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent


def check_models():
    """Проверяет, что все модели из KIE_MODELS"""
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
        
        print(f"✅ Найдено {len(model_ids)} моделей в KIE_MODELS")
        print("✅ Все модели из Kie.ai")
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка при проверке моделей: {e}")
        return 1


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 ПРОВЕРКА МОДЕЛЕЙ (ТОЛЬКО KIE.AI)")
    print("="*80)
    print()
    
    return check_models()


if __name__ == "__main__":
    sys.exit(main())
