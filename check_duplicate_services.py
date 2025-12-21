#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка дублирующих сервисов в Render с одним токеном
Помогает найти причину 409 Conflict
"""

import os
import sys
import json
import requests
from pathlib import Path

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

RENDER_API_BASE = "https://api.render.com/v1"

def load_services_config():
    """Загружает конфигурацию сервисов"""
    config_file = Path(__file__).parent / "services_config.json"
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None

def get_all_services(api_key: str):
    """Получает все сервисы из Render"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        # Получаем список всех сервисов
        response = requests.get(f"{RENDER_API_BASE}/services", headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"❌ Ошибка API: {response.status_code}")
            return []
        
        services = response.json()
        if isinstance(services, list):
            return services
        elif isinstance(services, dict) and "services" in services:
            return services["services"]
        return []
    except Exception as e:
        print(f"❌ Ошибка при получении сервисов: {e}")
        return []

def check_duplicate_tokens():
    """Проверяет дублирующие токены в сервисах"""
    print("=" * 80)
    print("🔍 ПРОВЕРКА ДУБЛИРУЮЩИХ СЕРВИСОВ В RENDER")
    print("=" * 80)
    print()
    
    # Загружаем конфигурацию
    config = load_services_config()
    if not config:
        print("⚠️  services_config.json не найден, используем переменные окружения")
        api_key = os.getenv("RENDER_API_KEY", "rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw")
        service_id = os.getenv("RENDER_SERVICE_ID", "srv-d4s025er433s73bsf62g")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y")
        
        services_to_check = [{
            "name": "Default Service",
            "service_id": service_id,
            "telegram_token": telegram_token
        }]
    else:
        api_key = config.get("render_api_key") or os.getenv("RENDER_API_KEY", "rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw")
        services_to_check = config.get("services", [])
    
    print(f"📋 Найдено сервисов в конфиге: {len(services_to_check)}")
    print()
    
    # Получаем все сервисы из Render
    print("📥 Получение всех сервисов из Render...")
    all_services = get_all_services(api_key)
    print(f"✅ Найдено сервисов в Render: {len(all_services)}")
    print()
    
    # Группируем по токенам
    token_to_services = {}
    
    for service_config in services_to_check:
        token = service_config.get("telegram_token")
        service_id = service_config.get("service_id")
        service_name = service_config.get("name", "Unknown")
        
        if not token:
            continue
        
        # Находим сервис в Render
        render_service = None
        for s in all_services:
            if isinstance(s, dict):
                s_id = s.get("service", {}).get("id") or s.get("id")
                if s_id == service_id:
                    render_service = s
                    break
        
        if token not in token_to_services:
            token_to_services[token] = []
        
        token_to_services[token].append({
            "name": service_name,
            "service_id": service_id,
            "render_service": render_service
        })
    
    # Проверяем дубликаты
    print("=" * 80)
    print("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
    print("=" * 80)
    print()
    
    duplicates_found = False
    
    for token, services in token_to_services.items():
        token_short = token[:20] + "..." if len(token) > 20 else token
        print(f"🔑 Токен: {token_short}")
        print(f"   Сервисов с этим токеном: {len(services)}")
        print()
        
        if len(services) > 1:
            duplicates_found = True
            print("   ⚠️  ОБНАРУЖЕНЫ ДУБЛИКАТЫ!")
            print()
        
        for i, service in enumerate(services, 1):
            print(f"   {i}. {service['name']}")
            print(f"      Service ID: {service['service_id']}")
            
            render_service = service.get("render_service")
            if render_service:
                service_info = render_service.get("service", render_service)
                status = service_info.get("suspendedInactiveAt")
                if status:
                    print(f"      Статус: ⏸️  Приостановлен")
                else:
                    print(f"      Статус: ✅ Активен")
                
                # Проверяем тип сервиса
                service_type = service_info.get("type", "unknown")
                print(f"      Тип: {service_type}")
            else:
                print(f"      Статус: ❓ Не найден в Render")
            
            print()
        
        print("-" * 80)
        print()
    
    if duplicates_found:
        print("=" * 80)
        print("❌ ПРОБЛЕМА: Обнаружены дублирующие сервисы с одним токеном!")
        print("=" * 80)
        print()
        print("💡 РЕШЕНИЕ:")
        print("   1. В Render Dashboard проверьте все сервисы")
        print("   2. Убедитесь, что только ОДИН сервис активен для каждого токена")
        print("   3. Остановите или удалите дублирующие сервисы")
        print("   4. Перезапустите основной сервис")
        print()
    else:
        print("=" * 80)
        print("✅ Дубликатов не найдено")
        print("=" * 80)
        print()
        print("💡 Если 409 Conflict всё ещё возникает:")
        print("   1. Проверьте локальные запуски бота")
        print("   2. Проверьте другие сервисы в Render (не в конфиге)")
        print("   3. Убедитесь, что нет webhook'ов для этого токена")
        print()

if __name__ == "__main__":
    check_duplicate_tokens()







