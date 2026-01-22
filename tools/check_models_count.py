#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка количества моделей в каталоге"""
import yaml
import sys
from pathlib import Path
from collections import defaultdict

# Устанавливаем UTF-8 для вывода
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

catalog_file = Path('app/kie_catalog/models_pricing.yaml')
if not catalog_file.exists():
    print(f"[ERROR] Catalog file not found: {catalog_file}")
    sys.exit(1)

with open(catalog_file, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

models = data.get('models', [])
print(f"[OK] Total models in catalog: {len(models)}")
print(f"\nModel IDs (first 20):")
for i, model in enumerate(models[:20], 1):
    model_id = model.get('id', 'N/A')
    title = model.get('title_ru', 'N/A')
    model_type = model.get('type', 'N/A')
    print(f"  {i:2d}. {model_id:40s} | {model_type:10s} | {title}")

if len(models) > 20:
    print(f"\n... and {len(models) - 20} more models")

# Группировка по типам
by_type = defaultdict(int)
for model in models:
    model_type = model.get('type', 'unknown')
    by_type[model_type] += 1

print(f"\nModels by type:")
for model_type, count in sorted(by_type.items()):
    print(f"  {model_type:20s}: {count:3d} models")

