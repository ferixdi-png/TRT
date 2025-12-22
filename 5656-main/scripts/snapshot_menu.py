#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot всех меню и подменю
Сохраняет artifacts/menu_snapshot.json и artifacts/menu_snapshot.md
"""

import sys
import json
import re
import io
from pathlib import Path
from typing import Dict, List, Set

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
artifacts_dir = project_root / "artifacts"
artifacts_dir.mkdir(exist_ok=True)

bot_file = project_root / "bot_kie.py"


def extract_menus() -> Dict:
    """Извлекает все меню из bot_kie.py"""
    if not bot_file.exists():
        print("❌ bot_kie.py не найден")
        return {}
    
    content = bot_file.read_text(encoding='utf-8', errors='ignore')
    
    menus = {
        "main_menu": [],
        "model_selection": [],
        "generation_types": [],
        "admin_menu": [],
        "payment_menu": [],
        "callbacks": set(),
    }
    
    # Ищем все callback_data
    callback_pattern = r'callback_data\s*[=:]\s*["\']([^"\']+)["\']'
    callbacks = re.findall(callback_pattern, content)
    menus["callbacks"] = sorted(set(callbacks))
    
    # Ищем главное меню
    if 'build_main_menu_keyboard' in content:
        # Извлекаем кнопки из функции
        start = content.find('def build_main_menu_keyboard')
        if start != -1:
            end = content.find('\ndef ', start + 1)
            if end == -1:
                end = len(content)
            menu_func = content[start:end]
            menu_callbacks = re.findall(callback_pattern, menu_func)
            menus["main_menu"] = sorted(set(menu_callbacks))
    
    # Ищем модели из KIE_MODELS
    try:
        sys.path.insert(0, str(project_root))
        from kie_models import KIE_MODELS
        if isinstance(KIE_MODELS, dict):
            menus["models"] = sorted(KIE_MODELS.keys())
        elif isinstance(KIE_MODELS, list):
            menus["models"] = sorted([m.get('id', '') for m in KIE_MODELS if isinstance(m, dict)])
    except:
        menus["models"] = []
    
    return menus


def generate_markdown(menus: Dict) -> str:
    """Генерирует markdown отчёт"""
    md = "# 📋 SNAPSHOT МЕНЮ\n\n"
    md += f"**Дата:** {Path(__file__).stat().st_mtime}\n\n"
    
    md += "## Главное меню\n\n"
    for cb in menus.get("main_menu", []):
        md += f"- `{cb}`\n"
    
    md += "\n## Модели\n\n"
    md += f"Всего моделей: {len(menus.get('models', []))}\n\n"
    for model in menus.get("models", [])[:20]:  # Первые 20
        md += f"- `{model}`\n"
    if len(menus.get("models", [])) > 20:
        md += f"\n... и ещё {len(menus.get('models', [])) - 20} моделей\n"
    
    md += "\n## Все callback'ы\n\n"
    md += f"Всего callback'ов: {len(menus.get('callbacks', []))}\n\n"
    for cb in menus.get("callbacks", []):
        md += f"- `{cb}`\n"
    
    return md


def main():
    """Главная функция"""
    print("Creating menu snapshot...")
    
    menus = extract_menus()
    
    # Сохраняем JSON
    json_file = artifacts_dir / "menu_snapshot.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(menus, f, indent=2, ensure_ascii=False)
    print(f"OK Saved {json_file}")
    
    # Сохраняем Markdown
    md_file = artifacts_dir / "menu_snapshot.md"
    md_content = generate_markdown(menus)
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"OK Saved {md_file}")
    
    print(f"\nStatistics:")
    print(f"  Main menu: {len(menus.get('main_menu', []))} buttons")
    print(f"  Models: {len(menus.get('models', []))}")
    print(f"  Total callbacks: {len(menus.get('callbacks', []))}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
