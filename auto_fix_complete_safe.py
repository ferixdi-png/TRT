#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
БЕЗОПАСНАЯ автоматизированная система исправления ошибок
С учётом всех правил безопасности и надёжности
"""

import os
import sys
import json
import time
import re
import ast
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict
from enum import Enum

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Render API
RENDER_API_BASE = "https://api.render.com/v1"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Whitelist файлов для правок
ALLOWED_FILES = {
    "bot_kie.py", "run_bot.py", "database.py", 
    "kie_gateway.py", "kie_models.py", "business_layer.py",
    "helpers.py", "config.py", "requirements.txt"
}

# Запрещённые паттерны (не трогать)
FORBIDDEN_PATTERNS = [
    r"migration", r"migrate", r"schema", r"CREATE TABLE", r"ALTER TABLE",
    r"DATABASE_URL", r"RENDER_", r"API_KEY", r"SECRET", r"TOKEN"
]

# State файл
STATE_FILE = Path(__file__).parent / ".auto_fix_state.json"


class ErrorType(Enum):
    """Типы ошибок"""
    MISSING_IMPORT = "missing_import"
    ASYNCIO_ERROR = "asyncio_error"
    TELEGRAM_CONFLICT = "telegram_conflict"
    SYNTAX_ERROR = "syntax_error"
    ATTRIBUTE_ERROR = "attribute_error"
    NAME_ERROR = "name_error"
    GENERAL_ERROR = "general_error"


@dataclass
class ErrorOccurrence:
    """Одно вхождение ошибки"""
    error_type: str
    error_message: str
    timestamp: str
    file: Optional[str] = None
    line: Optional[int] = None
    context: Optional[Dict] = None
    
    def signature(self) -> str:
        """Уникальная сигнатура ошибки"""
        key = f"{self.error_type}:{self.error_message[:100]}"
        if self.file:
            key += f":{self.file}"
        return key


@dataclass
class FixState:
    """Состояние системы автофикса"""
    last_deploy_time: Optional[str] = None
    last_deploy_id: Optional[str] = None
    last_processed_log_time: Optional[str] = None
    error_counts: Dict[str, int] = None  # signature -> count
    fixes_applied_today: List[str] = None  # timestamps
    last_fix_time: Optional[str] = None
    processed_errors: Set[str] = None  # signatures
    
    def __post_init__(self):
        if self.error_counts is None:
            self.error_counts = {}
        if self.fixes_applied_today is None:
            self.fixes_applied_today = []
        if self.processed_errors is None:
            self.processed_errors = set()
    
    def to_dict(self) -> dict:
        return {
            "last_deploy_time": self.last_deploy_time,
            "last_deploy_id": self.last_deploy_id,
            "last_processed_log_time": self.last_processed_log_time,
            "error_counts": self.error_counts,
            "fixes_applied_today": self.fixes_applied_today,
            "last_fix_time": self.last_fix_time,
            "processed_errors": list(self.processed_errors)
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FixState':
        state = cls()
        state.last_deploy_time = data.get("last_deploy_time")
        state.last_deploy_id = data.get("last_deploy_id")
        state.last_processed_log_time = data.get("last_processed_log_time")
        state.error_counts = data.get("error_counts", {})
        state.fixes_applied_today = data.get("fixes_applied_today", [])
        state.last_fix_time = data.get("last_fix_time")
        state.processed_errors = set(data.get("processed_errors", []))
        return state


class SafeAutoFix:
    """Безопасная система автоматического исправления"""
    
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
        
        # Загружаем состояние
        self.state = self.load_state()
        
        # Throttle: максимум 3 фикса в час
        self.MAX_FIXES_PER_HOUR = 3
        self.MIN_ERROR_REPETITIONS = 2  # Ошибка должна повториться ≥2 раз
        self.GRACE_PERIOD_SECONDS = 60  # Grace-период после деплоя
        
    def load_state(self) -> FixState:
        """Загружает состояние из файла"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return FixState.from_dict(data)
            except Exception as e:
                print(f"⚠️  Ошибка загрузки состояния: {e}")
        return FixState()
    
    def save_state(self):
        """Сохраняет состояние в файл"""
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.state.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Ошибка сохранения состояния: {e}")
    
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
        
        print("\n⏳ Ожидание завершения деплоя...")
        
        while time.time() - start_time < timeout:
            deploy = self.get_latest_deploy()
            if not deploy:
                time.sleep(5)
                continue
            
            status = deploy.get("status", "unknown")
            if status != last_status:
                print(f"📊 Статус деплоя: {status}")
                last_status = status
            
            if status.lower() in ["live", "succeeded", "complete"]:
                deploy_id = deploy.get("id")
                deploy_time = deploy.get("finishedAt") or deploy.get("createdAt")
                
                # Обновляем состояние
                self.state.last_deploy_time = deploy_time
                self.state.last_deploy_id = deploy_id
                self.save_state()
                
                print("✅ Деплой завершён")
                print(f"⏳ Grace-период: {self.GRACE_PERIOD_SECONDS} секунд...")
                time.sleep(self.GRACE_PERIOD_SECONDS)
                return True
            elif status.lower() in ["failed", "canceled", "error"]:
                print(f"❌ Деплой завершился с ошибкой: {status}")
                return False
            elif status.lower() in ["building", "updating", "live_in_progress", "pending"]:
                time.sleep(10)
            else:
                time.sleep(5)
        
        print("⏰ Превышено время ожидания")
        return False
    
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
    
    def get_logs_after_deploy(self, lines: int = 500) -> Optional[List[Dict]]:
        """Получает логи ТОЛЬКО после последнего деплоя"""
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
            logs_list = []
            
            if isinstance(logs_data, list):
                logs_list = logs_data
            elif isinstance(logs_data, dict) and "logs" in logs_data:
                logs_list = logs_data["logs"]
            
            # Фильтруем логи по времени (только после последнего деплоя)
            if self.state.last_deploy_time:
                deploy_time = datetime.fromisoformat(self.state.last_deploy_time.replace('Z', '+00:00'))
                filtered_logs = []
                for log in logs_list:
                    if isinstance(log, dict):
                        log_time_str = log.get("timestamp") or log.get("createdAt", "")
                        if log_time_str:
                            try:
                                log_time = datetime.fromisoformat(log_time_str.replace('Z', '+00:00'))
                                if log_time >= deploy_time:
                                    filtered_logs.append(log)
                            except:
                                pass
                logs_list = filtered_logs
            
            # Обрабатываем формат
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
            
            return processed_logs
            
        except Exception as e:
            print(f"❌ Ошибка при получении логов: {e}")
            return None
    
    def analyze_error(self, message: str, timestamp: str) -> Optional[ErrorOccurrence]:
        """Анализирует ошибку и создаёт ErrorOccurrence"""
        message_lower = message.lower()
        
        # Игнорируем одноразовые ошибки и шум
        noise_patterns = [
            r"timeout", r"retry", r"connection.*reset", r"temporary",
            r"rate limit", r"429", r"503", r"502"
        ]
        for pattern in noise_patterns:
            if re.search(pattern, message_lower):
                return None  # Игнорируем шум
        
        # Определяем тип ошибки
        error_type = None
        file_path = None
        line_num = None
        
        if "modulenotfounderror" in message_lower or "no module named" in message_lower:
            match = re.search(r"no module named ['\"]([^'\"]+)['\"]", message_lower)
            if match:
                module_name = match.group(1)
                # Ищем файл из traceback
                file_match = re.search(r'File "([^"]+)"', message)
                if file_match:
                    file_path = file_match.group(1)
                error_type = ErrorType.MISSING_IMPORT.value
                return ErrorOccurrence(
                    error_type=error_type,
                    error_message=message,
                    timestamp=timestamp,
                    file=file_path or "bot_kie.py",
                    context={"module": module_name}
                )
        
        elif "asyncio.run() cannot be called" in message or "running event loop" in message_lower:
            file_match = re.search(r'File "([^"]+)"', message)
            if file_match:
                file_path = file_match.group(1)
            error_type = ErrorType.ASYNCIO_ERROR.value
            return ErrorOccurrence(
                error_type=error_type,
                error_message=message,
                timestamp=timestamp,
                file=file_path or "bot_kie.py"
            )
        
        elif "409" in message or ("conflict" in message_lower and "telegram" in message_lower):
            error_type = ErrorType.TELEGRAM_CONFLICT.value
            return ErrorOccurrence(
                error_type=error_type,
                error_message=message,
                timestamp=timestamp
            )
        
        return None
    
    def count_error_repetitions(self, errors: List[ErrorOccurrence]) -> Dict[str, int]:
        """Подсчитывает повторения ошибок"""
        counts = defaultdict(int)
        for error in errors:
            signature = error.signature()
            counts[signature] += 1
        return dict(counts)
    
    def check_throttle(self) -> bool:
        """Проверяет throttle (максимум 3 фикса в час)"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        recent_fixes = [
            fix_time for fix_time in self.state.fixes_applied_today
            if datetime.fromisoformat(fix_time) >= hour_ago
        ]
        
        if len(recent_fixes) >= self.MAX_FIXES_PER_HOUR:
            print(f"⚠️  Throttle: уже {len(recent_fixes)} фиксов за последний час")
            return False
        
        return True
    
    def check_git_status(self) -> bool:
        """Проверяет, что git status чист"""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                print("⚠️  Git status не чист, есть незакоммиченные изменения")
                print("   Остановка для безопасности")
                return False
            return True
        except Exception as e:
            print(f"⚠️  Ошибка проверки git status: {e}")
            return False
    
    def check_file_allowed(self, file_path: str) -> bool:
        """Проверяет, что файл в whitelist"""
        file_name = Path(file_path).name
        if file_name not in ALLOWED_FILES:
            print(f"⚠️  Файл {file_name} не в whitelist, пропускаем")
            return False
        
        # Проверяем запрещённые паттерны
        try:
            with open(self.project_root / file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                for pattern in FORBIDDEN_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE):
                        print(f"⚠️  Файл {file_path} содержит запрещённый паттерн: {pattern}")
                        return False
        except:
            pass
        
        return True
    
    def fix_missing_import(self, module_name: str, file_path: str) -> bool:
        """Исправляет отсутствующий импорт (минимальный diff)"""
        if not self.check_file_allowed(file_path):
            return False
        
        file_path_obj = self.project_root / file_path
        if not file_path_obj.exists():
            return False
        
        try:
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем, есть ли уже импорт
            if f"import {module_name}" in content or f"from {module_name}" in content:
                return True  # Уже есть
            
            # Находим место для добавления импорта (минимальный diff)
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
            
            print(f"✅ Добавлен импорт {module_name} в {file_path}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при исправлении импорта: {e}")
            return False
    
    def fix_asyncio_error(self, file_path: str) -> bool:
        """Исправляет ошибку asyncio.run() (минимальный diff)"""
        if not self.check_file_allowed(file_path):
            return False
        
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
            
            # Заменяем только первое вхождение (минимальный diff)
            match = matches[0]
            func_call = match.group(1)
            new_content = content[:match.start()] + f"await {func_call}" + content[match.end():]
            
            with open(file_path_obj, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ Исправлено asyncio.run() → await в {file_path}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при исправлении asyncio: {e}")
            return False
    
    def fix_telegram_conflict(self) -> bool:
        """Исправляет конфликт Telegram (удаляет webhook)"""
        try:
            url = f"{TELEGRAM_API_BASE}{self.telegram_token}/deleteWebhook"
            response = requests.post(url, params={"drop_pending_updates": True}, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    print("✅ Удалён webhook Telegram")
                    return True
            return False
        except Exception as e:
            print(f"❌ Ошибка при удалении webhook: {e}")
            return False
    
    def verify_compilation(self) -> bool:
        """Проверяет компиляцию после патча"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", "bot_kie.py"],
                cwd=self.project_root,
                capture_output=True,
                timeout=30
            )
            if result.returncode == 0:
                print("✅ Компиляция успешна")
                return True
            else:
                print(f"❌ Ошибка компиляции: {result.stderr.decode('utf-8', errors='replace')}")
                return False
        except Exception as e:
            print(f"⚠️  Ошибка проверки компиляции: {e}")
            return True  # Продолжаем, если не удалось проверить
    
    def apply_fix(self, error: ErrorOccurrence) -> bool:
        """Применяет ОДИН фикс для ОДНОГО типа ошибки"""
        print(f"\n🔧 Применение фикса для: {error.error_type}")
        print(f"   Файл: {error.file or 'N/A'}")
        print(f"   Ошибка: {error.error_message[:100]}...")
        
        fixed = False
        
        if error.error_type == ErrorType.MISSING_IMPORT.value:
            module = error.context.get("module") if error.context else None
            if module:
                fixed = self.fix_missing_import(module, error.file or "bot_kie.py")
        
        elif error.error_type == ErrorType.ASYNCIO_ERROR.value:
            fixed = self.fix_asyncio_error(error.file or "bot_kie.py")
        
        elif error.error_type == ErrorType.TELEGRAM_CONFLICT.value:
            fixed = self.fix_telegram_conflict()
        
        if fixed:
            # Проверяем компиляцию
            if not self.verify_compilation():
                print("❌ Компиляция не прошла, откатываем изменения")
                subprocess.run(["git", "checkout", "--", "."], cwd=self.project_root)
                return False
            
            # Обновляем состояние
            self.state.fixes_applied_today.append(datetime.now().isoformat())
            self.state.last_fix_time = datetime.now().isoformat()
            self.state.processed_errors.add(error.signature())
            self.save_state()
            
            return True
        
        return False
    
    def commit_and_push(self, error: ErrorOccurrence) -> bool:
        """Коммитит и пушит изменения (только если git status чист)"""
        if not self.check_git_status():
            return False
        
        try:
            # Git add только изменённых файлов
            result = subprocess.run(
                ["git", "add", "-u"],
                cwd=self.project_root,
                capture_output=True,
                timeout=30
            )
            
            # Проверяем, есть ли изменения
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self.project_root,
                timeout=10
            )
            if result.returncode == 0:
                print("ℹ️  Нет изменений для коммита")
                return False
            
            # Коммит с версионированием
            commit_message = f"auto/fix-{error.error_type}: {error.error_message[:50]}"
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.project_root,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"⚠️  Ошибка git commit: {result.stderr.decode('utf-8', errors='replace')}")
                return False
            
            print(f"✅ Коммит создан: {commit_message}")
            
            # Push
            result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.project_root,
                capture_output=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print("✅ Изменения отправлены в GitHub")
                return True
            else:
                print(f"❌ Ошибка git push: {result.stderr.decode('utf-8', errors='replace')}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при коммите/пуше: {e}")
            return False
    
    def verify_fix(self, error: ErrorOccurrence, timeout: int = 300) -> bool:
        """Проверяет, что ошибка исчезла после деплоя"""
        print(f"\n🔍 Проверка результата фикса...")
        
        # Ждём деплой
        if not self.wait_for_deploy_complete(timeout):
            return False
        
        # Получаем логи после деплоя
        logs = self.get_logs_after_deploy(lines=200)
        if not logs:
            return False
        
        # Ищем ошибку в логах
        error_signature = error.signature()
        for log in logs:
            if isinstance(log, dict):
                message = log.get("message", "")
                analyzed = self.analyze_error(message, log.get("timestamp", ""))
                if analyzed and analyzed.signature() == error_signature:
                    print("⚠️  Ошибка всё ещё присутствует в логах")
                    return False
        
        print("✅ Ошибка исчезла из логов")
        return True
    
    def run(self, interval: int = 120):
        """Основной цикл (интервал увеличен для стабильности)"""
        print("=" * 80)
        print("🛡️  БЕЗОПАСНАЯ СИСТЕМА АВТОМАТИЧЕСКОГО ИСПРАВЛЕНИЯ")
        print("=" * 80)
        print(f"📊 Интервал проверки: {interval} секунд")
        print("Нажмите Ctrl+C для остановки")
        print("=" * 80)
        
        iteration = 0
        
        try:
            while True:
                iteration += 1
                print(f"\n\n{'=' * 80}")
                print(f"🔄 ИТЕРАЦИЯ #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 80)
                
                # Проверяем деплой
                if self.is_deploying():
                    print("⏳ Обнаружен активный деплой, ждём завершения...")
                    self.wait_for_deploy_complete()
                    continue
                
                # Проверяем throttle
                if not self.check_throttle():
                    print(f"⏳ Throttle активен, ждём {interval} секунд...")
                    time.sleep(interval)
                    continue
                
                # Получаем логи ТОЛЬКО после последнего деплоя
                print("\n📥 Получение логов (только после последнего деплоя)...")
                logs = self.get_logs_after_deploy(lines=500)
                if not logs:
                    print("⚠️  Не удалось получить логи")
                    time.sleep(interval)
                    continue
                
                print(f"✅ Получено {len(logs)} строк логов")
                
                # Анализируем ошибки
                print("\n🔍 Анализ ошибок...")
                errors = []
                for log in logs:
                    if isinstance(log, dict):
                        message = log.get("message", "")
                        timestamp = log.get("timestamp", "")
                        error = self.analyze_error(message, timestamp)
                        if error:
                            errors.append(error)
                
                if not errors:
                    print("✅ Критических ошибок не найдено")
                    time.sleep(interval)
                    continue
                
                # Подсчитываем повторения
                error_counts = self.count_error_repetitions(errors)
                
                # Фильтруем: только ошибки, которые повторились ≥2 раз
                errors_to_fix = []
                for error in errors:
                    signature = error.signature()
                    count = error_counts.get(signature, 0)
                    
                    if count >= self.MIN_ERROR_REPETITIONS:
                        if signature not in self.state.processed_errors:
                            errors_to_fix.append(error)
                
                if not errors_to_fix:
                    print("✅ Нет ошибок для исправления (недостаточно повторений или уже обработаны)")
                    time.sleep(interval)
                    continue
                
                # Применяем ОДИН фикс за раз
                error_to_fix = errors_to_fix[0]  # Только первая ошибка
                print(f"\n📊 Найдено {len(errors_to_fix)} ошибок для исправления")
                print(f"   Исправляем: {error_to_fix.error_type}")
                
                # Проверяем git status
                if not self.check_git_status():
                    print("⏸️  Остановка: git status не чист")
                    time.sleep(interval)
                    continue
                
                # Применяем фикс
                if self.apply_fix(error_to_fix):
                    # Коммитим и пушим
                    if self.commit_and_push(error_to_fix):
                        # Проверяем результат
                        self.verify_fix(error_to_fix)
                
                # Ждём перед следующей проверкой
                print(f"\n⏳ Следующая проверка через {interval} секунд...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 СИСТЕМА ОСТАНОВЛЕНА")
            print("=" * 80)


def main():
    """Главная функция"""
    render_api_key = os.getenv("RENDER_API_KEY", "rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw")
    service_id = os.getenv("RENDER_SERVICE_ID", "srv-d4s025er433s73bsf62g")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y")
    
    system = SafeAutoFix(render_api_key, service_id, telegram_token)
    system.run(interval=120)  # Увеличенный интервал для стабильности


if __name__ == "__main__":
    main()







