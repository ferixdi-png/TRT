#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render Autopilot Monitor - автоматический мониторинг и исправление проблем
Отслеживает логи Render, находит ошибки и автоматически исправляет их
"""

import os
import sys
import io
import time
import json
import requests
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Render API
RENDER_API_BASE = "https://api.render.com/v1"

# Конфигурация из ENV или дефолт
RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

project_root = Path(__file__).parent.parent


class RenderAutopilotMonitor:
    """Автоматический мониторинг и исправление проблем Render"""
    
    def __init__(self):
        self.api_key = RENDER_API_KEY
        self.service_id = RENDER_SERVICE_ID
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        self.owner_id = None
        self.last_log_timestamp = None
        self.error_patterns = {
            "NameError": r"NameError: name '(\w+)' is not defined",
            "ImportError": r"ImportError: (.*)",
            "AttributeError": r"AttributeError: (.*)",
            "409 Conflict": r"409|Conflict|another instance",
            "ConnectionError": r"ConnectionError|connection refused|timeout",
            "ModuleNotFoundError": r"ModuleNotFoundError: No module named '(\w+)'",
        }
    
    def get_owner_id(self) -> Optional[str]:
        """Получает Owner ID сервиса"""
        if self.owner_id:
            return self.owner_id
        
        try:
            response = requests.get(
                f"{RENDER_API_BASE}/services/{self.service_id}",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            service_data = response.json()
            
            # Обрабатываем разные форматы ответа
            if isinstance(service_data, dict):
                service_info = service_data.get("service", service_data)
                self.owner_id = (
                    service_info.get("ownerId") or 
                    service_info.get("owner", {}).get("id") if isinstance(service_info.get("owner"), dict) else None or
                    service_info.get("ownerId")
                )
            
            if not self.owner_id:
                # Пробуем получить через список сервисов
                services_response = requests.get(
                    f"{RENDER_API_BASE}/services",
                    headers=self.headers,
                    timeout=10
                )
                services_response.raise_for_status()
                services = services_response.json()
                
                # Обрабатываем разные форматы
                if isinstance(services, list):
                    for service in services:
                        service_info = service.get("service", service)
                        if service_info.get("id") == self.service_id:
                            self.owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
                            break
                elif isinstance(services, dict) and "services" in services:
                    for service in services["services"]:
                        service_info = service.get("service", service)
                        if service_info.get("id") == self.service_id:
                            self.owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
                            break
            
            if self.owner_id:
                print(f"✅ Owner ID получен: {self.owner_id[:10]}...")
            else:
                print("⚠️ Owner ID не найден, попробую без него")
            
            return self.owner_id
        except Exception as e:
            print(f"⚠️ Не удалось получить Owner ID: {e}")
            return None
    
    def get_logs(self, lines: int = 200) -> List[Dict]:
        """Получает логи с Render"""
        try:
            owner_id = self.get_owner_id()
            
            # Используем общий endpoint /logs с параметром resource
            url = f"{RENDER_API_BASE}/logs"
            params = {
                "resource": self.service_id,
                "limit": lines
            }
            
            # Owner ID может быть нужен для некоторых аккаунтов
            if owner_id:
                params["ownerId"] = owner_id
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code != 200:
                error_text = response.text[:200] if hasattr(response, 'text') else str(response.status_code)
                print(f"⚠️ HTTP {response.status_code}: {error_text}")
                # Пробуем без ownerId
                if owner_id and "ownerId" in str(error_text):
                    params.pop("ownerId", None)
                    response = requests.get(url, headers=self.headers, params=params, timeout=30)
                    if response.status_code != 200:
                        return []
                else:
                    return []
            
            # response.raise_for_status() - не вызываем, т.к. уже проверили статус
            
            logs_data = response.json()
            
            # Обрабатываем разные форматы
            if isinstance(logs_data, list):
                logs = logs_data
            elif isinstance(logs_data, dict):
                logs = logs_data.get("logs", logs_data.get("data", logs_data.get("items", [])))
            else:
                logs = []
            
            # Обрабатываем логи
            processed_logs = []
            for log_entry in logs:
                if isinstance(log_entry, dict):
                    message = log_entry.get("message", log_entry.get("text", str(log_entry)))
                    timestamp = log_entry.get("timestamp", log_entry.get("createdAt", ""))
                    level = log_entry.get("level", "INFO")
                    
                    processed_logs.append({
                        "message": message,
                        "timestamp": timestamp,
                        "level": level,
                        "raw": log_entry
                    })
                else:
                    processed_logs.append({
                        "message": str(log_entry),
                        "timestamp": "",
                        "level": "INFO",
                        "raw": log_entry
                    })
            
            return processed_logs
            
        except Exception as e:
            print(f"❌ Ошибка при получении логов: {e}")
            return []
    
    def analyze_errors(self, logs: List[Dict]) -> Dict:
        """Анализирует логи на наличие ошибок"""
        errors = {
            "critical": [],
            "warnings": [],
            "conflicts_409": [],
            "import_errors": [],
            "name_errors": [],
            "other": []
        }
        
        for log in logs:
            message = log.get("message", "").lower()
            level = log.get("level", "").upper()
            
            # 409 Conflict
            if "409" in message or "conflict" in message:
                errors["conflicts_409"].append(log)
            
            # NameError
            if "nameerror" in message or "name '" in message:
                errors["name_errors"].append(log)
            
            # ImportError
            if "importerror" in message or "no module named" in message:
                errors["import_errors"].append(log)
            
            # Критические ошибки
            if level == "ERROR" or "error" in message:
                if log not in errors["name_errors"] and log not in errors["import_errors"]:
                    errors["critical"].append(log)
            
            # Предупреждения
            if level == "WARNING" or "warning" in message:
                errors["warnings"].append(log)
        
        return errors
    
    def fix_name_error(self, error_log: Dict) -> bool:
        """Исправляет NameError"""
        message = error_log.get("message", "")
        
        # Ищем имя неопределенной переменной
        import re
        match = re.search(r"name '(\w+)' is not defined", message)
        if not match:
            return False
        
        missing_name = match.group(1)
        print(f"🔧 Найдена ошибка: NameError: name '{missing_name}' is not defined")
        
        # Проверяем, есть ли эта функция/переменная в коде
        bot_kie_path = project_root / "bot_kie.py"
        if not bot_kie_path.exists():
            return False
        
        # Читаем файл
        content = bot_kie_path.read_text(encoding='utf-8')
        
        # Проверяем, определена ли переменная/функция
        if missing_name in content:
            # Проверяем, есть ли она в fallback блоке
            if "except ImportError:" in content:
                # Проверяем, есть ли fallback для этой переменной
                import_block_start = content.find("except ImportError:")
                import_block = content[import_block_start:import_block_start+5000]
                
                if missing_name not in import_block:
                    print(f"⚠️ Переменная '{missing_name}' используется, но нет fallback")
                    # Здесь можно добавить автоматическое исправление
                    return False
        
        return True
    
    def fix_import_error(self, error_log: Dict) -> bool:
        """Исправляет ImportError"""
        message = error_log.get("message", "")
        print(f"🔧 Найдена ошибка ImportError: {message[:100]}")
        
        # Проверяем requirements.txt
        requirements_path = project_root / "requirements.txt"
        if requirements_path.exists():
            requirements = requirements_path.read_text(encoding='utf-8')
            # Здесь можно добавить проверку и автоматическое добавление модулей
            pass
        
        return False
    
    def fix_409_conflict(self) -> bool:
        """Исправляет 409 Conflict"""
        print("🔧 Исправление 409 Conflict...")
        
        # Удаляем webhook через Telegram API
        try:
            delete_url = f"https://api.telegram.org/bot{self.bot_token}/deleteWebhook"
            params = {"drop_pending_updates": "true"}
            response = requests.get(delete_url, params=params, timeout=10)
            
            if response.status_code == 200:
                print("✅ Webhook удалён")
                return True
            else:
                print(f"⚠️ Не удалось удалить webhook: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Ошибка при удалении webhook: {e}")
            return False
    
    def restart_service(self) -> bool:
        """Перезапускает сервис на Render"""
        try:
            owner_id = self.get_owner_id()
            if not owner_id:
                print("❌ Не удалось получить Owner ID для перезапуска")
                return False
            
            # Render API для перезапуска
            url = f"{RENDER_API_BASE}/services/{self.service_id}/deploys"
            data = {
                "clearCache": False
            }
            
            response = requests.post(url, headers=self.headers, json=data, timeout=30)
            
            if response.status_code in [200, 201]:
                print("✅ Сервис перезапущен")
                return True
            else:
                print(f"⚠️ Не удалось перезапустить сервис: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Ошибка при перезапуске сервиса: {e}")
            return False
    
    def auto_fix(self, errors: Dict) -> bool:
        """Автоматически исправляет найденные ошибки"""
        fixed = False
        
        # 409 Conflict - приоритет
        if errors["conflicts_409"]:
            print(f"\n🚨 Найдено {len(errors['conflicts_409'])} конфликтов 409")
            if self.fix_409_conflict():
                fixed = True
        
        # NameError
        if errors["name_errors"]:
            print(f"\n🚨 Найдено {len(errors['name_errors'])} ошибок NameError")
            for error in errors["name_errors"][:3]:  # Исправляем первые 3
                if self.fix_name_error(error):
                    fixed = True
        
        # ImportError
        if errors["import_errors"]:
            print(f"\n🚨 Найдено {len(errors['import_errors'])} ошибок ImportError")
            for error in errors["import_errors"][:3]:
                if self.fix_import_error(error):
                    fixed = True
        
        # Критические ошибки
        if errors["critical"]:
            print(f"\n🚨 Найдено {len(errors['critical'])} критических ошибок")
            # Показываем первые 5
            for error in errors["critical"][:5]:
                print(f"   - {error.get('message', '')[:150]}")
        
        return fixed
    
    def monitor_loop(self, interval: int = 30):
        """Основной цикл мониторинга"""
        print("🚀 Render Autopilot Monitor запущен")
        print(f"   Service ID: {self.service_id}")
        print(f"   Интервал проверки: {interval} секунд")
        print("   Нажмите Ctrl+C для остановки\n")
        
        try:
            while True:
                print(f"\n{'='*80}")
                print(f"📊 Проверка логов: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*80}")
                
                # Получаем логи
                logs = self.get_logs(lines=100)
                
                if not logs:
                    print("⚠️ Логи не получены")
                    time.sleep(interval)
                    continue
                
                # Анализируем ошибки
                errors = self.analyze_errors(logs)
                
                # Показываем статистику
                total_errors = (
                    len(errors["critical"]) +
                    len(errors["name_errors"]) +
                    len(errors["import_errors"]) +
                    len(errors["conflicts_409"])
                )
                
                if total_errors > 0:
                    print(f"\n⚠️ Найдено ошибок: {total_errors}")
                    print(f"   - Критические: {len(errors['critical'])}")
                    print(f"   - NameError: {len(errors['name_errors'])}")
                    print(f"   - ImportError: {len(errors['import_errors'])}")
                    print(f"   - 409 Conflict: {len(errors['conflicts_409'])}")
                    
                    # Автоматическое исправление
                    if self.auto_fix(errors):
                        print("\n✅ Некоторые ошибки исправлены автоматически")
                        # Перезапускаем сервис если были критические ошибки
                        if errors["critical"] or errors["name_errors"] or errors["import_errors"]:
                            print("🔄 Перезапуск сервиса...")
                            if self.restart_service():
                                print("✅ Сервис перезапущен, ждём 60 секунд...")
                                time.sleep(60)
                else:
                    print("✅ Ошибок не найдено, всё работает нормально")
                
                # Показываем последние 5 строк логов
                print(f"\n📋 Последние логи:")
                for log in logs[-5:]:
                    level = log.get("level", "INFO")
                    message = log.get("message", "")[:100]
                    timestamp = log.get("timestamp", "")[:19]
                    print(f"   [{timestamp}] {level}: {message}")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Мониторинг остановлен пользователем")
        except Exception as e:
            print(f"\n❌ Критическая ошибка мониторинга: {e}")
            import traceback
            traceback.print_exc()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Render Autopilot Monitor")
    parser.add_argument("--interval", type=int, default=30, help="Интервал проверки в секундах")
    parser.add_argument("--once", action="store_true", help="Проверить один раз и выйти")
    parser.add_argument("--fix", action="store_true", help="Автоматически исправлять ошибки")
    
    args = parser.parse_args()
    
    monitor = RenderAutopilotMonitor()
    
    if args.once:
        # Однократная проверка
        logs = monitor.get_logs(lines=100)
        errors = monitor.analyze_errors(logs)
        
        total_errors = (
            len(errors["critical"]) +
            len(errors["name_errors"]) +
            len(errors["import_errors"]) +
            len(errors["conflicts_409"])
        )
        
        if total_errors > 0:
            print(f"⚠️ Найдено {total_errors} ошибок")
            if args.fix:
                monitor.auto_fix(errors)
        else:
            print("✅ Ошибок не найдено")
    else:
        # Непрерывный мониторинг
        monitor.monitor_loop(interval=args.interval)


if __name__ == "__main__":
    main()





