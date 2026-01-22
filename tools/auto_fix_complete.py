#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Полностью автоматизированная система исправления ошибок
- Проверяет статус деплоя на Render
- Ждёт завершения деплоя перед проверкой ошибок
- Автоматически исправляет ошибки
- Коммитит и пушит изменения
- Ждёт завершения деплоя после исправлений
- Понятный вывод о всех действиях
"""

import os
import sys
import json
import time
import re
import ast
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Set

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Render API
RENDER_API_BASE = "https://api.render.com/v1"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

class DeploymentChecker:
    """Проверяет статус деплоя на Render"""
    
    def __init__(self, api_key: str, service_id: str):
        self.api_key = api_key
        self.service_id = service_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
    
    def get_latest_deploy(self) -> Optional[Dict]:
        """Получает последний деплой"""
        try:
            url = f"{RENDER_API_BASE}/services/{self.service_id}/deploys"
            response = requests.get(url, headers=self.headers, params={"limit": 1}, timeout=10)
            if response.status_code == 200:
                deploys = response.json()
                if isinstance(deploys, list) and len(deploys) > 0:
                    return deploys[0]
                elif isinstance(deploys, dict) and "deploys" in deploys:
                    deploys_list = deploys["deploys"]
                    if len(deploys_list) > 0:
                        return deploys_list[0]
            return None
        except Exception as e:
            print(f"⚠️  Ошибка при получении деплоя: {e}")
            return None
    
    def is_deploying(self) -> bool:
        """Проверяет, идёт ли сейчас деплой"""
        deploy = self.get_latest_deploy()
        if not deploy:
            return False
        
        status = deploy.get("status", "").lower()
        return status in ["building", "updating", "live_in_progress", "pending"]
    
    def wait_for_deploy_complete(self, timeout: int = 600) -> bool:
        """Ждёт завершения деплоя"""
        start_time = time.time()
        last_status = None
        
        print("\n" + "=" * 80)
        print("⏳ ПРОВЕРКА СТАТУСА ДЕПЛОЯ")
        print("=" * 80)
        
        while time.time() - start_time < timeout:
            deploy = self.get_latest_deploy()
            if not deploy:
                print("⚠️  Не удалось получить статус деплоя, продолжаем...")
                return True
            
            status = deploy.get("status", "unknown")
            if status != last_status:
                print(f"📊 Статус деплоя: {status}")
                last_status = status
            
            if status.lower() in ["live", "succeeded", "complete"]:
                print("✅ Деплой завершён успешно!")
                return True
            elif status.lower() in ["failed", "canceled", "error"]:
                print(f"❌ Деплой завершился с ошибкой: {status}")
                return False
            elif status.lower() in ["building", "updating", "live_in_progress", "pending"]:
                elapsed = int(time.time() - start_time)
                print(f"⏳ Деплой в процессе... ({elapsed} сек)")
                time.sleep(10)
            else:
                print(f"⚠️  Неизвестный статус: {status}, продолжаем...")
                time.sleep(5)
        
        print("⏰ Превышено время ожидания деплоя")
        return False


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
        
        main_files = [
            "bot_kie.py", "run_bot.py", "database.py",
            "kie_gateway.py", "kie_models.py", "business_layer.py"
        ]
        
        for file_name in main_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                self.analyze_file(file_path)
        
        print(f"✅ Проанализировано: {len(self.main_files)} файлов, {len(self.functions_map)} функций")
    
    def analyze_file(self, file_path: Path):
        """Анализирует один файл"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.main_files[str(file_path)] = {
                "size": len(content),
                "lines": content.count('\n')
            }
            
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
            except:
                pass
        except Exception:
            pass
    
    def find_file_with_error(self, error_message: str) -> Optional[str]:
        """Находит файл, связанный с ошибкой"""
        file_match = re.search(r'File "([^"]+)"', error_message)
        if file_match:
            return file_match.group(1)
        
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
        
        if "no module named" in error_message.lower():
            match = re.search(r"no module named ['\"]([^'\"]+)['\"]", error_message.lower())
            if match:
                module_name = match.group(1)
                context["imports"].append(module_name)
                context["suggestions"].append(f"Добавить 'import {module_name}'")
        
        for func_name, func_info in self.functions_map.items():
            if func_name in error_message:
                context["functions"].append({
                    "name": func_name,
                    "file": func_info["file"],
                    "line": func_info["line"]
                })
        
        file_path = self.find_file_with_error(error_message)
        if file_path:
            context["files"].append(file_path)
        
        return context


