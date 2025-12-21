#!/usr/bin/env python3
"""
Интеграция с Cursor для автоматического исправления ошибок по логам
Создаёт задачи для Cursor AI на основе ошибок из логов
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# Render API
RENDER_API_BASE = "https://api.render.com/v1"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class CursorAutoFix:
    def __init__(self, render_api_key: str, service_id: str, telegram_token: str):
        self.render_api_key = render_api_key
        self.service_id = service_id
        self.telegram_token = telegram_token
        self.project_root = Path(__file__).parent
        self.headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json"
        }
        self.owner_id = None
        self.tasks_file = self.project_root / ".cursor" / "auto_fix_tasks.json"
        self.tasks_file.parent.mkdir(exist_ok=True)
        
    def get_owner_id(self) -> Optional[str]:
        """Получает Owner ID"""
        if self.owner_id:
            return self.owner_id
            
        try:
            response = requests.get(f"{RENDER_API_BASE}/services/{self.service_id}", 
                                  headers=self.headers, timeout=10)
            response.raise_for_status()
            service_data = response.json()
            self.owner_id = service_data.get("ownerId") or service_data.get("service", {}).get("ownerId")
            return self.owner_id
        except Exception as e:
            print(f"⚠️  Ошибка при получении Owner ID: {e}")
            return None
    
    def get_logs(self, lines: int = 200) -> Optional[List[Dict]]:
        """Получает логи с Render"""
        try:
            owner_id = self.get_owner_id()
            if not owner_id:
                print("❌ Owner ID не найден, невозможно получить логи")
                return None
                
            url = f"{RENDER_API_BASE}/logs"
            params = {
                "ownerId": owner_id,
                "resource": self.service_id,
                "limit": lines
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ Ошибка HTTP {response.status_code}: {response.text[:300]}")
                return None
            
            logs_data = response.json()
            
            # Обрабатываем разные форматы
            if isinstance(logs_data, list):
                return logs_data
            elif isinstance(logs_data, dict):
                # Render API возвращает в формате {"logs": [...], "hasMore": bool, ...}
                if "logs" in logs_data:
                    logs_list = logs_data["logs"]
                    # Обрабатываем каждый лог
                    processed_logs = []
                    for log in logs_list:
                        if isinstance(log, dict):
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
                return logs_data.get("data") or logs_data.get("items") or []
            return []
        except Exception as e:
            print(f"❌ Ошибка при получении логов: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def analyze_errors(self, logs: List[Dict]) -> List[Dict]:
        """Анализирует логи и создаёт задачи для Cursor"""
        tasks = []
        seen_errors = set()
        
        for log_entry in logs:
            message = ""
            if isinstance(log_entry, dict):
                message = str(log_entry.get("message", log_entry.get("text", "")))
                timestamp = log_entry.get("timestamp", log_entry.get("createdAt", ""))
            else:
                message = str(log_entry)
                timestamp = ""
            
            message_lower = message.lower()
            
            # Создаём уникальный ключ для ошибки
            error_hash = hash(message[:200])
            if error_hash in seen_errors:
                continue
            seen_errors.add(error_hash)
            
            # Определяем тип ошибки и создаём задачу
            if "modulenotfounderror" in message_lower or "no module named" in message_lower:
                import re
                match = re.search(r"no module named ['\"]([^'\"]+)['\"]", message_lower)
                if match:
                    module_name = match.group(1)
                    tasks.append({
                        "type": "missing_import",
                        "error": message,
                        "module": module_name,
                        "timestamp": timestamp,
                        "fix": f"Добавить импорт: import {module_name}",
                        "priority": "high"
                    })
            
            elif "409" in message or "conflict" in message_lower or "terminated by other getUpdates" in message_lower:
                tasks.append({
                    "type": "telegram_conflict",
                    "error": message,
                    "timestamp": timestamp,
                    "fix": "Удалить webhook и перезапустить сервис",
                    "priority": "critical"
                })
            
            elif "syntaxerror" in message_lower or "indentationerror" in message_lower:
                tasks.append({
                    "type": "syntax_error",
                    "error": message,
                    "timestamp": timestamp,
                    "fix": "Исправить синтаксическую ошибку",
                    "priority": "high"
                })
            
            elif "attributeerror" in message_lower:
                tasks.append({
                    "type": "attribute_error",
                    "error": message,
                    "timestamp": timestamp,
                    "fix": "Исправить обращение к атрибуту",
                    "priority": "medium"
                })
            
            elif "nameerror" in message_lower or "is not defined" in message_lower:
                tasks.append({
                    "type": "name_error",
                    "error": message,
                    "timestamp": timestamp,
                    "fix": "Исправить неопределённую переменную",
                    "priority": "medium"
                })
            
            elif "error" in message_lower and any(keyword in message_lower for keyword in ["failed", "exception", "traceback"]):
                tasks.append({
                    "type": "general_error",
                    "error": message,
                    "timestamp": timestamp,
                    "fix": "Проанализировать и исправить ошибку",
                    "priority": "medium"
                })
        
        return tasks
    
    def save_tasks(self, tasks: List[Dict]):
        """Сохраняет задачи в файл для Cursor"""
        try:
            existing_tasks = []
            if self.tasks_file.exists():
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    existing_tasks = json.load(f)
            
            # Добавляем новые задачи
            existing_hashes = {hash(t.get("error", "")[:200]) for t in existing_tasks}
            new_tasks = []
            
            for task in tasks:
                task_hash = hash(task.get("error", "")[:200])
                if task_hash not in existing_hashes:
                    task["created_at"] = datetime.now().isoformat()
                    task["status"] = "pending"
                    new_tasks.append(task)
                    existing_tasks.append(task)
            
            # Сохраняем все задачи
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(existing_tasks, f, ensure_ascii=False, indent=2)
            
            return len(new_tasks)
        except Exception as e:
            print(f"❌ Ошибка при сохранении задач: {e}")
            return 0
    
    def create_cursor_prompt_file(self, tasks: List[Dict]):
        """Создаёт файл с промптом для Cursor AI"""
        if not tasks:
            return
        
        prompt_file = self.project_root / ".cursor" / "auto_fix_prompt.md"
        
        critical_tasks = [t for t in tasks if t.get("priority") == "critical"]
        high_tasks = [t for t in tasks if t.get("priority") == "high"]
        other_tasks = [t for t in tasks if t.get("priority") not in ["critical", "high"]]
        
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write("# 🤖 Автоматические задачи для исправления\n\n")
            f.write(f"**Создано:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 🚨 КРИТИЧЕСКИЕ ОШИБКИ\n\n")
            
            if critical_tasks:
                for i, task in enumerate(critical_tasks, 1):
                    f.write(f"### Задача {i}: {task['type']}\n\n")
                    f.write(f"**Ошибка:**\n```\n{task['error'][:500]}\n```\n\n")
                    f.write(f"**Исправление:** {task['fix']}\n\n")
                    f.write("---\n\n")
            else:
                f.write("Критических ошибок не найдено.\n\n")
            
            f.write("## ⚠️ ВЫСОКИЙ ПРИОРИТЕТ\n\n")
            if high_tasks:
                for i, task in enumerate(high_tasks, 1):
                    f.write(f"### Задача {i}: {task['type']}\n\n")
                    f.write(f"**Ошибка:**\n```\n{task['error'][:300]}\n```\n\n")
                    f.write(f"**Исправление:** {task['fix']}\n\n")
                    f.write("---\n\n")
            else:
                f.write("Ошибок высокого приоритета не найдено.\n\n")
            
            if other_tasks:
                f.write("## 📋 ДРУГИЕ ОШИБКИ\n\n")
                for i, task in enumerate(other_tasks[:10], 1):  # Ограничиваем до 10
                    f.write(f"### Задача {i}: {task['type']}\n\n")
                    f.write(f"**Ошибка:**\n```\n{task['error'][:200]}\n```\n\n")
                    f.write("---\n\n")
        
        print(f"✅ Промпт для Cursor создан: {prompt_file}")
    
    def run(self, interval: int = 60):
        """Основной цикл мониторинга и создания задач"""
        print("=" * 80)
        print("🤖 АВТОМАТИЧЕСКОЕ СОЗДАНИЕ ЗАДАЧ ДЛЯ CURSOR")
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
                
                print(f"✅ Получено {len(logs)} строк логов")
                
                # Анализируем ошибки
                tasks = self.analyze_errors(logs)
                
                if tasks:
                    print(f"\n📊 Найдено ошибок: {len(tasks)}")
                    
                    # Группируем по приоритетам
                    critical = [t for t in tasks if t.get("priority") == "critical"]
                    high = [t for t in tasks if t.get("priority") == "high"]
                    medium = [t for t in tasks if t.get("priority") == "medium"]
                    
                    print(f"   🚨 Критических: {len(critical)}")
                    print(f"   ⚠️  Высокий приоритет: {len(high)}")
                    print(f"   📋 Средний приоритет: {len(medium)}")
                    
                    # Сохраняем задачи
                    new_tasks_count = self.save_tasks(tasks)
                    if new_tasks_count > 0:
                        print(f"✅ Сохранено новых задач: {new_tasks_count}")
                    
                    # Создаём промпт для Cursor
                    self.create_cursor_prompt_file(tasks)
                    
                    print("\n💡 Откройте файл .cursor/auto_fix_prompt.md в Cursor для просмотра задач")
                else:
                    print("✅ Критических ошибок не найдено")
                
                # Ждем перед следующей проверкой
                print(f"\n⏳ Следующая проверка через {interval} секунд...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 МОНИТОРИНГ ОСТАНОВЛЕН")
            print("=" * 80)


def main():
    """Главная функция"""
    print("=" * 80)
    print("🤖 ИНТЕГРАЦИЯ С CURSOR ДЛЯ АВТОМАТИЧЕСКОГО ИСПРАВЛЕНИЯ")
    print("=" * 80)
    print()
    
    # Получаем переменные окружения
    render_api_key = os.getenv("RENDER_API_KEY", "rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw")
    service_id = os.getenv("RENDER_SERVICE_ID", "srv-d4s025er433s73bsf62g")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y")
    
    # Создаём интегратор
    integrator = CursorAutoFix(render_api_key, service_id, telegram_token)
    
    # Запускаем
    print("\n🚀 Запуск мониторинга...")
    print("   Интервал: 60 секунд")
    print()
    
    integrator.run(interval=60)


if __name__ == "__main__":
    main()







