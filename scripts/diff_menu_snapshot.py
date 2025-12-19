#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сравнение прошлого и текущего снимка меню
Сохраняет artifacts/menu_diff.md
"""

import sys
import json
from pathlib import Path

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

SNAPSHOT_JSON = ARTIFACTS_DIR / "menu_snapshot.json"
PREV_SNAPSHOT_JSON = ARTIFACTS_DIR / "menu_snapshot_prev.json"
DIFF_MD = ARTIFACTS_DIR / "menu_diff.md"


def load_snapshot(file_path: Path) -> dict:
    """Загружает снимок из JSON"""
    if not file_path.exists():
        return {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def compare_snapshots(current: dict, previous: dict) -> dict:
    """Сравнивает два снимка и возвращает различия"""
    diff = {
        "added_callbacks": [],
        "removed_callbacks": [],
        "added_handlers": [],
        "removed_handlers": [],
        "added_models": [],
        "removed_models": [],
    }
    
    # Callback'ы
    current_callbacks = set(current.get("callbacks", {}).keys())
    prev_callbacks = set(previous.get("callbacks", {}).keys())
    diff["added_callbacks"] = sorted(current_callbacks - prev_callbacks)
    diff["removed_callbacks"] = sorted(prev_callbacks - current_callbacks)
    
    # Обработчики
    current_handlers = set(current.get("handlers", {}).keys())
    prev_handlers = set(previous.get("handlers", {}).keys())
    diff["added_handlers"] = sorted(current_handlers - prev_handlers)
    diff["removed_handlers"] = sorted(prev_handlers - current_handlers)
    
    # Модели
    current_models = {m.get("id") for m in current.get("models", [])}
    prev_models = {m.get("id") for m in previous.get("models", [])}
    diff["added_models"] = sorted(current_models - prev_models)
    diff["removed_models"] = sorted(prev_models - current_models)
    
    return diff


def save_diff(diff: dict):
    """Сохраняет различия в Markdown"""
    with open(DIFF_MD, 'w', encoding='utf-8') as f:
        f.write("# Различия в меню\n\n")
        
        total_changes = (
            len(diff["added_callbacks"]) +
            len(diff["removed_callbacks"]) +
            len(diff["added_handlers"]) +
            len(diff["removed_handlers"]) +
            len(diff["added_models"]) +
            len(diff["removed_models"])
        )
        
        if total_changes == 0:
            f.write("✅ Изменений не обнаружено\n")
            return
        
        f.write(f"**Всего изменений:** {total_changes}\n\n")
        
        if diff["added_callbacks"]:
            f.write("## ➕ Добавленные callback'ы\n\n")
            for callback in diff["added_callbacks"]:
                f.write(f"- `{callback}`\n")
            f.write("\n")
        
        if diff["removed_callbacks"]:
            f.write("## ➖ Удалённые callback'ы\n\n")
            for callback in diff["removed_callbacks"]:
                f.write(f"- `{callback}`\n")
            f.write("\n")
        
        if diff["added_handlers"]:
            f.write("## ➕ Добавленные обработчики\n\n")
            for handler in diff["added_handlers"]:
                f.write(f"- `{handler}`\n")
            f.write("\n")
        
        if diff["removed_handlers"]:
            f.write("## ➖ Удалённые обработчики\n\n")
            for handler in diff["removed_handlers"]:
                f.write(f"- `{handler}`\n")
            f.write("\n")
        
        if diff["added_models"]:
            f.write("## ➕ Добавленные модели\n\n")
            for model_id in diff["added_models"]:
                f.write(f"- `{model_id}`\n")
            f.write("\n")
        
        if diff["removed_models"]:
            f.write("## ➖ Удалённые модели\n\n")
            for model_id in diff["removed_models"]:
                f.write(f"- `{model_id}`\n")
            f.write("\n")


def main():
    """Главная функция"""
    print("="*80)
    print("🔍 СРАВНЕНИЕ СНИМКОВ МЕНЮ")
    print("="*80)
    print()
    
    current = load_snapshot(SNAPSHOT_JSON)
    previous = load_snapshot(PREV_SNAPSHOT_JSON)
    
    if not current:
        print("❌ Текущий снимок не найден. Запустите scripts/snapshot_menu.py")
        return 1
    
    if not previous:
        print("⚠️ Предыдущий снимок не найден. Создаю пустой diff.")
        diff = {
            "added_callbacks": list(current.get("callbacks", {}).keys()),
            "removed_callbacks": [],
            "added_handlers": list(current.get("handlers", {}).keys()),
            "removed_handlers": [],
            "added_models": [m.get("id") for m in current.get("models", [])],
            "removed_models": [],
        }
    else:
        diff = compare_snapshots(current, previous)
    
    save_diff(diff)
    
    # Сохраняем текущий снимок как предыдущий для следующего запуска
    if SNAPSHOT_JSON.exists():
        import shutil
        shutil.copy(SNAPSHOT_JSON, PREV_SNAPSHOT_JSON)
    
    print(f"✅ Различия сохранены: {DIFF_MD}")
    print()
    
    total_changes = sum(len(v) for v in diff.values())
    if total_changes > 0:
        print(f"📊 Найдено изменений: {total_changes}")
        print(f"   ➕ Callback'ов: {len(diff['added_callbacks'])}")
        print(f"   ➖ Callback'ов: {len(diff['removed_callbacks'])}")
        print(f"   ➕ Обработчиков: {len(diff['added_handlers'])}")
        print(f"   ➖ Обработчиков: {len(diff['removed_handlers'])}")
        print(f"   ➕ Моделей: {len(diff['added_models'])}")
        print(f"   ➖ Моделей: {len(diff['removed_models'])}")
    else:
        print("✅ Изменений не обнаружено")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