class AutoFixer:
    """Автоматически исправляет ошибки"""
    
    def __init__(self, project_root: Path, context: ProjectContext, render_api_key: str, service_id: str):
        self.project_root = project_root
        self.context = context
        self.fixes_applied = []
        self.render_api_key = render_api_key
        self.service_id = service_id
        self.headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json"
        }
    
    def fix_missing_import(self, module_name: str, file_path: Optional[str] = None) -> bool:
        """Исправляет отсутствующий импорт"""
        if not file_path:
            file_path = "bot_kie.py"
        
        file_path_obj = self.project_root / file_path
        if not file_path_obj.exists():
            print(f"⚠️  Файл {file_path} не найден")
            return False
        
        try:
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем, есть ли уже импорт
            if f"import {module_name}" in content or f"from {module_name}" in content:
                print(f"✅ Импорт {module_name} уже есть в {file_path}")
                return True
            
            # Находим место для добавления импорта
            lines = content.split('\n')
            import_end = 0
            
            for i, line in enumerate(lines):
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    import_end = i + 1
                elif line.strip() and not line.strip().startswith('#'):
                    break
            
            # Добавляем импорт
            lines.insert(import_end, f"import {module_name}")
            new_content = '\n'.join(lines)
            
            with open(file_path_obj, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            self.fixes_applied.append(f"Добавлен импорт {module_name} в {file_path}")
            print(f"✅ Исправлено: добавлен импорт {module_name} в {file_path}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при исправлении импорта: {e}")
            return False
    
    def fix_asyncio_error(self, file_path: str) -> bool:
        """Исправляет ошибку asyncio.run()"""
        file_path_obj = self.project_root / file_path
        if not file_path_obj.exists():
            return False
        
        try:
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем asyncio.run() внутри async функции
            pattern = r'asyncio\.run\(([^)]+)\)'
            matches = list(re.finditer(pattern, content))
            
            if not matches:
                return False
            
            fixed = False
            for match in reversed(matches):
                func_call = match.group(1)
                # Заменяем asyncio.run(...) на await ...
                new_content = content[:match.start()] + f"await {func_call}" + content[match.end():]
                content = new_content
                fixed = True
            
            if fixed:
                with open(file_path_obj, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.fixes_applied.append(f"Исправлена ошибка asyncio.run() в {file_path}")
                print(f"✅ Исправлено: asyncio.run() → await в {file_path}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Ошибка при исправлении asyncio: {e}")
            return False
    
    def fix_telegram_conflict(self, telegram_token: str) -> bool:
        """Исправляет конфликт Telegram (удаляет webhook и перезапускает сервис)"""
        fixed = False
        
        # Шаг 1: Удаляем webhook
        print("   🔧 Шаг 1: Удаление webhook Telegram...")
        try:
            url = f"{TELEGRAM_API_BASE}{telegram_token}/deleteWebhook"
            response = requests.post(url, params={"drop_pending_updates": True}, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    self.fixes_applied.append("Удалён webhook Telegram")
                    print("   ✅ Webhook удалён успешно")
                    fixed = True
                else:
                    print(f"   ⚠️  Webhook не был установлен или уже удалён")
            else:
                print(f"   ⚠️  Ошибка HTTP {response.status_code} при удалении webhook")
        except Exception as e:
            print(f"   ⚠️  Ошибка при удалении webhook: {e}")
        
        # Шаг 2: Перезапускаем сервис на Render
        print("   🔧 Шаг 2: Перезапуск сервиса на Render...")
        if self.restart_render_service():
            self.fixes_applied.append("Перезапущен сервис на Render")
            print("   ✅ Сервис перезапущен")
            fixed = True
        else:
            print("   ⚠️  Не удалось перезапустить сервис (возможно, уже перезапускается)")
        
        if fixed:
            print("✅ Исправлено: конфликт Telegram обработан")
            return True
        return False
    
    def restart_render_service(self) -> bool:
        """Перезапускает сервис на Render через API"""
        try:
            # Создаём новый деплой (это перезапустит сервис)
            url = f"{RENDER_API_BASE}/services/{self.service_id}/deploys"
            data = {"clearBuildCache": False}
            
            response = requests.post(url, headers=self.headers, json=data, timeout=30)
            
            if response.status_code in [200, 201]:
                deploy = response.json()
                deploy_id = deploy.get("deploy", {}).get("id") or deploy.get("id")
                if deploy_id:
                    print(f"   📊 Deploy ID: {deploy_id}")
                    return True
                return True  # Даже если ID не получен, деплой мог начаться
            elif response.status_code == 409:
                # Конфликт - возможно, деплой уже идёт
                print("   ℹ️  Деплой уже в процессе")
                return True
            else:
                print(f"   ⚠️  Ошибка HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"   ⚠️  Ошибка при перезапуске: {e}")
            return False


class CompleteAutoFix:
    """Полностью автоматизированная система исправления"""
    
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
        
        self.deploy_checker = DeploymentChecker(render_api_key, service_id)
        self.context = ProjectContext(self.project_root)
        self.fixer = AutoFixer(self.project_root, self.context, render_api_key, service_id)
        
        self.context.analyze_project()
    
    def get_owner_id(self) -> Optional[str]:
        """Получает Owner ID"""
        if self.owner_id:
            return self.owner_id
        
        try:
            response = requests.get(f"{RENDER_API_BASE}/services/{self.service_id}", 
                                  headers=self.headers, timeout=10)
            if response.status_code == 200:
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
                return None
            
            url = f"{RENDER_API_BASE}/logs"
            params = {
                "ownerId": owner_id,
                "resource": self.service_id,
                "limit": lines
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            if response.status_code != 200:
                return None
            
            logs_data = response.json()
            
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
            return []
        except Exception as e:
            print(f"❌ Ошибка при получении логов: {e}")
            return None
    
    def analyze_errors(self, logs: List[Dict]) -> List[Dict]:
        """Анализирует логи и создаёт задачи"""
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
            error_hash = hash(message[:200])
            if error_hash in seen_errors:
                continue
            seen_errors.add(error_hash)
            
            error_context = self.context.get_related_context(message)
            
            if "modulenotfounderror" in message_lower or "no module named" in message_lower:
                match = re.search(r"no module named ['\"]([^'\"]+)['\"]", message_lower)
                if match:
                    module_name = match.group(1)
                    file_path = error_context.get("files", [None])[0] if error_context.get("files") else None
                    tasks.append({
                        "type": "missing_import",
                        "error": message,
                        "module": module_name,
                        "file": file_path or "bot_kie.py",
                        "priority": "high"
                    })
            
            elif "asyncio.run() cannot be called" in message or "running event loop" in message_lower:
                file_path = error_context.get("files", [None])[0] if error_context.get("files") else "bot_kie.py"
                tasks.append({
                    "type": "asyncio_error",
                    "error": message,
                    "file": file_path,
                    "priority": "critical"
                })
            
            elif "409" in message or "conflict" in message_lower or "terminated by other getUpdates" in message_lower or "telegram.error.Conflict" in message:
                tasks.append({
                    "type": "telegram_conflict",
                    "error": message,
                    "priority": "critical",
                    "description": "Конфликт Telegram: запущено несколько экземпляров бота"
                })
        
        return tasks
    
    def apply_fixes(self, tasks: List[Dict]) -> int:
        """Применяет исправления"""
        fixes_count = 0
        
        print("\n" + "=" * 80)
        print("🔧 ПРИМЕНЕНИЕ ИСПРАВЛЕНИЙ")
        print("=" * 80)
        
        for task in tasks:
            task_type = task.get("type")
            print(f"\n📋 Задача: {task_type}")
            if task.get('description'):
                print(f"   Описание: {task.get('description')}")
            print(f"   Ошибка: {task.get('error', '')[:150]}...")
            
            if task_type == "missing_import":
                module = task.get("module")
                file_path = task.get("file")
                if self.fixer.fix_missing_import(module, file_path):
                    fixes_count += 1
            
            elif task_type == "asyncio_error":
                file_path = task.get("file")
                if self.fixer.fix_asyncio_error(file_path):
                    fixes_count += 1
            
            elif task_type == "telegram_conflict":
                if self.fixer.fix_telegram_conflict(self.telegram_token):
                    fixes_count += 1
        
        return fixes_count
    
    def commit_and_push(self, fixes_count: int) -> bool:
        """Коммитит и пушит изменения"""
        if fixes_count == 0:
            return False
        
        print("\n" + "=" * 80)
        print("📤 КОММИТ И ПУШ ИЗМЕНЕНИЙ")
        print("=" * 80)
        
        try:
            # Git add
            result = subprocess.run(
                ["git", "add", "."],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                print(f"⚠️  Ошибка git add: {result.stderr}")
            
            # Git commit
            commit_message = f"Auto-fix: исправлено {fixes_count} ошибок из логов"
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                if "nothing to commit" in result.stdout.lower():
                    print("ℹ️  Нет изменений для коммита")
                    return False
                print(f"⚠️  Ошибка git commit: {result.stderr}")
                return False
            
            print(f"✅ Коммит создан: {commit_message}")
            
            # Git push
            result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                print("✅ Изменения отправлены в GitHub")
                return True
            else:
                print(f"❌ Ошибка git push: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при коммите/пуше: {e}")
            return False
    
    def run(self, interval: int = 60):
        """Основной цикл"""
        print("=" * 80)
        print("🤖 ПОЛНОСТЬЮ АВТОМАТИЗИРОВАННАЯ СИСТЕМА ИСПРАВЛЕНИЯ ОШИБОК")
        print("=" * 80)
        print(f"📊 Интервал проверки: {interval} секунд")
        print("Нажмите Ctrl+C для остановки")
        print("=" * 80)
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                print("\n\n" + "=" * 80)
                print(f"🔄 ИТЕРАЦИЯ #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 80)
                
                # Проверяем статус деплоя
                if self.deploy_checker.is_deploying():
                    print("⏳ Обнаружен активный деплой, ждём завершения...")
                    self.deploy_checker.wait_for_deploy_complete()
                    print("✅ Деплой завершён, продолжаем проверку ошибок...")
                    time.sleep(10)  # Небольшая пауза после деплоя
                
                # Получаем логи
                print("\n📥 Получение логов...")
                logs = self.get_logs(lines=200)
                if not logs:
                    print("⚠️  Не удалось получить логи")
                    time.sleep(interval)
                    continue
                
                print(f"✅ Получено {len(logs)} строк логов")
                
                # Анализируем ошибки
                print("\n🔍 Анализ ошибок...")
                tasks = self.analyze_errors(logs)
                
                if tasks:
                    print(f"\n📊 Найдено ошибок: {len(tasks)}")
                    
                    critical = [t for t in tasks if t.get("priority") == "critical"]
                    high = [t for t in tasks if t.get("priority") == "high"]
                    
                    print(f"   🚨 Критических: {len(critical)}")
                    print(f"   ⚠️  Высокий приоритет: {len(high)}")
                    
                    # Применяем исправления
                    fixes_count = self.apply_fixes(tasks)
                    
                    if fixes_count > 0:
                        print(f"\n✅ Применено исправлений: {fixes_count}")
                        
                        # Коммитим и пушим
                        if self.commit_and_push(fixes_count):
                            print("\n⏳ Ожидание деплоя после исправлений...")
                            self.deploy_checker.wait_for_deploy_complete()
                            print("✅ Деплой после исправлений завершён")
                else:
                    print("✅ Критических ошибок не найдено")
                
                # Ждём перед следующей проверкой
                print(f"\n⏳ Следующая проверка через {interval} секунд...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 СИСТЕМА ОСТАНОВЛЕНА")
            print("=" * 80)


def main():
    """Главная функция"""
    print("=" * 80)
    print("🤖 ПОЛНОСТЬЮ АВТОМАТИЗИРОВАННАЯ СИСТЕМА ИСПРАВЛЕНИЯ")
    print("=" * 80)
    print()
    
    render_api_key = os.getenv("RENDER_API_KEY", "rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw")
    service_id = os.getenv("RENDER_SERVICE_ID", "srv-d4s025er433s73bsf62g")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y")
    
    system = CompleteAutoFix(render_api_key, service_id, telegram_token)
    system.run(interval=60)


if __name__ == "__main__":
    main()







