#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Интеграция с Cursor AI для умного исправления ошибок
- Глубокий анализ структуры проекта
- Понимание кнопок, генераций, KIE API
- Создание детальных задач для Cursor
- Работа в связке с Cursor для контекстного исправления
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

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Render API
RENDER_API_BASE = "https://api.render.com/v1"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Файлы для Cursor
CURSOR_DIR = Path(__file__).parent / ".cursor"
CURSOR_TASKS_FILE = CURSOR_DIR / "auto_fix_tasks.json"
CURSOR_PROMPT_FILE = CURSOR_DIR / "auto_fix_prompt.md"
CURSOR_STATE_FILE = CURSOR_DIR / "cursor_state.json"
SERVICES_CONFIG_FILE = Path(__file__).parent / "services_config.json"
CURSOR_DIR.mkdir(exist_ok=True)


class ProjectAnalyzer:
    """Глубокий анализ структуры проекта"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.callbacks_map = {}  # callback_data -> handler info
        self.generation_functions = {}  # function -> generation info
        self.kie_api_calls = {}  # model_id -> API call info
        self.imports_graph = {}  # file -> imports
        self.functions_map = {}  # function -> file, line
        self.classes_map = {}  # class -> file, line
        
    def analyze_project(self):
        """Полный анализ проекта"""
        print("🔍 Глубокий анализ структуры проекта...", flush=True)
        sys.stdout.flush()
        
        # Анализируем основные файлы
        main_files = [
            "bot_kie.py", "run_bot.py", "database.py",
            "kie_gateway.py", "kie_models.py", "business_layer.py",
            "helpers.py", "config.py", "kie_client.py"
        ]
        
        print(f"📁 Анализ {len(main_files)} файлов...", flush=True)
        sys.stdout.flush()
        for i, file_name in enumerate(main_files, 1):
            file_path = self.project_root / file_name
            if file_path.exists():
                print(f"   [{i}/{len(main_files)}] Анализ {file_name}...", end="\r", flush=True)
                self.analyze_file(file_path)
            else:
                print(f"   [{i}/{len(main_files)}] ⚠️  {file_name} не найден", end="\r", flush=True)
        print()  # Новая строка после прогресса
        sys.stdout.flush()
        
        # Специальный анализ для bot_kie.py (может быть долгим из-за размера файла)
        print("🤖 Специальный анализ bot_kie.py...", flush=True)
        sys.stdout.flush()
        bot_file = self.project_root / "bot_kie.py"
        if bot_file.exists():
            # Упрощённый анализ для больших файлов (только основные паттерны)
            try:
                print("   ⚡ Быстрый анализ (основные паттерны)...", flush=True)
                sys.stdout.flush()
                self.analyze_bot_structure_fast(bot_file)
                print("   ✅ Структура бота проанализирована (быстрый режим)", flush=True)
            except Exception as e:
                print(f"   ⚠️  Ошибка при анализе: {e}, пропускаю...", flush=True)
        else:
            print("   ⚠️  bot_kie.py не найден", flush=True)
        sys.stdout.flush()
        
        print(f"\n✅ Проанализировано:", flush=True)
        print(f"   Файлов: {len(self.imports_graph)}", flush=True)
        print(f"   Функций: {len(self.functions_map)}", flush=True)
        print(f"   Классов: {len(self.classes_map)}", flush=True)
        print(f"   Callback handlers: {len(self.callbacks_map)}", flush=True)
        print(f"   Generation functions: {len(self.generation_functions)}", flush=True)
        print(f"   KIE API calls: {len(self.kie_api_calls)}", flush=True)
        sys.stdout.flush()
    
    def analyze_file(self, file_path: Path):
        """Анализирует один файл"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            file_name = file_path.name
            self.imports_graph[file_name] = []
            
            # Парсим AST
            try:
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    # Импорты
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.imports_graph[file_name].append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            self.imports_graph[file_name].append(f"{module}.{alias.name}")
                    
                    # Функции
                    if isinstance(node, ast.FunctionDef):
                        self.functions_map[node.name] = {
                            "file": str(file_path),
                            "line": node.lineno,
                            "async": isinstance(node, ast.AsyncFunctionDef)
                        }
                    
                    # Классы
                    elif isinstance(node, ast.ClassDef):
                        self.classes_map[node.name] = {
                            "file": str(file_path),
                            "line": node.lineno
                        }
            except:
                pass
                
        except Exception as e:
            pass
    
    def analyze_bot_structure_fast(self, bot_file: Path):
        """Быстрый анализ структуры бота (только основные паттерны)"""
        try:
            print(f"   📖 Чтение {bot_file.name}...", flush=True)
            sys.stdout.flush()
            
            # Читаем файл построчно для экономии памяти
            callback_count = 0
            gen_count = 0
            kie_count = 0
            
            with open(bot_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    # Быстрый поиск callback_data (только основные паттерны)
                    if 'callback_data' in line and ('=' in line or ':' in line):
                        match = re.search(r"callback_data\s*[=:]\s*['\"]([^'\"]+)['\"]", line)
                        if match:
                            callback_data = match.group(1)
                            if callback_data not in self.callbacks_map:
                                self.callbacks_map[callback_data] = {
                                    "handler": "button_callback",
                                    "line": line_num,
                                    "file": str(bot_file)
                                }
                                callback_count += 1
                    
                    # Быстрый поиск generation functions (только основные)
                    if 'async def' in line and ('generation' in line.lower() or 'generate' in line.lower()):
                        match = re.search(r'async def (\w+)', line)
                        if match:
                            func_name = match.group(1)
                            if func_name not in self.generation_functions:
                                self.generation_functions[func_name] = {
                                    "file": str(bot_file),
                                    "line": line_num,
                                    "kie_calls": []
                                }
                                gen_count += 1
                    
                    # Быстрый поиск model_id (только основные)
                    if 'model_id' in line and ('=' in line):
                        match = re.search(r"model_id\s*=\s*['\"]([^'\"]+)['\"]", line)
                        if match:
                            model_id = match.group(1)
                            if model_id not in self.kie_api_calls:
                                self.kie_api_calls[model_id] = {
                                    "file": str(bot_file),
                                    "line": line_num
                                }
                                kie_count += 1
                    
                    # Показываем прогресс каждые 5000 строк
                    if line_num % 5000 == 0:
                        print(f"      Обработано {line_num} строк...", flush=True)
                        sys.stdout.flush()
            
            print(f"   ✅ Найдено: {callback_count} callbacks, {gen_count} генераций, {kie_count} KIE API", flush=True)
            sys.stdout.flush()
                        
        except Exception as e:
            print(f"   ❌ Ошибка при анализе {bot_file.name}: {e}", flush=True)
            sys.stdout.flush()
    
    def analyze_bot_structure(self, bot_file: Path):
        """Специальный анализ структуры бота"""
        try:
            print(f"   📖 Чтение {bot_file.name} (это может занять время для больших файлов)...", flush=True)
            sys.stdout.flush()
            with open(bot_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"   ✅ {bot_file.name} прочитан ({len(content)} символов)", flush=True)
            sys.stdout.flush()
            
            # Ищем callback handlers
            print("   🔍 Поиск callback handlers...", flush=True)
            sys.stdout.flush()
            callback_pattern = r"callback_data\s*[=:]\s*['\"]([^'\"]+)['\"]"
            callback_count = 0
            for match in re.finditer(callback_pattern, content):
                callback_count += 1
                # Показываем прогресс каждые 50 найденных
                if callback_count % 50 == 0:
                    print(f"      Найдено {callback_count} callback handlers...", flush=True)
                    sys.stdout.flush()
                callback_data = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                
                # Ищем функцию-обработчик
                lines = content.split('\n')
                handler_func = None
                for i in range(max(0, line_num - 50), min(len(lines), line_num + 50)):
                    func_match = re.search(r'async def (\w+)', lines[i])
                    if func_match:
                        handler_func = func_match.group(1)
                        break
                
                self.callbacks_map[callback_data] = {
                    "handler": handler_func or "button_callback",
                    "line": line_num,
                    "file": str(bot_file)
                }
            
            # Ищем generation functions
            gen_patterns = [
                r"async def (confirm_generation|start_generation|generate_\w+)",
                r"def (generate_\w+|create_task|get_status)"
            ]
            for pattern in gen_patterns:
                for match in re.finditer(pattern, content):
                    func_name = match.group(1)
                    line_num = content[:match.start()].count('\n') + 1
                    
                    # Ищем KIE API calls в функции
                    func_start = match.start()
                    func_end = self._find_function_end(content, func_start)
                    func_body = content[func_start:func_end]
                    
                    kie_calls = self._extract_kie_api_calls(func_body)
                    
                    self.generation_functions[func_name] = {
                        "file": str(bot_file),
                        "line": line_num,
                        "kie_calls": kie_calls
                    }
            print(f"   ✅ Найдено {len(self.generation_functions)} generation functions", flush=True)
            sys.stdout.flush()
            
            # Ищем KIE API calls
            print("   🔍 Поиск KIE API calls...", flush=True)
            sys.stdout.flush()
            kie_patterns = [
                r"createTask\s*\(",
                r"get_status\s*\(",
                r"get_kie_gateway\s*\(",
                r"model_id\s*=\s*['\"]([^'\"]+)['\"]"
            ]
            for pattern in kie_patterns:
                for match in re.finditer(pattern, content):
                    line_num = content[:match.start()].count('\n') + 1
                    if 'model_id' in pattern:
                        model_id = match.group(1)
                        self.kie_api_calls[model_id] = {
                            "file": str(bot_file),
                            "line": line_num
                        }
                        
        except Exception as e:
            pass
    
    def _find_function_end(self, content: str, start_pos: int) -> int:
        """Находит конец функции"""
        lines = content[start_pos:].split('\n')
        indent_level = None
        for i, line in enumerate(lines[1:], 1):
            if line.strip():
                current_indent = len(line) - len(line.lstrip())
                if indent_level is None:
                    indent_level = current_indent
                elif current_indent <= indent_level and not line.strip().startswith('#'):
                    return start_pos + sum(len(l) + 1 for l in lines[:i])
        return len(content)
    
    def _extract_kie_api_calls(self, func_body: str) -> List[Dict]:
        """Извлекает вызовы KIE API из функции"""
        calls = []
        patterns = [
            r"createTask\s*\([^)]*model[^)]*\)",
            r"get_status\s*\([^)]+\)",
            r"gateway\.(create_task|get_status)"
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, func_body):
                calls.append({
                    "type": "kie_api",
                    "call": match.group(0)[:100]
                })
        return calls
    
    def get_error_context(self, error_message: str, error_file: Optional[str] = None) -> Dict:
        """Получает полный контекст для ошибки"""
        context = {
            "error_message": error_message,
            "related_files": [],
            "related_functions": [],
            "related_callbacks": [],
            "related_generations": [],
            "related_kie_calls": [],
            "imports_chain": [],
            "suggestions": []
        }
        
        # Ищем упоминания функций
        for func_name, func_info in self.functions_map.items():
            if func_name in error_message:
                context["related_functions"].append({
                    "name": func_name,
                    "file": func_info["file"],
                    "line": func_info["line"],
                    "async": func_info.get("async", False)
                })
                context["related_files"].append(func_info["file"])
        
        # Ищем упоминания callback_data
        for callback_data, callback_info in self.callbacks_map.items():
            if callback_data in error_message or callback_data.replace(':', '_') in error_message:
                context["related_callbacks"].append({
                    "callback_data": callback_data,
                    "handler": callback_info["handler"],
                    "file": callback_info["file"],
                    "line": callback_info["line"]
                })
                context["related_files"].append(callback_info["file"])
        
        # Ищем упоминания генераций
        for gen_func, gen_info in self.generation_functions.items():
            if gen_func in error_message:
                context["related_generations"].append({
                    "function": gen_func,
                    "file": gen_info["file"],
                    "line": gen_info["line"],
                    "kie_calls": gen_info.get("kie_calls", [])
                })
                context["related_files"].append(gen_info["file"])
        
        # Ищем упоминания моделей KIE
        for model_id, model_info in self.kie_api_calls.items():
            if model_id in error_message:
                context["related_kie_calls"].append({
                    "model_id": model_id,
                    "file": model_info["file"],
                    "line": model_info["line"]
                })
                context["related_files"].append(model_info["file"])
        
        # Строим цепочку импортов
        if error_file:
            error_file_name = Path(error_file).name
            context["imports_chain"] = self._build_imports_chain(error_file_name)
        
        # Генерируем предложения
        context["suggestions"] = self._generate_suggestions(error_message, context)
        
        return context
    
    def _build_imports_chain(self, file_name: str, visited: Set[str] = None) -> List[str]:
        """Строит цепочку импортов"""
        if visited is None:
            visited = set()
        if file_name in visited:
            return []
        visited.add(file_name)
        
        chain = [file_name]
        imports = self.imports_graph.get(file_name, [])
        for imp in imports[:5]:  # Ограничиваем глубину
            if imp not in visited:
                chain.extend(self._build_imports_chain(imp, visited))
        return chain
    
    def _generate_suggestions(self, error_message: str, context: Dict) -> List[str]:
        """Генерирует предложения по исправлению"""
        suggestions = []
        error_lower = error_message.lower()
        
        if "modulenotfounderror" in error_lower:
            match = re.search(r"no module named ['\"]([^'\"]+)['\"]", error_lower)
            if match:
                module = match.group(1)
                suggestions.append(f"Добавить 'import {module}' в начало файла")
                suggestions.append(f"Проверить, что {module} есть в requirements.txt")
        
        if "attributeerror" in error_lower:
            suggestions.append("Проверить, что объект инициализирован перед использованием")
            suggestions.append("Проверить правильность имени атрибута")
        
        if "callback" in error_lower or "button" in error_lower:
            suggestions.append("Проверить, что callback_data обработан в button_callback")
            suggestions.append("Убедиться, что query.answer() вызван")
            if context.get("related_callbacks"):
                suggestions.append(f"Проверить обработчик для: {context['related_callbacks'][0]['callback_data']}")
        
        if "generation" in error_lower or "kie" in error_lower:
            suggestions.append("Проверить подключение к KIE API")
            suggestions.append("Проверить параметры генерации согласно документации KIE")
            suggestions.append("Убедиться, что модель поддерживает запрашиваемый mode")
        
        if "asyncio" in error_lower:
            suggestions.append("Заменить asyncio.run() на await внутри async функции")
            suggestions.append("Проверить, что функция объявлена как async")
        
        return suggestions


class CursorAIIntegration:
    """Интеграция с Cursor AI"""
    
    def __init__(self, render_api_key: str, service_id: str, telegram_token: str, service_name: str = None):
        self.render_api_key = render_api_key
        self.service_id = service_id
        self.telegram_token = telegram_token
        self.service_name = service_name or f"Service {service_id[:10]}..."
        self.project_root = Path(__file__).parent
        self.headers = {
            "Authorization": f"Bearer {render_api_key}",
            "Accept": "application/json"
        }
        self.owner_id = None
        
        # Анализ проекта
        print("🔍 Инициализация анализатора проекта...", flush=True)
        sys.stdout.flush()
        self.analyzer = ProjectAnalyzer(self.project_root)
        print("📊 Запуск анализа проекта...", flush=True)
        sys.stdout.flush()
        self.analyzer.analyze_project()
        print("✅ Анализ проекта завершён", flush=True)
        sys.stdout.flush()
        
        # State
        print("💾 Загрузка состояния...", flush=True)
        sys.stdout.flush()
        self.state = self.load_state()
        print("✅ Состояние загружено", flush=True)
        sys.stdout.flush()
    
    def load_state(self) -> Dict:
        """Загружает состояние"""
        if CURSOR_STATE_FILE.exists():
            try:
                with open(CURSOR_STATE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "last_deploy_time": None,
            "processed_errors": [],
            "last_check": None
        }
    
    def save_state(self):
        """Сохраняет состояние"""
        try:
            with open(CURSOR_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except:
            pass
    
    def get_owner_id(self) -> Optional[str]:
        """Получает Owner ID"""
        try:
            print("   🔗 Подключение к Render API...", end="\r")
            response = requests.get(f"{RENDER_API_BASE}/services/{self.service_id}", 
                                  headers=self.headers, timeout=10)
            if response.status_code == 200:
                service_data = response.json()
                owner_id = service_data.get("ownerId") or service_data.get("service", {}).get("ownerId")
                if owner_id:
                    print(f"   ✅ Owner ID получен: {owner_id[:20]}...")
                else:
                    print("   ⚠️  Owner ID не найден в ответе")
                return owner_id
            else:
                print(f"   ❌ Ошибка API: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Ошибка при получении Owner ID: {e}")
        return None
    
    def get_logs(self, lines: int = 500) -> Optional[List[Dict]]:
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
            logs_list = []
            
            if isinstance(logs_data, list):
                logs_list = logs_data
            elif isinstance(logs_data, dict) and "logs" in logs_data:
                logs_list = logs_data["logs"]
            
            processed_logs = []
            for log in logs_list:
                if isinstance(log, dict):
                    message = log.get("message", log.get("text", str(log)))
                    processed_logs.append({
                        "message": message,
                        "timestamp": log.get("timestamp", log.get("createdAt", "")),
                        "level": log.get("level", "INFO")
                    })
            
            return processed_logs
            
        except Exception as e:
            print(f"❌ Ошибка при получении логов: {e}")
            return None
    
    def analyze_errors(self, logs: List[Dict]) -> List[Dict]:
        """Анализирует ошибки с полным контекстом"""
        errors = []
        seen_signatures = set()
        
        for log in logs:
            message = log.get("message", "")
            if not message or "error" not in message.lower():
                continue
            
            # Игнорируем шум
            noise_patterns = [r"timeout", r"retry", r"429", r"503"]
            if any(re.search(p, message.lower()) for p in noise_patterns):
                continue
            
            # Определяем тип ошибки
            error_type = None
            error_file = None
            
            # Ищем файл в traceback
            file_match = re.search(r'File "([^"]+)"', message)
            if file_match:
                error_file = file_match.group(1)
            
            if "modulenotfounderror" in message.lower() or "no module named" in message.lower():
                error_type = "missing_import"
            elif "asyncio" in message.lower() and "run()" in message:
                error_type = "asyncio_error"
            elif "409" in message or ("conflict" in message.lower() and "telegram" in message.lower()):
                error_type = "telegram_conflict"
            elif "attributeerror" in message.lower():
                error_type = "attribute_error"
            elif "nameerror" in message.lower():
                error_type = "name_error"
            elif "syntaxerror" in message.lower():
                error_type = "syntax_error"
            else:
                error_type = "general_error"
            
            # Получаем контекст
            context = self.analyzer.get_error_context(message, error_file)
            
            # Создаём уникальную сигнатуру
            signature = f"{error_type}:{message[:100]}:{error_file or 'unknown'}"
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            
            errors.append({
                "type": error_type,
                "message": message,
                "file": error_file,
                "timestamp": log.get("timestamp", ""),
                "context": context,
                "signature": signature
            })
        
        return errors
    
    def create_cursor_tasks(self, errors: List[Dict]):
        """Создаёт детальные задачи для Cursor"""
        tasks = []
        
        for error in errors:
            context = error.get("context", {})
            
            task = {
                "id": error["signature"],
                "type": error["type"],
                "error": error["message"],
                "file": error.get("file"),
                "timestamp": error.get("timestamp"),
                "priority": "critical" if error["type"] in ["missing_import", "asyncio_error", "telegram_conflict"] else "high",
                "context": {
                    "related_files": context.get("related_files", []),
                    "related_functions": context.get("related_functions", []),
                    "related_callbacks": context.get("related_callbacks", []),
                    "related_generations": context.get("related_generations", []),
                    "related_kie_calls": context.get("related_kie_calls", []),
                    "imports_chain": context.get("imports_chain", []),
                    "suggestions": context.get("suggestions", [])
                },
                "fix_instructions": self._generate_fix_instructions(error, context),
                "status": "pending",
                "created_at": datetime.now().isoformat()
            }
            
            tasks.append(task)
        
        return tasks
    
    def _generate_fix_instructions(self, error: Dict, context: Dict) -> str:
        """Генерирует детальные инструкции по исправлению"""
        instructions = []
        error_type = error["type"]
        
        instructions.append(f"Тип ошибки: {error_type}")
        instructions.append(f"Файл: {error.get('file', 'неизвестен')}")
        instructions.append("")
        instructions.append("КОНТЕКСТ ПРОЕКТА:")
        
        if context.get("related_functions"):
            instructions.append("Связанные функции:")
            for func in context["related_functions"][:3]:
                instructions.append(f"  - {func['name']} в {func['file']} (строка {func['line']})")
            instructions.append("")
        
        if context.get("related_callbacks"):
            instructions.append("Связанные кнопки:")
            for cb in context["related_callbacks"][:3]:
                instructions.append(f"  - callback_data: {cb['callback_data']}")
                instructions.append(f"    handler: {cb['handler']} в {cb['file']} (строка {cb['line']})")
            instructions.append("")
        
        if context.get("related_generations"):
            instructions.append("Связанные генерации:")
            for gen in context["related_generations"][:2]:
                instructions.append(f"  - {gen['function']} в {gen['file']} (строка {gen['line']})")
            instructions.append("")
        
        if context.get("suggestions"):
            instructions.append("ПРЕДЛОЖЕНИЯ ПО ИСПРАВЛЕНИЮ:")
            for suggestion in context["suggestions"]:
                instructions.append(f"  - {suggestion}")
            instructions.append("")
        
        instructions.append("ВАЖНО:")
        instructions.append("  - Учитывать структуру проекта (кнопки → handlers → генерации → KIE API)")
        instructions.append("  - Проверить все связанные функции и файлы")
        instructions.append("  - Убедиться, что исправление не сломает другие компоненты")
        instructions.append("  - Протестировать кнопки и генерации после исправления")
        
        return "\n".join(instructions)
    
    def save_cursor_prompt(self, tasks: List[Dict]):
        """Сохраняет промпт для Cursor"""
        if not tasks:
            return
        
        with open(CURSOR_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write("# 🤖 ЗАДАЧИ ДЛЯ CURSOR AI: УМНОЕ ИСПРАВЛЕНИЕ ОШИБОК\n\n")
            f.write(f"**Создано:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 📋 КОНТЕКСТ ПРОЕКТА\n\n")
            f.write("**Структура проекта:**\n")
            f.write("- Telegram бот с нейросетями (KIE AI)\n")
            f.write("- Кнопки: callback handlers в `button_callback()`\n")
            f.write("- Генерации: функции `confirm_generation()`, `start_generation()`\n")
            f.write("- KIE API: `kie_gateway.py`, `kie_client.py`, `kie_models.py`\n")
            f.write("- База данных: `database.py` (PostgreSQL через asyncpg)\n")
            f.write("- Бизнес-логика: `business_layer.py`\n\n")
            f.write("**Важно:** Все исправления должны учитывать:\n")
            f.write("- Работу кнопок (query.answer() обязателен)\n")
            f.write("- Генерации через KIE API (строго по документации)\n")
            f.write("- Структуру callback_data → handlers\n")
            f.write("- Асинхронность (async/await)\n\n")
            f.write("---\n\n")
            
            for i, task in enumerate(tasks, 1):
                f.write(f"## 🚨 ЗАДАЧА {i}: {task['type']}\n\n")
                f.write(f"**Приоритет:** {task['priority']}\n\n")
                f.write(f"**Ошибка:**\n```\n{task['error'][:500]}\n```\n\n")
                
                if task.get('file'):
                    f.write(f"**Файл:** `{task['file']}`\n\n")
                
                f.write("**КОНТЕКСТ:**\n\n")
                
                context = task.get('context', {})
                
                if context.get('related_functions'):
                    f.write("**Связанные функции:**\n")
                    for func in context['related_functions'][:5]:
                        f.write(f"- `{func['name']}` в `{func['file']}` (строка {func['line']})\n")
                    f.write("\n")
                
                if context.get('related_callbacks'):
                    f.write("**Связанные кнопки:**\n")
                    for cb in context['related_callbacks'][:5]:
                        f.write(f"- `{cb['callback_data']}` → handler: `{cb['handler']}` в `{cb['file']}` (строка {cb['line']})\n")
                    f.write("\n")
                
                if context.get('related_generations'):
                    f.write("**Связанные генерации:**\n")
                    for gen in context['related_generations'][:3]:
                        f.write(f"- `{gen['function']}` в `{gen['file']}` (строка {gen['line']})\n")
                    f.write("\n")
                
                if context.get('related_kie_calls'):
                    f.write("**Связанные KIE API вызовы:**\n")
                    for kie in context['related_kie_calls'][:3]:
                        f.write(f"- Модель: `{kie['model_id']}` в `{kie['file']}` (строка {kie['line']})\n")
                    f.write("\n")
                
                f.write("**ИНСТРУКЦИИ ПО ИСПРАВЛЕНИЮ:**\n\n")
                f.write(f"{task['fix_instructions']}\n\n")
                f.write("---\n\n")
            
            f.write("## ✅ ЧТО НУЖНО СДЕЛАТЬ\n\n")
            f.write("1. Проанализировать каждую задачу с учётом контекста проекта\n")
            f.write("2. Исправить ошибки, учитывая структуру кнопок, генераций, KIE API\n")
            f.write("3. Убедиться, что исправления не сломают другие компоненты\n")
            f.write("4. Протестировать работу кнопок и генераций\n")
            f.write("5. Коммитить изменения с понятным сообщением\n\n")
            f.write("**ВАЖНО:** Все исправления должны обеспечивать:\n")
            f.write("- ✅ Работу всех кнопок бота\n")
            f.write("- ✅ Генерации через KIE AI\n")
            f.write("- ✅ Корректную работу с базой данных\n")
            f.write("- ✅ Асинхронность и обработку ошибок\n")
        
        # Сохраняем задачи в JSON
        existing_tasks = []
        if CURSOR_TASKS_FILE.exists():
            try:
                with open(CURSOR_TASKS_FILE, 'r', encoding='utf-8') as f:
                    existing_tasks = json.load(f)
            except:
                pass
        
        # Добавляем новые задачи
        existing_ids = {t.get("id") for t in existing_tasks}
        new_tasks = [t for t in tasks if t["id"] not in existing_ids]
        existing_tasks.extend(new_tasks)
        
        with open(CURSOR_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_tasks, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Создано задач для Cursor: {len(new_tasks)}")
        print(f"   Промпт: {CURSOR_PROMPT_FILE}")
        print(f"   Задачи: {CURSOR_TASKS_FILE}")
    
    def run(self, interval: int = 120):
        """Основной цикл"""
        print("=" * 80)
        print("🤖 ИНТЕГРАЦИЯ С CURSOR AI ДЛЯ УМНОГО ИСПРАВЛЕНИЯ")
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
                
                # Получаем логи
                print(f"\n📥 Получение логов с Render ({self.service_name})...")
                print("   Получение owner_id...", end="\r")
                logs = self.get_logs(lines=500)
                if not logs:
                    print("   ❌ Не удалось получить логи")
                    print(f"   ⚠️  Проверьте RENDER_API_KEY и Service ID: {self.service_id}")
                    time.sleep(interval)
                    continue
                
                print(f"   ✅ Получено {len(logs)} строк логов")
                
                # Анализируем ошибки с контекстом
                print("\n🔍 Анализ ошибок с контекстом проекта...")
                errors = self.analyze_errors(logs)
                
                if not errors:
                    print("✅ Критических ошибок не найдено")
                    time.sleep(interval)
                    continue
                
                print(f"📊 Найдено ошибок: {len(errors)}")
                
                # Создаём задачи для Cursor
                print("\n📝 Создание задач для Cursor AI...")
                tasks = self.create_cursor_tasks(errors)
                
                # Сохраняем промпт для Cursor
                self.save_cursor_prompt(tasks)
                
                print(f"\n💡 Откройте файл .cursor/auto_fix_prompt.md в Cursor")
                print(f"   Cursor AI автоматически увидит задачи и исправит ошибки")
                print(f"   Сервис: {self.service_name} ({self.service_id})")
                
                # Обновляем состояние
                self.state["last_check"] = datetime.now().isoformat()
                self.state["processed_errors"].extend([e["signature"] for e in errors])
                self.save_state()
                
                # Ждём перед следующей проверкой
                print(f"\n⏳ Следующая проверка через {interval} секунд...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 СИСТЕМА ОСТАНОВЛЕНА")
            print("=" * 80)


def load_services_config() -> Dict:
    """Загружает конфигурацию сервисов"""
    if SERVICES_CONFIG_FILE.exists():
        try:
            with open(SERVICES_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Ошибка при загрузке конфига: {e}")
    return {
        "services": [],
        "render_api_key": os.getenv("RENDER_API_KEY", ""),
        "default_service": None
    }


def list_services(config: Dict) -> List[Dict]:
    """Получает список активных сервисов"""
    services = config.get("services", [])
    return [s for s in services if s.get("enabled", True)]


def main():
    """Главная функция"""
    print("🚀 Инициализация системы...", flush=True)
    sys.stdout.flush()
    
    # Загружаем конфигурацию
    config = load_services_config()
    render_api_key = config.get("render_api_key") or os.getenv("RENDER_API_KEY", "")
    print(f"✅ API ключ загружен: {render_api_key[:20]}...", flush=True)
    sys.stdout.flush()
    
    # Получаем список сервисов
    services_list = list_services(config)
    
    if not services_list:
        # Fallback на старый способ (env vars)
        print("⚠️  Конфигурация сервисов не найдена, используем переменные окружения", flush=True)
        sys.stdout.flush()
        service_id = os.getenv("RENDER_SERVICE_ID", "srv-d4s025er433s73bsf62g")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y")
        
        print("✅ Параметры загружены из env vars", flush=True)
        print(f"   Service ID: {service_id}", flush=True)
        print(f"   Token: {telegram_token[:20]}...", flush=True)
        sys.stdout.flush()
        print("🔧 Создание объекта CursorAIIntegration...", flush=True)
        sys.stdout.flush()
        system = CursorAIIntegration(render_api_key, service_id, telegram_token)
        print("✅ Система готова к работе", flush=True)
        print("\n" + "=" * 80, flush=True)
        sys.stdout.flush()
        system.run(interval=120)
        return
    
    # Если несколько сервисов - выбираем или мониторим все
    if len(services_list) == 1:
        # Один сервис - используем его
        service = services_list[0]
        service_id = service["service_id"]
        telegram_token = service["telegram_token"]
        service_name = service.get("name", f"Service {service_id[:10]}...")
        
        print(f"✅ Найден сервис: {service_name}")
        print(f"🔧 Создание объекта CursorAIIntegration...")
        system = CursorAIIntegration(render_api_key, service_id, telegram_token, service_name)
        print("✅ Система готова к работе")
        print("\n" + "=" * 80)
        system.run(interval=120)
    else:
        # Несколько сервисов - мониторим все по очереди
        print(f"✅ Найдено сервисов: {len(services_list)}")
        print("\n📋 Список сервисов:")
        for i, service in enumerate(services_list, 1):
            print(f"   {i}. {service.get('name', 'Без имени')} ({service['service_id']})")
        
        print("\n🔄 Мониторинг всех сервисов...")
        print("=" * 80)
        
        iteration = 0
        try:
            while True:
                iteration += 1
                print(f"\n\n{'=' * 80}")
                print(f"🔄 ИТЕРАЦИЯ #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 80)
                
                all_errors = []
                
                for service in services_list:
                    service_id = service["service_id"]
                    telegram_token = service["telegram_token"]
                    service_name = service.get("name", f"Service {service_id[:10]}...")
                    
                    print(f"\n{'─' * 80}")
                    print(f"📡 Сервис: {service_name} ({service_id})")
                    print("─" * 80)
                    
                    try:
                        system = CursorAIIntegration(render_api_key, service_id, telegram_token, service_name)
                        
                        # Получаем логи
                        logs = system.get_logs(lines=200)
                        if not logs:
                            print(f"   ⚠️  Не удалось получить логи для {service_name}")
                            continue
                        
                        # Анализируем ошибки
                        errors = system.analyze_errors(logs)
                        if errors:
                            print(f"   📊 Найдено ошибок: {len(errors)}")
                            all_errors.extend(errors)
                        else:
                            print(f"   ✅ Ошибок не найдено")
                    
                    except Exception as e:
                        print(f"   ❌ Ошибка при обработке {service_name}: {e}")
                        continue
                
                # Создаём общий промпт для всех ошибок
                if all_errors:
                    print(f"\n📝 Создание общего промпта для {len(all_errors)} ошибок...")
                    # Используем первый сервис для создания промпта
                    first_service = services_list[0]
                    system = CursorAIIntegration(
                        render_api_key,
                        first_service["service_id"],
                        first_service["telegram_token"],
                        "Все сервисы"
                    )
                    tasks = system.create_cursor_tasks(all_errors)
                    system.save_cursor_prompt(tasks)
                    print("💡 Откройте файл .cursor/auto_fix_prompt.md в Cursor")
                
                print(f"\n⏳ Следующая проверка через 120 секунд...")
                time.sleep(120)
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 СИСТЕМА ОСТАНОВЛЕНА")
            print("=" * 80)


if __name__ == "__main__":
    main()







