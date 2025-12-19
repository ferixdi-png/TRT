#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сравнение текущего и предыдущего snapshot меню
Сохраняет artifacts/menu_diff.md
"""

import sys
import json
from pathlib import Path
from typing import Dict, Set

project_root = Path(__file__).parent.parent
artifacts_dir = project_root / "artifacts"

current_file = artifacts_dir / "menu_snapshot.json"
previous_file = artifacts_dir / "menu_snapshot_previous.json"


def load_snapshot(file_path: Path) -> Dict:
    """Загружает snapshot"""
    if not file_path.exists():
        return {}
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def diff_snapshots(current: Dict, previous: Dict) -> str:
    """Сравнивает snapshot'ы и возвращает diff"""
    md = "# 🔄 DIFF МЕНЮ\n\n"
    
    # Сравниваем callback'ы
    current_callbacks = set(current.get("callbacks", []))
    previous_callbacks = set(previous.get("callbacks", []))
    
    added = current_callbacks - previous_callbacks
    removed = previous_callbacks - current_callbacks
    
    if added:
        md += "## ➕ Добавлены callback'ы\n\n"
        for cb in sorted(added):
            md += f"- `{cb}`\n"
        md += "\n"
    
    if removed:
        md += "## ➖ Удалены callback'ы\n\n"
        for cb in sorted(removed):
            md += f"- `{cb}`\n"
        md += "\n"
    
    if not added and not removed:
        md += "## ✅ Изменений нет\n\n"
    
    # Сравниваем модели
    current_models = set(current.get("models", []))
    previous_models = set(previous.get("models", []))
    
    added_models = current_models - previous_models
    removed_models = previous_models - current_models
    
    if added_models:
        md += "## ➕ Добавлены модели\n\n"
        for model in sorted(added_models):
            md += f"- `{model}`\n"
        md += "\n"
    
    if removed_models:
        md += "## ➖ Удалены модели\n\n"
        for model in sorted(removed_models):
            md += f"- `{model}`\n"
        md += "\n"
    
    return md


def main():
    """Главная функция"""
    print("🔄 Сравнение snapshot'ов меню...")
    
    current = load_snapshot(current_file)
    previous = load_snapshot(previous_file)
    
    if not previous:
        print("⚠️ Предыдущий snapshot не найден, создаю первый diff")
        diff_content = "# 🔄 DIFF МЕНЮ\n\n## Первый snapshot\n\nНет предыдущего snapshot для сравнения.\n"
    else:
        diff_content = diff_snapshots(current, previous)
    
    # Сохраняем diff
    diff_file = artifacts_dir / "menu_diff.md"
    with open(diff_file, 'w', encoding='utf-8') as f:
        f.write(diff_content)
    print(f"✅ Сохранён {diff_file}")
    
    # Сохраняем текущий как previous для следующего раза
    if current_file.exists():
        import shutil
        shutil.copy(current_file, previous_file)
        print(f"✅ Сохранён {previous_file} для следующего сравнения")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
