#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render Logs Connector - улучшенная версия
Поддержка tail/follow, фильтров, пагинации
"""

import os
import sys
import argparse
import requests
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

RENDER_API_BASE = "https://api.render.com/v1"


def get_render_api_key() -> Optional[str]:
    """Получает API ключ Render"""
    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        print("❌ RENDER_API_KEY не установлен")
        print("\n💡 Установите: set RENDER_API_KEY=your_key (Windows)")
        print("   или: export RENDER_API_KEY=your_key (Linux/Mac)")
        return None
    return api_key


def get_service_id_from_config() -> Optional[str]:
    """Получает Service ID из services_config.json"""
    try:
        import json
        config_file = Path(__file__).parent.parent / "services_config.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                services = config.get("services", [])
                if services:
                    # Возвращаем первый активный сервис
                    for service in services:
                        if service.get("enabled", True):
                            return service.get("service_id")
    except:
        pass
    return None


def get_service_id() -> Optional[str]:
    """Получает Service ID из ENV или конфига"""
    service_id = os.getenv("RENDER_SERVICE_ID")
    if not service_id:
        service_id = get_service_id_from_config()
    return service_id


def list_services(api_key: str):
    """Список всех сервисов"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(f"{RENDER_API_BASE}/services", headers=headers, timeout=10)
        response.raise_for_status()
        services = response.json()
        
        # Обрабатываем разные форматы ответа
        if isinstance(services, dict) and "services" in services:
            services = services["services"]
        
        print("\n📋 Ваши сервисы на Render:")
        print("=" * 80)
        for service in services:
            if isinstance(service, dict):
                service_info = service.get("service", service)
                service_id = service_info.get("id", "N/A")
                name = service_info.get("name", "N/A")
                service_type = service_info.get("type", "N/A")
                status = service_info.get("suspendedInactiveAt")
                status_text = "⏸️ Приостановлен" if status else "✅ Активен"
                
                print(f"  ID: {service_id}")
                print(f"  Название: {name}")
                print(f"  Тип: {service_type}")
                print(f"  Статус: {status_text}")
                print("-" * 80)
        
        return services
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


def get_owner_id(api_key: str, service_id: str) -> Optional[str]:
    """Получает Owner ID"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(f"{RENDER_API_BASE}/services/{service_id}", headers=headers, timeout=10)
        if response.status_code == 200:
            service_data = response.json()
            service_info = service_data.get("service", service_data)
            return service_info.get("ownerId")
    except:
        pass
    return None


def parse_time_filter(since: str) -> Optional[datetime]:
    """Парсит фильтр времени (например, '15m', '2h', '1d')"""
    if not since:
        return None
    
    try:
        since = since.lower().strip()
        
        if since.endswith('m'):
            minutes = int(since[:-1])
            return datetime.now() - timedelta(minutes=minutes)
        elif since.endswith('h'):
            hours = int(since[:-1])
            return datetime.now() - timedelta(hours=hours)
        elif since.endswith('d'):
            days = int(since[:-1])
            return datetime.now() - timedelta(days=days)
        else:
            # Пробуем распарсить как ISO формат
            return datetime.fromisoformat(since.replace('Z', '+00:00'))
    except:
        return None


def get_logs(
    api_key: str,
    service_id: str,
    lines: int = 100,
    level: Optional[str] = None,
    text_filter: Optional[str] = None,
    since: Optional[str] = None,
    owner_id: Optional[str] = None
) -> List[Dict]:
    """Получает логи с фильтрами"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    try:
        if not owner_id:
            owner_id = get_owner_id(api_key, service_id)
        
        url = f"{RENDER_API_BASE}/logs"
        params = {
            "resource": service_id,
            "limit": lines
        }
        
        if owner_id:
            params["ownerId"] = owner_id
        
        # Пагинация (если нужно)
        # Render API поддерживает nextStartTime/nextEndTime для пагинации
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        logs_data = response.json()
        
        # Обрабатываем разные форматы
        if isinstance(logs_data, list):
            logs = logs_data
        elif isinstance(logs_data, dict):
            logs = logs_data.get("logs", logs_data.get("data", logs_data.get("items", [])))
        else:
            logs = []
        
        # Применяем фильтры
        filtered_logs = []
        since_time = parse_time_filter(since) if since else None
        
        for log_entry in logs:
            if not isinstance(log_entry, dict):
                continue
            
            # Фильтр по уровню
            if level:
                log_level = log_entry.get("level", "").upper()
                if level.upper() not in log_level:
                    continue
            
            # Фильтр по тексту (поддержка regex через --grep)
            if text_filter:
                message = str(log_entry.get("message", log_entry.get("text", "")))
                try:
                    import re
                    # Пробуем как regex, если не работает - как обычный поиск
                    if re.search(text_filter, message, re.IGNORECASE):
                        pass  # Совпадение найдено
                    else:
                        continue
                except re.error:
                    # Если не regex - обычный поиск
                    if text_filter.lower() not in message.lower():
                        continue
            
            # Фильтр по времени
            if since_time:
                timestamp_str = log_entry.get("timestamp", "")
                if timestamp_str:
                    try:
                        log_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if log_time < since_time:
                            continue
                    except:
                        pass
            
            filtered_logs.append(log_entry)
        
        return filtered_logs
        
    except Exception as e:
        print(f"❌ Ошибка при получении логов: {e}")
        return []


