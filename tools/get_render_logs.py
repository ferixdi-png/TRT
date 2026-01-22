#!/usr/bin/env python3
"""
Скрипт для получения логов с Render через API
Использование:
    python get_render_logs.py [--service-id SERVICE_ID] [--lines LINES] [--follow]
"""

import os
import sys
import argparse
import requests
import time
from datetime import datetime
from typing import Optional

# Render API endpoints
RENDER_API_BASE = "https://api.render.com/v1"

def get_render_api_key() -> Optional[str]:
    """Получает API ключ Render из переменных окружения"""
    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        print("❌ RENDER_API_KEY не установлен в переменных окружения")
        print("\n💡 Как получить API ключ:")
        print("1. Откройте https://dashboard.render.com/")
        print("2. Перейдите в Settings → API Keys")
        print("3. Создайте новый API ключ")
        print("4. Установите: set RENDER_API_KEY=your_key_here (Windows)")
        print("   или: export RENDER_API_KEY=your_key_here (Linux/Mac)")
        return None
    return api_key

def get_service_id() -> Optional[str]:
    """Получает Service ID из переменных окружения или запрашивает"""
    service_id = os.getenv("RENDER_SERVICE_ID")
    if not service_id:
        print("⚠️  RENDER_SERVICE_ID не установлен")
        print("💡 Установите: set RENDER_SERVICE_ID=your_service_id (Windows)")
        print("   или: export RENDER_SERVICE_ID=your_service_id (Linux/Mac)")
        print("\n📋 Как найти Service ID:")
        print("1. Откройте ваш сервис в Render Dashboard")
        print("2. Service ID находится в URL: https://dashboard.render.com/web/your-service-id")
        print("   или в Settings → Service ID")
    return service_id

def list_services(api_key: str):
    """Список всех сервисов пользователя"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(f"{RENDER_API_BASE}/services", headers=headers, timeout=10)
        response.raise_for_status()
        services = response.json()
        
        print("\n📋 Ваши сервисы на Render:")
        print("=" * 80)
        for service in services:
            service_id = service.get("service", {}).get("id", "N/A")
            name = service.get("service", {}).get("name", "N/A")
            service_type = service.get("service", {}).get("type", "N/A")
            print(f"  ID: {service_id}")
            print(f"  Название: {name}")
            print(f"  Тип: {service_type}")
            print("-" * 80)
        
        return services
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при получении списка сервисов: {e}")
        return None

def get_owner_id(api_key: str, service_id: str) -> Optional[str]:
    """Получает Owner ID из информации о сервисе"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        # Получаем информацию о сервисе
        response = requests.get(f"{RENDER_API_BASE}/services/{service_id}", headers=headers, timeout=10)
        response.raise_for_status()
        
        service_data = response.json()
        service_info = service_data.get("service", {})
        
        # Owner ID может быть в разных местах
        owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
        
        if owner_id:
            return owner_id
        
        # Если не найден, пробуем через список сервисов
        services_response = requests.get(f"{RENDER_API_BASE}/services", headers=headers, timeout=10)
        services_response.raise_for_status()
        services = services_response.json()
        
        if isinstance(services, list):
            for service in services:
                service_info = service.get("service", {})
                if service_info.get("id") == service_id:
                    owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
                    if owner_id:
                        return owner_id
        
        return None
        
    except Exception as e:
        return None

