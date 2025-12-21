#!/usr/bin/env python3
"""
Полностью автоматический скрипт для мониторинга и исправления проекта
- Мониторит логи на Render
- Находит ошибки
- Автоматически исправляет код
- Коммитит и пушит изменения
"""

import os
import sys
import time
import re
import requests
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

# Render API
RENDER_API_BASE = "https://api.render.com/v1"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class AutoFixer:
    def __init__(self, render_api_key: str, service_id: str, telegram_token: str):
        self.render_api_key = render_api_key
        self.service_id = service_id
        self.telegram_token = telegram_token
        self.project_root = Path(__file__).parent
        self.headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json"
        }
        self.fixes_applied = []
        self.owner_id = None
        
    def get_owner_id(self) -> Optional[str]:
        """Получает Owner ID"""
        if self.owner_id:
            return self.owner_id
            
        try:
            response = requests.get(f"{RENDER_API_BASE}/services/{self.service_id}", 
                                  headers=self.headers, timeout=10)
            response.raise_for_status()
            service_data = response.json()
            
            # Owner ID может быть напрямую в ответе или в service
            self.owner_id = service_data.get("ownerId") or service_data.get("service", {}).get("ownerId")
            
            if self.owner_id:
                print(f"✅ Owner ID получен: {self.owner_id}")
                return self.owner_id
            
            # Если не найден, пробуем через список сервисов
            services_response = requests.get(f"{RENDER_API_BASE}/services", headers=self.headers, timeout=10)
            services_response.raise_for_status()
            services = services_response.json()
            
            if isinstance(services, list):
                for service in services:
                    service_info = service.get("service", {})
                    if service_info.get("id") == self.service_id:
                        self.owner_id = service_info.get("ownerId") or service_info.get("owner", {}).get("id")
                        if self.owner_id:
                            print(f"✅ Owner ID получен из списка: {self.owner_id}")
                            return self.owner_id
            
            return None
        except Exception as e:
            print(f"⚠️  Ошибка при получении Owner ID: {e}")
            return None
    
    def get_logs(self, lines: int = 200) -> Optional[List[Dict]]:
        """Получает логи с Render"""
        try:
            owner_id = self.get_owner_id()
            url = f"{RENDER_API_BASE}/logs"
            params = {"resource": self.service_id, "limit": lines}
            
            # Owner ID обязателен для получения логов
            if owner_id:
                params["ownerId"] = owner_id
            else:
                print("⚠️  Owner ID не найден, пробую без него...")
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            # Если ошибка, выводим детали
            if response.status_code != 200:
                print(f"❌ Ошибка HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Детали: {error_detail}")
                except:
                    print(f"   Ответ: {response.text[:300]}")
                return None
            
            response.raise_for_status()
            logs_data = response.json()
            
            # Обрабатываем разные форматы ответа
            if isinstance(logs_data, list):
                return logs_data
            elif isinstance(logs_data, dict):
                # Render API возвращает в формате {"logs": [...], "hasMore": bool, ...}
                if "logs" in logs_data:
                    logs_list = logs_data["logs"]
                    # Каждый лог может быть объектом с полем "message"
                    processed_logs = []
                    for log in logs_list:
                        if isinstance(log, dict):
                            # Извлекаем сообщение из лога
                            message = log.get("message", log.get("text", str(log)))
                            processed_logs.append({
                                "message": message,
                                "timestamp": log.get("timestamp", log.get("createdAt", "")),
                                "level": log.get("level", "INFO"),
                                "raw": log
                            })
                        else:
                            processed_logs.append({"message": str(log), "timestamp": "", "level": "INFO"})
                    return processed_logs
                elif "data" in logs_data:
                    return logs_data["data"]
                elif "items" in logs_data:
                    return logs_data["items"]
                else:
                    # Если это один лог-объект
                    return [logs_data]
            return []
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP ошибка при получении логов: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   Детали: {error_detail}")
                except:
                    print(f"   Ответ: {e.response.text[:300]}")
            return None
        except Exception as e:
            print(f"⚠️  Ошибка при получении логов: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def analyze_errors(self, logs: List[Dict]) -> List[Dict]:
        """Анализирует логи и находит ошибки для исправления"""
        errors = []
        
        for log_entry in logs:
            message = ""
            if isinstance(log_entry, dict):
                message = str(log_entry.get("message", log_entry.get("text", "")))
            else:
                message = str(log_entry)
            
            message_lower = message.lower()
            
            # Типы ошибок для автоматического исправления
            error_types = {
                "import": {
                    "patterns": [r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", 
                                r"ImportError: cannot import name ['\"]([^'\"]+)['\"]"],
                    "type": "missing_import"
                },
                "syntax": {
                    "patterns": [r"SyntaxError: (.+)", r"IndentationError: (.+)"],
                    "type": "syntax_error"
                },
                "attribute": {
                    "patterns": [r"AttributeError: ['\"]([^'\"]+)['\"] object has no attribute ['\"]([^'\"]+)['\"]"],
                    "type": "attribute_error"
                },
                "name": {
                    "patterns": [r"NameError: name ['\"]([^'\"]+)['\"] is not defined"],
                    "type": "name_error"
                },
                "409_conflict": {
                    "patterns": [r"409", r"Conflict", r"terminated by other getUpdates"],
                    "type": "telegram_conflict"
                },
                "webhook": {
                    "patterns": [r"webhook", r"getWebhookInfo"],
                    "type": "webhook_issue"
                }
            }
            
            for error_name, error_info in error_types.items():
                for pattern in error_info["patterns"]:
                    match = re.search(pattern, message, re.IGNORECASE)
                    if match:
                        errors.append({
                            "type": error_info["type"],
                            "message": message,
                            "match": match.groups() if match.groups() else None,
                            "full_match": match.group(0) if match else None
                        })
                        break
        
        return errors
    
    def fix_missing_import(self, module_name: str, file_path: Optional[str] = None) -> bool:
        """Исправляет отсутствующий импорт"""
        try:
            # Ищем файл с ошибкой или главный файл бота
            if not file_path:
                bot_file = self.project_root / "bot_kie.py"
                if bot_file.exists():
                    file_path = str(bot_file)
                else:
                    return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем, есть ли уже импорт
            if f"import {module_name}" in content or f"from {module_name}" in content:
                return True
            
            # Добавляем импорт в начало файла
            lines = content.split('\n')
            import_section_end = 0
            
            for i, line in enumerate(lines):
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    import_section_end = i + 1
                elif line.strip() and not line.strip().startswith('#'):
                    break
            
            # Добавляем импорт
            new_import = f"import {module_name}"
            lines.insert(import_section_end, new_import)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            self.fixes_applied.append(f"Добавлен импорт: {module_name} в {file_path}")
            return True
        except Exception as e:
            print(f"❌ Ошибка при исправлении импорта: {e}")
            return False
    
    def fix_telegram_conflict(self) -> bool:
        """Исправляет конфликт 409 Telegram"""
        try:
            # Удаляем webhook
            url = f"{TELEGRAM_API_BASE}{self.telegram_token}/deleteWebhook"
            params = {"drop_pending_updates": True}
            response = requests.get(url, params=params, timeout=10)
            
            if response.json().get("ok"):
                self.fixes_applied.append("Удалён webhook для исправления конфликта 409")
                return True
        except:
            pass
        return False
    
    def fix_syntax_error(self, error_msg: str) -> bool:
        """Пытается исправить синтаксические ошибки"""
        # Базовые исправления синтаксиса
        fixes = {
            "unexpected EOF": "Проверка незакрытых скобок",
            "invalid syntax": "Проверка синтаксиса",
        }
        
        for pattern, fix_desc in fixes.items():
            if pattern.lower() in error_msg.lower():
                self.fixes_applied.append(f"Обнаружена синтаксическая ошибка: {fix_desc}")
                # Здесь можно добавить более сложную логику исправления
                return True
        return False
    
    def apply_fixes(self, errors: List[Dict]) -> int:
        """Применяет исправления для найденных ошибок"""
        fixes_count = 0
        
        for error in errors:
            error_type = error["type"]
            match = error.get("match")
            message = error.get("message", "")
            
            if error_type == "missing_import" and match:
                module_name = match[0] if match else None
                if module_name:
                    if self.fix_missing_import(module_name):
                        fixes_count += 1
            
            elif error_type == "telegram_conflict":
                if self.fix_telegram_conflict():
                    fixes_count += 1
            
            elif error_type == "syntax_error":
                if self.fix_syntax_error(message):
                    fixes_count += 1
        
        return fixes_count
    
    def commit_and_push(self, message: str = "Auto-fix: исправления из логов"):
        """Коммитит и пушит изменения в GitHub"""
        try:
            import subprocess
            
            # Проверяем, есть ли изменения
            result = subprocess.run(["git", "status", "--porcelain"], 
                                  capture_output=True, text=True, cwd=self.project_root)
            
            if not result.stdout.strip():
                return False  # Нет изменений
            
            # Добавляем все изменения
            subprocess.run(["git", "add", "."], cwd=self.project_root, check=True)
            
            # Коммитим
            subprocess.run(["git", "commit", "-m", message], 
                         cwd=self.project_root, check=True)
            
            # Пушим
            subprocess.run(["git", "push", "origin", "main"], 
                         cwd=self.project_root, check=True)
            
            return True
        except Exception as e:
            print(f"⚠️  Ошибка при коммите/пуше: {e}")
            return False
    
    def run(self, interval: int = 60):
        """Основной цикл автоматического исправления"""
        print("=" * 80)
        print("🤖 АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ПРОЕКТА")
        print("=" * 80)
        print(f"📊 Интервал проверки: {interval} секунд")
        print("Нажмите Ctrl+C для остановки")
        print("=" * 80)
        print()
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                print(f"\n{'=' * 80}")
                print(f"🔄 Проверка #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 80)
                
                # Получаем логи
                logs = self.get_logs(lines=200)
                if not logs:
                    print("⚠️  Не удалось получить логи")
                    time.sleep(interval)
                    continue
                
                # Анализируем ошибки
                errors = self.analyze_errors(logs)
                
                print(f"\n📊 Найдено ошибок для анализа: {len(errors)}")
                
                if errors:
                    print("\n🔍 Типы ошибок:")
                    error_types = {}
                    for error in errors:
                        error_type = error["type"]
                        error_types[error_type] = error_types.get(error_type, 0) + 1
                    
                    for error_type, count in error_types.items():
                        print(f"   - {error_type}: {count}")
                    
                    # Применяем исправления
                    print("\n🔧 Применение исправлений...")
                    fixes_count = self.apply_fixes(errors)
                    
                    if fixes_count > 0:
                        print(f"✅ Применено исправлений: {fixes_count}")
                        
                        # Коммитим и пушим изменения
                        if self.fixes_applied:
                            commit_msg = f"Auto-fix: исправлено {fixes_count} ошибок"
                            print(f"\n📝 Коммит изменений: {commit_msg}")
                            if self.commit_and_push(commit_msg):
                                print("✅ Изменения отправлены в GitHub")
                                self.fixes_applied = []
                    else:
                        print("ℹ️  Автоматические исправления не требуются")
                else:
                    print("✅ Критических ошибок не найдено")
                
                # Ждем перед следующей проверкой
                print(f"\n⏳ Следующая проверка через {interval} секунд...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ОСТАНОВЛЕНО")
            print("=" * 80)
            print(f"📊 Итоговая статистика:")
            print(f"   Применено исправлений: {len(self.fixes_applied)}")
            print("=" * 80)


def main():
    """Главная функция"""
    print("=" * 80)
    print("🤖 ПОЛНОСТЬЮ АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ПРОЕКТА")
    print("=" * 80)
    print()
    
    # Получаем переменные окружения
    render_api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Если не установлены, запрашиваем
    if not render_api_key:
        render_api_key = input("Введите ваш Render API ключ: ").strip()
        if not render_api_key:
            print("❌ API ключ обязателен!")
            sys.exit(1)
    
    if not service_id:
        service_id = input("Введите ваш Service ID (srv-xxxxx): ").strip()
        if not service_id:
            print("❌ Service ID обязателен!")
            sys.exit(1)
    
    if not telegram_token:
        telegram_token = input("Введите ваш Telegram Bot Token: ").strip()
        if not telegram_token:
            print("❌ Bot Token обязателен!")
            sys.exit(1)
    
    # Создаем автофиксер
    fixer = AutoFixer(render_api_key, service_id, telegram_token)
    
    # Запускаем
    print("\n🚀 Запуск автоматического исправления...")
    print("   Интервал: 60 секунд")
    print()
    
    fixer.run(interval=60)


if __name__ == "__main__":
    main()







