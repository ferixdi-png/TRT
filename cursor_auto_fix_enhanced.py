#!/usr/bin/env python3
"""
Улучшенная версия интеграции с Cursor для автоматического исправления
- Анализирует контекст проекта
- Связывает ошибки с конкретными файлами и функциями
- Создаёт детальные задачи с контекстом
"""

import os
import sys
import json
import time
import re
import ast
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Set

# Render API
RENDER_API_BASE = "https://api.render.com/v1"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class ProjectContext:
    """Анализирует структуру проекта для контекстного понимания"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.main_files = {}
        self.imports_map = {}
        self.functions_map = {}
        self.classes_map = {}
        
    def analyze_project(self):
        """Анализирует структуру проекта"""
        print("🔍 Анализ структуры проекта...")
        
        # Основные файлы проекта
        main_files = [
            "bot_kie.py",
            "run_bot.py",
            "database.py",
            "kie_gateway.py",
            "kie_models.py",
            "business_layer.py"
        ]
        
        for file_name in main_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                self.analyze_file(file_path)
        
        print(f"✅ Проанализировано файлов: {len(self.main_files)}")
        print(f"   Функций: {len(self.functions_map)}")
        print(f"   Классов: {len(self.classes_map)}")
        print(f"   Импортов: {len(self.imports_map)}")
    
    def analyze_file(self, file_path: Path):
        """Анализирует один файл"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.main_files[str(file_path)] = {
                "size": len(content),
                "lines": content.count('\n')
            }
            
            # Парсим AST для поиска функций и классов
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        self.functions_map[node.name] = {
                            "file": str(file_path),
                            "line": node.lineno
                        }
                    elif isinstance(node, ast.ClassDef):
                        self.classes_map[node.name] = {
                            "file": str(file_path),
                            "line": node.lineno
                        }
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        if isinstance(node, ast.ImportFrom):
                            module = node.module or ""
                            for alias in node.names:
                                self.imports_map[alias.name] = module
                        else:
                            for alias in node.names:
                                self.imports_map[alias.name] = ""
            except:
                pass  # Если не удалось распарсить, пропускаем
                
        except Exception as e:
            pass
    
    def find_file_with_error(self, error_message: str) -> Optional[str]:
        """Находит файл, связанный с ошибкой"""
        # Ищем упоминания файлов в traceback
        file_match = re.search(r'File "([^"]+)"', error_message)
        if file_match:
            return file_match.group(1)
        
        # Ищем упоминания функций
        for func_name, func_info in self.functions_map.items():
            if func_name in error_message:
                return func_info["file"]
        
        return None
    
    def get_related_context(self, error_message: str) -> Dict:
        """Получает контекст, связанный с ошибкой"""
        context = {
            "files": [],
            "functions": [],
            "imports": [],
            "suggestions": []
        }
        
        # Ищем упоминания модулей
        if "no module named" in error_message.lower():
            match = re.search(r"no module named ['\"]([^'\"]+)['\"]", error_message.lower())
            if match:
                module_name = match.group(1)
                context["imports"].append(module_name)
                context["suggestions"].append(f"Добавить 'import {module_name}' в начало файла")
        
        # Ищем упоминания функций
        for func_name, func_info in self.functions_map.items():
            if func_name in error_message:
                context["functions"].append({
                    "name": func_name,
                    "file": func_info["file"],
                    "line": func_info["line"]
                })
        
        # Ищем упоминания классов
        for class_name, class_info in self.classes_map.items():
            if class_name in error_message:
                context["files"].append(class_info["file"])
        
        # Ищем файл из traceback
        file_path = self.find_file_with_error(error_message)
        if file_path:
            context["files"].append(file_path)
        
        return context


