#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Снимок всех меню и подменю
Сохраняет artifacts/menu_snapshot.json и artifacts/menu_snapshot.md
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Any

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

SNAPSHOT_JSON = ARTIFACTS_DIR / "menu_snapshot.json"
SNAPSHOT_MD = ARTIFACTS_DIR / "menu_snapshot.md"


def extract_callbacks_from_code() -> Dict[str, Any]:
    """Извлекает все callback_data из кода"""
    bot_file = PROJECT_ROOT / "bot_kie.py"
    callbacks = {}
    
    if not bot_file.exists():
        return callbacks
    
    try:
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем callback_data в коде
        patterns = [
            (r'callback_data\s*=\s*["\']([^"\']+)["\']', "exact"),
            (r'callback_data\s*=\s*f["\']([^"\']+)["\']', "f-string"),
            (r'pattern\s*=\s*["\']([^"\']+)["\']', "pattern"),
        ]
        
        for pattern, pattern_type in patterns:
            for match in re.finditer(pattern, content):
                callback = match.group(1)
                # Убираем переменные из f-strings
                if '{' not in callback and '}' not in callback:
                    if callback not in callbacks:
                        callbacks[callback] = {
                            "type": pattern_type,
                            "handlers": []
                        }
    except Exception as e:
        print(f"⚠️ Ошибка при извлечении callback'ов: {e}")
    
    return callbacks


def extract_handlers_from_code() -> Dict[str, List[str]]:
    """Извлекает обработчики callback'ов"""
    bot_file = PROJECT_ROOT / "bot_kie.py"
    handlers = {}
    
    if not bot_file.exists():
        return handlers
    
    try:
        with open(bot_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем обработку callback_data в button_callback
        # Паттерны: if data == "...", if data.startswith("..."), elif data == "..."
        patterns = [
            r'if\s+data\s*==\s*["\']([^"\']+)["\']',
            r'elif\s+data\s*==\s*["\']([^"\']+)["\']',
            r'if\s+data\.startswith\(["\']([^"\']+)["\']',
            r'elif\s+data\.startswith\(["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                callback = match.group(1)
                if callback not in handlers:
                    handlers[callback] = []
                handlers[callback].append("button_callback")
    except Exception as e:
        print(f"⚠️ Ошибка при извлечении обработчиков: {e}")
    
    return handlers


def extract_models_from_kie_models() -> List[Dict[str, Any]]:
    """Извлекает модели из kie_models.py"""
    models = []
    
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from kie_models import KIE_MODELS
        
        if isinstance(KIE_MODELS, dict):
            for model_id, model_data in KIE_MODELS.items():
                models.append({
                    "id": model_id,
                    "name": model_data.get("name", ""),
                    "emoji": model_data.get("emoji", ""),
                    "generation_type": model_data.get("generation_type", ""),
                })
        elif isinstance(KIE_MODELS, list):
            for model in KIE_MODELS:
                models.append({
                    "id": model.get("id", ""),
                    "name": model.get("name", ""),
                    "emoji": model.get("emoji", ""),
                    "generation_type": model.get("generation_type", ""),
                })
    except Exception as e:
        print(f"⚠️ Ошибка при загрузке моделей: {e}")
    
    return models


def create_snapshot() -> Dict[str, Any]:
    """Создаёт снимок всех меню"""
    import time
    snapshot = {
        "timestamp": str(time.time()),
        "callbacks": extract_callbacks_from_code(),
        "handlers": extract_handlers_from_code(),
        "models": extract_models_from_kie_models(),
    }
    
    return snapshot


def save_snapshot(snapshot: Dict[str, Any]):
    """Сохраняет снимок в JSON и Markdown"""
    # JSON
    with open(SNAPSHOT_JSON, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    
    # Markdown
    with open(SNAPSHOT_MD, 'w', encoding='utf-8') as f:
        f.write("# Снимок меню\n\n")
        f.write(f"**Дата:** {snapshot['timestamp']}\n\n")
        
        f.write("## Callback'ы\n\n")
        f.write(f"Всего: {len(snapshot['callbacks'])}\n\n")
        for callback, info in sorted(snapshot['callbacks'].items()):
            f.write(f"- `{callback}` ({info['type']})\n")
        
        f.write("\n## Обработчики\n\n")
        f.write(f"Всего: {len(snapshot['handlers'])}\n\n")
        for callback, handler_list in sorted(snapshot['handlers'].items()):
            f.write(f"- `{callback}` → {', '.join(handler_list)}\n")
        
        f.write("\n## Модели\n\n")
        f.write(f"Всего: {len(snapshot['models'])}\n\n")
        for model in snapshot['models'][:20]:  # Первые 20
            f.write(f"- {model.get('emoji', '')} `{model.get('id', '')}` - {model.get('name', '')}\n")
        if len(snapshot['models']) > 20:
            f.write(f"\n... и ещё {len(snapshot['models']) - 20} моделей\n")


def main():
    """Главная функция"""
    print("="*80)
    print("📸 СОЗДАНИЕ СНИМКА МЕНЮ")
    print("="*80)
    print()
    
    snapshot = create_snapshot()
    save_snapshot(snapshot)
    
    print(f"✅ Снимок сохранён:")
    print(f"   JSON: {SNAPSHOT_JSON}")
    print(f"   Markdown: {SNAPSHOT_MD}")
    print()
    print(f"📊 Статистика:")
    print(f"   Callback'ов: {len(snapshot['callbacks'])}")
    print(f"   Обработчиков: {len(snapshot['handlers'])}")
    print(f"   Моделей: {len(snapshot['models'])}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
