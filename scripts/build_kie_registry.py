#!/usr/bin/env python3
"""
Build script для генерации machine-readable registry моделей KIE AI.

Вход: docs/*_INTEGRATION.md
Выход: models/kie_registry.generated.json

Использование:
    python scripts/build_kie_registry.py
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.kie.spec_parser import parse_all_integration_docs, model_spec_to_dict


def calculate_checksum(content: str) -> str:
    """Вычисляет SHA256 checksum содержимого."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def build_registry() -> Dict[str, Any]:
    """
    Строит registry из документации.
    
    Returns:
        Словарь с registry данными
    """
    docs_dir = project_root / "docs"
    
    if not docs_dir.exists():
        print(f"[ERROR] Directory {docs_dir} does not exist")
        sys.exit(1)
    
    # Парсим все файлы документации
    registry_dict = parse_all_integration_docs(docs_dir)
    
    if not registry_dict:
        print("[ERROR] No models found in documentation")
        sys.exit(1)
    
    # Конвертируем в JSON-совместимый формат
    models_data = {}
    for model_id, spec in registry_dict.items():
        models_data[model_id] = model_spec_to_dict(spec)
    
    # Формируем итоговый registry
    registry = {
        "version": "1.0",
        "source": "docs/*_INTEGRATION.md",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "models_count": len(models_data),
        "models": models_data
    }
    
    return registry


def main():
    """Главная функция."""
    print("Building KIE Registry from documentation...")
    
    # Строим registry
    registry = build_registry()
    
    # Вычисляем checksum
    registry_json = json.dumps(registry, indent=2, ensure_ascii=False)
    checksum = calculate_checksum(registry_json)
    registry["checksum"] = checksum
    
    # Сохраняем в файл
    output_dir = project_root / "models"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "kie_registry.generated.json"
    
    # Пересоздаём registry с checksum
    registry_json = json.dumps(registry, indent=2, ensure_ascii=False)
    output_file.write_text(registry_json, encoding='utf-8')
    
    print(f"[OK] Registry built: {output_file}")
    print(f"   Models count: {registry['models_count']}")
    print(f"   Checksum: {checksum[:16]}...")
    
    # Выводим список моделей
    print("\nModels in registry:")
    for model_id in sorted(registry["models"].keys()):
        print(f"   - {model_id}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