def print_logs(logs: List[Dict], show_timestamp: bool = True):
    """Выводит логи в консоль"""
    if not logs:
        print("📭 Логи не найдены")
        return
    
    print(f"\n📊 Найдено {len(logs)} строк логов:")
    print("=" * 80)
    
    for log_entry in logs:
        timestamp = log_entry.get("timestamp", "")
        message = log_entry.get("message", log_entry.get("text", ""))
        level = log_entry.get("level", "INFO")
        
        # Форматируем вывод
        if show_timestamp and timestamp:
            # Упрощаем timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                ts = dt.strftime("%H:%M:%S")
            except:
                ts = timestamp[:19] if len(timestamp) > 19 else timestamp
            print(f"[{ts}] {level}: {message}")
        else:
            print(f"{level}: {message}")


def tail_logs(
    api_key: str,
    service_id: str,
    interval: int = 5,
    level: Optional[str] = None,
    text_filter: Optional[str] = None,
    since: Optional[str] = None
):
    """Отслеживает логи в реальном времени (tail/follow)"""
    print(f"\n🔄 Отслеживание логов (обновление каждые {interval} сек)")
    print("Нажмите Ctrl+C для остановки")
    print("=" * 80)
    
    last_timestamp = None
    seen_logs = set()  # Для дедупликации
    
    try:
        while True:
            logs = get_logs(api_key, service_id, lines=100, level=level, text_filter=text_filter, since=since)
            
            # Фильтруем уже показанные логи
            new_logs = []
            for log in logs:
                log_id = f"{log.get('timestamp')}:{log.get('message', '')[:50]}"
                if log_id not in seen_logs:
                    seen_logs.add(log_id)
                    new_logs.append(log)
                    # Ограничиваем размер seen_logs
                    if len(seen_logs) > 1000:
                        seen_logs.clear()
            
            if new_logs:
                print_logs(new_logs, show_timestamp=True)
            
            time.sleep(interval)
            print(f"\n🔄 Обновление... ({datetime.now().strftime('%H:%M:%S')})")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Остановлено")


def main():
    parser = argparse.ArgumentParser(description="Render Logs Connector")
    parser.add_argument("--list-services", action="store_true", help="Список всех сервисов")
    parser.add_argument("--service-id", help="Service ID (или установите RENDER_SERVICE_ID)")
    parser.add_argument("--lines", type=int, default=100, help="Количество строк (по умолчанию: 100)")
    parser.add_argument("--tail", "--follow", action="store_true", help="Отслеживать логи в реальном времени")
    parser.add_argument("--interval", type=int, default=5, help="Интервал обновления для --tail (секунды)")
    parser.add_argument("--level", help="Фильтр по уровню (ERROR, WARNING, INFO)")
    parser.add_argument("--text", help="Фильтр по тексту")
    parser.add_argument("--since", help="Фильтр по времени (например: 15m, 2h, 1d)")
    parser.add_argument("--analyze", action="store_true", help="Анализ логов на ошибки")
    
    args = parser.parse_args()
    
    api_key = get_render_api_key()
    if not api_key:
        return 1
    
    if args.list_services:
        list_services(api_key)
        return 0
    
    service_id = args.service_id or get_service_id()
    if not service_id:
        print("❌ RENDER_SERVICE_ID не установлен")
        print("💡 Используйте --service-id или установите RENDER_SERVICE_ID")
        print("💡 Или используйте --list-services для выбора")
        return 1
    
    if args.tail:
        tail_logs(
            api_key, service_id,
            interval=args.interval,
            level=args.level,
            text_filter=args.text,
            since=args.since
        )
    else:
        logs = get_logs(
            api_key, service_id,
            lines=args.lines,
            level=args.level,
            text_filter=args.text,
            since=args.since
        )
        print_logs(logs)
        
        if args.analyze:
            # Анализ ошибок
            errors = [l for l in logs if "error" in str(l.get("message", "")).lower()]
            warnings = [l for l in logs if "warning" in str(l.get("message", "")).lower()]
            conflicts = [l for l in logs if "409" in str(l.get("message", "")) or "conflict" in str(l.get("message", "")).lower()]
            
            print("\n" + "=" * 80)
            print("📊 АНАЛИЗ ЛОГОВ")
            print("=" * 80)
            print(f"❌ Ошибок: {len(errors)}")
            print(f"⚠️ Предупреждений: {len(warnings)}")
            print(f"🚨 Конфликтов 409: {len(conflicts)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())