class EnhancedCursorAutoFix:
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
        self.prompt_file = self.project_root / ".cursor" / "auto_fix_prompt.md"
        self.tasks_file.parent.mkdir(exist_ok=True)
        
        # Анализируем проект для контекста
        self.context = ProjectContext(self.project_root)
        self.context.analyze_project()
        
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
                if "logs" in logs_data:
                    logs_list = logs_data["logs"]
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
    
    def analyze_errors_with_context(self, logs: List[Dict]) -> List[Dict]:
        """Анализирует логи с контекстом проекта"""
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
            
            # Получаем контекст для ошибки
            error_context = self.context.get_related_context(message)
            
            # Определяем тип ошибки и создаём задачу с контекстом
            if "modulenotfounderror" in message_lower or "no module named" in message_lower:
                import re
                match = re.search(r"no module named ['\"]([^'\"]+)['\"]", message_lower)
                if match:
                    module_name = match.group(1)
                    file_path = error_context.get("files", [None])[0] if error_context.get("files") else None
                    
                    tasks.append({
                        "type": "missing_import",
                        "error": message,
                        "module": module_name,
                        "timestamp": timestamp,
                        "context": error_context,
                        "file": file_path or "bot_kie.py",  # По умолчанию главный файл
                        "fix": f"Добавить импорт: import {module_name} в начало файла {file_path or 'bot_kie.py'}",
                        "priority": "high",
                        "code_context": f"Ошибка в файле: {file_path or 'bot_kie.py'}. Нужно добавить 'import {module_name}' в секцию импортов."
                    })
            
            elif "asyncio.run() cannot be called" in message or "running event loop" in message_lower:
                file_path = error_context.get("files", [None])[0] if error_context.get("files") else "bot_kie.py"
                tasks.append({
                    "type": "asyncio_error",
                    "error": message,
                    "timestamp": timestamp,
                    "context": error_context,
                    "file": file_path,
                    "fix": f"Заменить asyncio.run() на await в файле {file_path}",
                    "priority": "critical",
                    "code_context": f"В файле {file_path} используется asyncio.run() внутри async функции. Нужно заменить на await."
                })
            
            elif "409" in message or "conflict" in message_lower or "terminated by other getUpdates" in message_lower:
                tasks.append({
                    "type": "telegram_conflict",
                    "error": message,
                    "timestamp": timestamp,
                    "context": error_context,
                    "fix": "Удалить webhook через Telegram API и перезапустить сервис на Render",
                    "priority": "critical",
                    "code_context": "Конфликт 409 означает, что запущено несколько экземпляров бота. Нужно: 1) Удалить webhook через deleteWebhook API, 2) Проверить, что только один сервис запущен на Render, 3) Перезапустить сервис."
                })
            
            elif "syntaxerror" in message_lower or "indentationerror" in message_lower:
                file_path = error_context.get("files", [None])[0] if error_context.get("files") else None
                tasks.append({
                    "type": "syntax_error",
                    "error": message,
                    "timestamp": timestamp,
                    "context": error_context,
                    "file": file_path,
                    "fix": f"Исправить синтаксическую ошибку в {file_path or 'коде'}",
                    "priority": "high",
                    "code_context": f"Синтаксическая ошибка в файле {file_path or 'неизвестном'}. Проверить скобки, отступы, кавычки."
                })
            
            elif "attributeerror" in message_lower:
                file_path = error_context.get("files", [None])[0] if error_context.get("files") else None
                tasks.append({
                    "type": "attribute_error",
                    "error": message,
                    "timestamp": timestamp,
                    "context": error_context,
                    "file": file_path,
                    "fix": f"Исправить обращение к атрибуту в {file_path or 'коде'}",
                    "priority": "medium",
                    "code_context": f"Ошибка атрибута в файле {file_path or 'неизвестном'}. Проверить, что объект имеет нужный атрибут."
                })
            
            elif "nameerror" in message_lower or "is not defined" in message_lower:
                file_path = error_context.get("files", [None])[0] if error_context.get("files") else None
                match = re.search(r"name ['\"]([^'\"]+)['\"] is not defined", message_lower)
                var_name = match.group(1) if match else None
                
                tasks.append({
                    "type": "name_error",
                    "error": message,
                    "timestamp": timestamp,
                    "context": error_context,
                    "file": file_path,
                    "variable": var_name,
                    "fix": f"Исправить неопределённую переменную '{var_name}' в {file_path or 'коде'}" if var_name else f"Исправить неопределённую переменную в {file_path or 'коде'}",
                    "priority": "medium",
                    "code_context": f"Переменная '{var_name}' не определена в файле {file_path or 'неизвестном'}. Нужно определить переменную или импортировать её."
                })
            
            elif "error" in message_lower and any(keyword in message_lower for keyword in ["failed", "exception", "traceback"]):
                file_path = error_context.get("files", [None])[0] if error_context.get("files") else None
                tasks.append({
                    "type": "general_error",
                    "error": message,
                    "timestamp": timestamp,
                    "context": error_context,
                    "file": file_path,
                    "fix": f"Проанализировать и исправить ошибку в {file_path or 'коде'}",
                    "priority": "medium",
                    "code_context": f"Общая ошибка в файле {file_path or 'неизвестном'}. Нужно проанализировать traceback и исправить."
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
    
    def create_enhanced_cursor_prompt(self, tasks: List[Dict]):
        """Создаёт улучшенный промпт для Cursor с контекстом"""
        if not tasks:
            return
        
        critical_tasks = [t for t in tasks if t.get("priority") == "critical"]
        high_tasks = [t for t in tasks if t.get("priority") == "high"]
        other_tasks = [t for t in tasks if t.get("priority") not in ["critical", "high"]]
        
        with open(self.prompt_file, 'w', encoding='utf-8') as f:
            f.write("# 🤖 Автоматические задачи для исправления (с контекстом проекта)\n\n")
            f.write(f"**Создано:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 📋 КОНТЕКСТ ПРОЕКТА\n\n")
            f.write("**Структура проекта:**\n")
            f.write("- Основной файл: `bot_kie.py` (Telegram бот)\n")
            f.write("- База данных: `database.py` (PostgreSQL через asyncpg)\n")
            f.write("- KIE API: `kie_gateway.py`, `kie_models.py`\n")
            f.write("- Бизнес-логика: `business_layer.py`\n")
            f.write("- Запуск: `run_bot.py`\n\n")
            f.write("**Деплой:** Render.com (Web Service, Docker)\n")
            f.write("**База данных:** Render PostgreSQL (shared)\n\n")
            f.write("---\n\n")
            
            f.write("## 🚨 КРИТИЧЕСКИЕ ОШИБКИ\n\n")
            
            if critical_tasks:
                for i, task in enumerate(critical_tasks, 1):
                    f.write(f"### Задача {i}: {task['type']}\n\n")
                    f.write(f"**Файл:** `{task.get('file', 'неизвестен')}`\n\n")
                    f.write(f"**Ошибка:**\n```\n{task['error'][:500]}\n```\n\n")
                    
                    if task.get("code_context"):
                        f.write(f"**Контекст кода:**\n{task['code_context']}\n\n")
                    
                    if task.get("context", {}).get("files"):
                        f.write(f"**Связанные файлы:** {', '.join(task['context']['files'][:3])}\n\n")
                    
                    if task.get("context", {}).get("functions"):
                        f.write("**Связанные функции:**\n")
                        for func in task['context']['functions'][:3]:
                            f.write(f"- `{func['name']}` в `{func['file']}` (строка {func['line']})\n")
                        f.write("\n")
                    
                    f.write(f"**Исправление:** {task['fix']}\n\n")
                    f.write("---\n\n")
            else:
                f.write("Критических ошибок не найдено.\n\n")
            
            f.write("## ⚠️ ВЫСОКИЙ ПРИОРИТЕТ\n\n")
            if high_tasks:
                for i, task in enumerate(high_tasks, 1):
                    f.write(f"### Задача {i}: {task['type']}\n\n")
                    f.write(f"**Файл:** `{task.get('file', 'неизвестен')}`\n\n")
                    f.write(f"**Ошибка:**\n```\n{task['error'][:300]}\n```\n\n")
                    
                    if task.get("code_context"):
                        f.write(f"**Контекст:** {task['code_context']}\n\n")
                    
                    f.write(f"**Исправление:** {task['fix']}\n\n")
                    f.write("---\n\n")
            else:
                f.write("Ошибок высокого приоритета не найдено.\n\n")
            
            if other_tasks:
                f.write("## 📋 ДРУГИЕ ОШИБКИ\n\n")
                for i, task in enumerate(other_tasks[:10], 1):
                    f.write(f"### Задача {i}: {task['type']}\n\n")
                    f.write(f"**Файл:** `{task.get('file', 'неизвестен')}`\n\n")
                    f.write(f"**Ошибка:**\n```\n{task['error'][:200]}\n```\n\n")
                    f.write("---\n\n")
        
        print(f"✅ Улучшенный промпт для Cursor создан: {self.prompt_file}")
    
    def run(self, interval: int = 60):
        """Основной цикл мониторинга и создания задач"""
        print("=" * 80)
        print("🤖 УЛУЧШЕННАЯ ИНТЕГРАЦИЯ С CURSOR (С КОНТЕКСТОМ ПРОЕКТА)")
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
                
                # Анализируем ошибки с контекстом
                tasks = self.analyze_errors_with_context(logs)
                
                if tasks:
                    print(f"\n📊 Найдено ошибок: {len(tasks)}")
                    
                    # Группируем по приоритетам
                    critical = [t for t in tasks if t.get("priority") == "critical"]
                    high = [t for t in tasks if t.get("priority") == "high"]
                    medium = [t for t in tasks if t.get("priority") == "medium"]
                    
                    print(f"   🚨 Критических: {len(critical)}")
                    print(f"   ⚠️  Высокий приоритет: {len(high)}")
                    print(f"   📋 Средний приоритет: {len(medium)}")
                    
                    # Показываем контекст
                    files_mentioned = set()
                    for task in tasks:
                        if task.get("file"):
                            files_mentioned.add(task["file"])
                    
                    if files_mentioned:
                        print(f"\n📁 Затронутые файлы: {', '.join(list(files_mentioned)[:5])}")
                    
                    # Сохраняем задачи
                    new_tasks_count = self.save_tasks(tasks)
                    if new_tasks_count > 0:
                        print(f"✅ Сохранено новых задач: {new_tasks_count}")
                    
                    # Создаём улучшенный промпт для Cursor
                    self.create_enhanced_cursor_prompt(tasks)
                    
                    print("\n💡 Откройте файл .cursor/auto_fix_prompt.md в Cursor")
                    print("   Cursor автоматически увидит задачи с контекстом проекта")
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
    print("🤖 УЛУЧШЕННАЯ ИНТЕГРАЦИЯ С CURSOR (С КОНТЕКСТОМ ПРОЕКТА)")
    print("=" * 80)
    print()
    
    # Получаем переменные окружения
    render_api_key = os.getenv("RENDER_API_KEY", "")
    service_id = os.getenv("RENDER_SERVICE_ID", "")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Создаём интегратор
    integrator = EnhancedCursorAutoFix(render_api_key, service_id, telegram_token)
    
    # Запускаем
    print("\n🚀 Запуск мониторинга...")
    print("   Интервал: 60 секунд")
    print()
    
    integrator.run(interval=60)


if __name__ == "__main__":
    main()