def get_logs(api_key: str, service_id: str, lines: int = 100, owner_id: Optional[str] = None):
    """Получает логи сервиса используя правильный endpoint /v1/logs"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        # Получаем Owner ID если не передан
        if not owner_id:
            owner_id = get_owner_id(api_key, service_id)
        
        # Правильный endpoint для получения логов
        url = f"{RENDER_API_BASE}/logs"
        params = {
            "resource": service_id,
            "limit": lines
        }
        
        # Добавляем ownerId если есть
        if owner_id:
            params["ownerId"] = owner_id
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        logs_data = response.json()
        
        # Обрабатываем разные форматы ответа
        if isinstance(logs_data, list):
            logs = logs_data
        elif isinstance(logs_data, dict):
            if "logs" in logs_data:
                logs = logs_data["logs"]
            elif "data" in logs_data:
                logs = logs_data["data"]
            elif "items" in logs_data:
                logs = logs_data["items"]
            else:
                logs = [logs_data]
        else:
            logs = [logs_data] if logs_data else []
        
        print(f"\n📊 Последние {len(logs)} строк логов:")
        print("=" * 80)
        
        for log_entry in logs:
            if isinstance(log_entry, dict):
                timestamp = log_entry.get("timestamp", "")
                message = log_entry.get("message", log_entry.get("text", ""))
                level = log_entry.get("level", "INFO")
                
                # Форматируем вывод
                if timestamp:
                    print(f"[{timestamp}] {level}: {message}")
                else:
                    print(f"{level}: {message}")
            else:
                print(log_entry)
        
        return logs
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при получении логов: {e}")
        if hasattr(e.response, 'text'):
            print(f"Ответ сервера: {e.response.text}")
        return None

def follow_logs(api_key: str, service_id: str, interval: int = 5):
    """Отслеживает логи в реальном времени (polling)"""
    print(f"\n🔄 Отслеживание логов (обновление каждые {interval} секунд)")
    print("Нажмите Ctrl+C для остановки")
    print("=" * 80)
    
    last_timestamp = None
    
    try:
        while True:
            logs = get_logs(api_key, service_id, lines=50)
            
            if logs:
                # Сохраняем последний timestamp для следующего запроса
                if isinstance(logs[-1], dict):
                    last_timestamp = logs[-1].get("timestamp")
            
            time.sleep(interval)
            print("\n" + "=" * 80)
            print(f"🔄 Обновление... ({datetime.now().strftime('%H:%M:%S')})")
            print("=" * 80)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Остановлено пользователем")

def analyze_logs_for_errors(logs):
    """Анализирует логи на наличие ошибок"""
    if not logs:
        return
    
    errors = []
    warnings = []
    conflicts_409 = []
    
    for log_entry in logs:
        message = ""
        if isinstance(log_entry, dict):
            message = str(log_entry.get("message", log_entry.get("text", "")))
            level = log_entry.get("level", "").upper()
        else:
            message = str(log_entry)
            level = "INFO"
        
        message_lower = message.lower()
        
        if "error" in message_lower or level == "ERROR":
            errors.append(message)
        if "warning" in message_lower or level == "WARNING":
            warnings.append(message)
        if "409" in message or "conflict" in message_lower:
            conflicts_409.append(message)
    
    print("\n" + "=" * 80)
    print("📊 АНАЛИЗ ЛОГОВ")
    print("=" * 80)
    
    if conflicts_409:
        print(f"\n🚨 КРИТИЧНО: Найдено {len(conflicts_409)} конфликтов 409!")
        print("Это означает, что запущено несколько экземпляров бота одновременно")
        print("\n💡 РЕШЕНИЕ:")
        print("1. Остановите все локальные экземпляры бота")
        print("2. Проверьте Render Dashboard - нет ли дублирующих сервисов")
        print("3. Выполните Restart на Render")
        print("4. Убедитесь, что webhook удалён:")
        print("   curl https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true")
        for conflict in conflicts_409[:5]:  # Показываем первые 5
            print(f"   - {conflict[:100]}...")
    
    if errors:
        print(f"\n❌ Найдено {len(errors)} ошибок:")
        for error in errors[:10]:  # Показываем первые 10
            print(f"   - {error[:150]}...")
    
    if warnings:
        print(f"\n⚠️  Найдено {len(warnings)} предупреждений:")
        for warning in warnings[:10]:  # Показываем первые 10
            print(f"   - {warning[:150]}...")
    
    if not errors and not warnings and not conflicts_409:
        print("\n✅ Ошибок не найдено! Всё работает нормально.")

def main():
    parser = argparse.ArgumentParser(
        description="Получение логов с Render",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Получить последние 100 строк логов
  python get_render_logs.py --service-id srv-xxxxx --lines 100
  
  # Отслеживать логи в реальном времени
  python get_render_logs.py --service-id srv-xxxxx --follow
  
  # Список всех сервисов
  python get_render_logs.py --list-services
  
  # Использовать переменные окружения
  set RENDER_API_KEY=your_key
  set RENDER_SERVICE_ID=srv-xxxxx
  python get_render_logs.py
        """
    )
    
    parser.add_argument(
        "--service-id",
        help="Service ID на Render (или установите RENDER_SERVICE_ID)"
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=100,
        help="Количество строк логов (по умолчанию: 100)"
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Отслеживать логи в реальном времени"
    )
    parser.add_argument(
        "--list-services",
        action="store_true",
        help="Показать список всех сервисов"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Проанализировать логи на наличие ошибок"
    )
    
    args = parser.parse_args()
    
    # Получаем API ключ
    api_key = get_render_api_key()
    if not api_key:
        sys.exit(1)
    
    # Список сервисов
    if args.list_services:
        list_services(api_key)
        return
    
    # Получаем Service ID
    service_id = args.service_id or get_service_id()
    if not service_id:
        print("\n💡 Используйте --list-services чтобы увидеть все ваши сервисы")
        sys.exit(1)
    
    # Получаем логи
    if args.follow:
        follow_logs(api_key, service_id)
    else:
        logs = get_logs(api_key, service_id, lines=args.lines)
        
        if args.analyze and logs:
            analyze_logs_for_errors(logs)

if __name__ == "__main__":
    main()







