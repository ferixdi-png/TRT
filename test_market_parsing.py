#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Тестовый скрипт для анализа структуры страницы маркета"""

import requests
from bs4 import BeautifulSoup
import json
import re

url = "https://kie.ai/ru/market"
print(f"Запрос к {url}...")
resp = requests.get(url)
print(f"Status: {resp.status_code}")
print(f"Размер HTML: {len(resp.text)} символов\n")

soup = BeautifulSoup(resp.text, 'html.parser')

# Ищем __NEXT_DATA__
scripts = soup.find_all('script')
print(f"Найдено script тегов: {len(scripts)}\n")

# Проверяем все script теги
for i, script in enumerate(scripts):
    script_text = script.string or script.get_text()
    if not script_text or len(script_text) < 50:
        continue
    
    print(f"\nScript #{i}: {len(script_text)} символов")
    
    # Ищем JSON паттерны
    if '{' in script_text and ('model' in script_text.lower() or 'api' in script_text.lower() or 'item' in script_text.lower()):
        print(f"  [OK] Possible JSON with models")
        
        # Пытаемся найти JSON объект
        json_patterns = [
            r'__NEXT_DATA__\s*=\s*({.+?})\s*</script>',
            r'window\.__[A-Z_]+__\s*=\s*({.+?});',
            r'({[^{}]*"models?"[^{}]*})',
        ]
        
        for pattern in json_patterns:
            matches = re.finditer(pattern, script_text, re.DOTALL)
            for match in matches:
                try:
                    json_str = match.group(1)
                    if len(json_str) > 100000:  # Слишком большой
                        continue
                    data = json.loads(json_str)
                    print(f"  [OK] JSON parsed successfully!")
                    print(f"  Type: {type(data).__name__}")
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())[:10]}")
                    elif isinstance(data, list):
                        print(f"  List length: {len(data)}")
                    
                    # Сохраняем для анализа
                    with open(f'next_data_{i}.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"  [OK] Saved to next_data_{i}.json")
                    break
                except Exception as e:
                    continue

